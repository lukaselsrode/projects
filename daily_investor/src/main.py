"""
main.py — Daily investment strategy entry point.

Responsibilities:
  - Robinhood login
  - Fund top-up
  - Buy cycle: pre-filter → risk-check → batch sentiment → execute orders
  - Sell cycle: hard/soft decision engine → batch sentiment (soft only) → execute
  - Iteration loop until cash exhausted or no more candidates

Changes in this revision:
  - Portfolio risk controls: position cap, sector cap, order cap, liquidity gate
  - Sell decision engine: hard vs soft sells, stop-loss, take-profit, weak-value, yield-trap
  - make_sales() refactored: hard sells execute immediately; soft sells optionally held by sentiment
  - make_buys() passes every buy through can_buy_symbol() before placing order
"""

import datetime
import logging
import os
import sys
import time

import pandas as pd
import pyotp
import robin_stocks.robinhood as rb
from dotenv import load_dotenv

from sentiment_analysis import get_batch_sentiment_recommendations, get_sentiment_recommendation
from source_data import get_data as generate_daily_undervalued_stocks
from util import (
    AUTO_APPROVE,
    CONFIDENCE_THRESHOLD,
    DATA_DIRECTORY,
    ETFS,
    INDEX_PCT,
    METRIC_KEYS,
    METRIC_THRESHOLD,
    RISK_LIMITS,
    SELL_RULES,
    USE_SENTIMENT_ANALYSIS,
    WEEKLY_INVESTMENT,
    read_data_as_pd,
    safe_float,
    update_industry_valuations,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("investment_bot.log"),
    ],
)
logger = logging.getLogger("investment_bot")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login() -> None:
    username = os.getenv("RB_ACCT")
    password = os.getenv("RB_CREDS")
    if not username or not password:
        raise ValueError(
            "Missing required env vars: RB_ACCT and RB_CREDS must be set in .env"
        )
    mfa_code = None
    mfa_secret = os.getenv("RB_MFA_SECRET")
    if mfa_secret:
        try:
            mfa_code = pyotp.TOTP(mfa_secret).now()
            logger.info("MFA code generated from RB_MFA_SECRET")
        except Exception as e:
            logger.error(f"MFA generation failed: {e}")

    try:
        rb.login(username=username, password=password, mfa_code=mfa_code, store_session=True)
        logger.info("Logged in to Robinhood")
    except Exception as e:
        if "mfa_required" in str(e).lower() and not mfa_code:
            mfa_code = input("Enter MFA code: ").strip()
            rb.login(username=username, password=password, mfa_code=mfa_code, store_session=True)
            logger.info("Logged in with manual MFA code")
        else:
            raise


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def confirm(prompt: str) -> bool:
    if AUTO_APPROVE:
        logger.info(f"AUTO-APPROVED: {prompt}")
        return True
    return input(f"{prompt} [y/n] ").strip().lower() in ("y", "yes")


def get_available_cash() -> float:
    """Return cash minus committed-but-not-settled buy orders."""
    cash = float(rb.account.build_user_profile().get("cash", 0))

    try:
        committed = 0.0
        for order in rb.orders.get_all_open_stock_orders():
            if order.get("side") != "buy":
                continue
            if order.get("state") not in ("confirmed", "queued", "unconfirmed"):
                continue
            order_type = order.get("type")
            if order_type == "market" and order.get("extended_hours", False):
                continue
            if order_type == "market":
                for field in ("executed_notional", "total_notional", "dollar_based_amount"):
                    nested = order.get(field) or {}
                    amt = nested.get("amount")
                    if amt:
                        committed += float(amt)
                        break
            elif order_type == "limit":
                committed += float(order.get("quantity", 0)) * float(order.get("price", 0))

        available = cash - committed
    except Exception as e:
        logger.warning(f"Could not subtract pending orders from cash: {e}")
        available = cash

    logger.info(
        f"Cash: ${available:,.2f} available "
        f"(total=${cash:,.2f}, pending=${cash - available:,.2f})"
    )
    return max(0.0, available)


def add_funds_to_account() -> None:
    available = get_available_cash()
    if available >= WEEKLY_INVESTMENT:
        logger.info(f"Sufficient cash (${available:,.2f} ≥ ${WEEKLY_INVESTMENT:,.2f}) — no deposit needed")
        return

    needed = WEEKLY_INVESTMENT - available
    if not confirm(f"Cash ${available:,.2f} < target ${WEEKLY_INVESTMENT:,.2f}. Deposit ${needed:,.2f}?"):
        return

    try:
        accounts = rb.get_linked_bank_accounts()
        ach = (accounts[0].get("url") if accounts else None)
        if not ach:
            logger.warning("No linked bank account found — cannot deposit")
            return
        resp = rb.deposit_funds_to_robinhood_account(ach, round(needed, 2))
        logger.info(f"Deposit requested: ${needed:,.2f} — state={resp.get('state')}")
    except Exception as e:
        logger.error(f"Deposit failed: {e}")


def wipe_data() -> None:
    if not confirm("Wipe data directory?"):
        return
    for f in os.listdir(DATA_DIRECTORY):
        path = os.path.join(DATA_DIRECTORY, f)
        try:
            os.remove(path)
            logger.debug(f"Removed {path}")
        except Exception as e:
            logger.error(f"Could not remove {path}: {e}")
    logger.info("Data directory cleared")


# ---------------------------------------------------------------------------
# Order helpers
# ---------------------------------------------------------------------------

def _place_buy(symbol: str, allocation: float) -> bool:
    """Try fractional order, fall back to whole-share market order. Returns True on success."""
    res = rb.orders.order_buy_fractional_by_price(symbol, allocation)
    if res is not None:
        logger.info(f"Buy {symbol} ${allocation:.2f}: {res.get('state')}")
        return True

    logger.warning(f"{symbol}: fractional unavailable — retrying as market order (qty=1)")
    try:
        res = rb.orders.order_buy_market(symbol, 1)
    except Exception as e:
        logger.error(f"{symbol}: market order fallback failed: {e}")
        res = None

    if res is not None:
        logger.info(f"Buy {symbol} market order: {res.get('state')}")
        return True

    logger.warning(f"{symbol}: both order types failed")
    return False


def _place_sell(symbol: str, quantity: float) -> bool:
    if not AUTO_APPROVE and not confirm(f"Sell {quantity} shares of {symbol}?"):
        logger.info(f"Sell cancelled for {symbol}")
        return False
    res = rb.order_sell_market(symbol, quantity)
    if res:
        logger.info(f"Sold {quantity} shares of {symbol}: {res.get('state')}")
        return True
    logger.warning(f"Sell order returned None for {symbol}")
    return False


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _load_news_for_symbol(symbol: str, news_df: pd.DataFrame | None) -> dict:
    try:
        if news_df is not None and not news_df.empty:
            rows = news_df[news_df["symbol"] == symbol]["news"]
            if not rows.empty:
                return {symbol: rows.iloc[0] if len(rows) == 1 else rows.tolist()}
    except Exception as e:
        logger.debug(f"News load failed for {symbol}: {e}")
    return {}


def _build_stocks_data(candidates: pd.DataFrame, action: str) -> list[dict]:
    """
    Build the list consumed by get_batch_sentiment_recommendations.
    Both CSVs are loaded once and reused for all symbols.
    """
    try:
        agg_df = read_data_as_pd("agg_data")
    except Exception:
        agg_df = None
    try:
        news_df = read_data_as_pd("news")
    except Exception:
        news_df = None

    stocks_data = []
    for _, row in candidates.iterrows():
        symbol = row["symbol"]

        # Prefer agg_data CSV values; fall back to row values from the passed DataFrame
        if agg_df is not None and not agg_df.empty and "symbol" in agg_df.columns:
            agg_row = agg_df[agg_df["symbol"] == symbol]
            fundamentals = (
                {k: agg_row.iloc[0].get(k) for k in METRIC_KEYS}
                if not agg_row.empty
                else {k: row.get(k) for k in METRIC_KEYS}
            )
        else:
            fundamentals = {k: row.get(k) for k in METRIC_KEYS}

        stocks_data.append({
            "symbol":              symbol,
            "action":              action,
            "fundamental_metrics": fundamentals,
            "news_sentiment":      _load_news_for_symbol(symbol, news_df),
        })

    return stocks_data


# ---------------------------------------------------------------------------
# Portfolio risk controls
# ---------------------------------------------------------------------------

def get_portfolio_value() -> float:
    """Return total portfolio equity."""
    try:
        return float(rb.account.build_user_profile().get("equity", 0) or 0)
    except Exception as e:
        logger.warning(f"Could not fetch portfolio value: {e}")
        return 0.0


def get_current_positions() -> dict:
    """Return holdings dict {symbol: data}."""
    try:
        return rb.build_holdings() or {}
    except Exception as e:
        logger.warning(f"Could not fetch holdings: {e}")
        return {}


def get_position_value(symbol: str, holdings: dict) -> float:
    """Return current dollar value of a position."""
    try:
        return float(holdings.get(symbol, {}).get("equity", 0) or 0)
    except Exception:
        return 0.0


def get_sector_exposure(holdings: dict, agg_df: pd.DataFrame | None) -> dict[str, float]:
    """Return {sector: total_dollar_value} for all current holdings."""
    totals: dict[str, float] = {}
    for symbol, data in holdings.items():
        equity = safe_float(data.get("equity"), 0.0)
        sector = "Unknown"
        if agg_df is not None and not agg_df.empty and "symbol" in agg_df.columns:
            row = agg_df[agg_df["symbol"] == symbol]
            if not row.empty:
                sector = str(row.iloc[0].get("sector") or "Unknown")
        totals[sector] = totals.get(sector, 0.0) + equity
    return totals


def can_buy_symbol(
    symbol: str,
    allocation: float,
    holdings: dict,
    agg_df: pd.DataFrame | None,
    portfolio_value: float,
    available_cash: float,
) -> tuple[bool, str, float]:
    """
    Validate and adjust a proposed buy allocation against risk limits.
    Returns (approved, reason, adjusted_allocation).
    Reduces allocation to the maximum allowed rather than blocking outright when possible.
    """
    max_single    = RISK_LIMITS["max_single_position_pct"]
    max_sector    = RISK_LIMITS["max_sector_pct"]
    max_order_pct = RISK_LIMITS["max_order_pct_of_cash"]
    min_order     = RISK_LIMITS["min_order_amount"]
    min_volume    = RISK_LIMITS["min_liquidity_volume"]

    # Liquidity gate
    if agg_df is not None and not agg_df.empty and "symbol" in agg_df.columns:
        row = agg_df[agg_df["symbol"] == symbol]
        if not row.empty:
            vol = safe_float(row.iloc[0].get("volume"), 0.0)
            if vol < min_volume:
                return False, f"volume {vol:,.0f} < min {min_volume:,.0f}", 0.0

    # Order size cap (fraction of available cash)
    max_order = available_cash * max_order_pct
    if allocation > max_order:
        logger.info(
            f"{symbol}: order ${allocation:.2f} capped to {max_order_pct:.0%} of cash "
            f"(${available_cash:.2f}) = ${max_order:.2f}"
        )
        allocation = max_order

    # Single-position cap
    if portfolio_value > 0:
        current_pos = get_position_value(symbol, holdings)
        max_allowed = portfolio_value * max_single
        room = max_allowed - current_pos
        if room <= 0:
            return (
                False,
                f"position cap reached (${current_pos:.2f} / ${max_allowed:.2f})",
                0.0,
            )
        if allocation > room:
            logger.info(
                f"{symbol}: buy reduced ${allocation:.2f} → ${room:.2f} "
                f"(single-position cap {max_single:.0%} of ${portfolio_value:.2f})"
            )
            allocation = room

    # Sector cap
    if portfolio_value > 0 and agg_df is not None and not agg_df.empty:
        row = agg_df[agg_df["symbol"] == symbol]
        sector = str(row.iloc[0].get("sector") or "") if not row.empty else ""
        if sector:
            sector_exp     = get_sector_exposure(holdings, agg_df)
            current_sector = sector_exp.get(sector, 0.0)
            max_sector_val = portfolio_value * max_sector
            room = max_sector_val - current_sector
            if room <= 0:
                return (
                    False,
                    f"sector cap reached for {sector!r} "
                    f"(${current_sector:.2f} / ${max_sector_val:.2f})",
                    0.0,
                )
            if allocation > room:
                logger.info(
                    f"{symbol}: buy reduced ${allocation:.2f} → ${room:.2f} "
                    f"(sector {sector!r} cap {max_sector:.0%})"
                )
                allocation = room

    # Final minimum check — bump up to min_order if cash covers it
    if allocation < min_order:
        if available_cash >= min_order:
            logger.info(
                f"{symbol}: allocation ${allocation:.2f} below min — bumping to ${min_order:.2f}"
            )
            allocation = min_order
        else:
            return (
                False,
                f"allocation ${allocation:.2f} below min_order_amount ${min_order:.2f} "
                f"and cash ${available_cash:.2f} insufficient to cover minimum",
                0.0,
            )

    return True, "ok", allocation


# ---------------------------------------------------------------------------
# Sell decision engine
# ---------------------------------------------------------------------------

def evaluate_sell_candidate(
    symbol: str,
    holding: dict,
    metrics_row: "pd.Series | None",
) -> dict:
    """
    Evaluate a single holding for sell conditions.

    Returns:
        should_sell: bool
        reason: str
        severity: "hard" | "soft" | None
        percent_change: float | None   (decimal: -0.12 = -12%)
        value_metric: float | None
        quality_score: float | None
        yield_trap_flag: bool | None
    """
    # Derive percent_change — Robinhood returns it as a percentage string e.g. "-15.3"
    percent_change: float | None = None
    pct_raw = safe_float(holding.get("percent_change"))
    if pct_raw is not None:
        percent_change = pct_raw / 100.0

    # Fallback: compute from average_buy_price and current price
    if percent_change is None:
        avg   = safe_float(holding.get("average_buy_price"))
        price = safe_float(holding.get("price"))
        if avg and avg > 0 and price:
            percent_change = (price / avg) - 1.0

    # Extract metrics
    value_metric:   float | None = None
    quality_score:  float | None = None
    yield_trap_flag: bool | None = None

    if metrics_row is not None:
        value_metric  = safe_float(metrics_row.get("value_metric"))
        quality_score = safe_float(metrics_row.get("quality_score"))
        yt = metrics_row.get("yield_trap_flag")
        if yt is not None:
            try:
                yield_trap_flag = bool(yt) if not pd.isna(yt) else None
            except Exception:
                yield_trap_flag = None

    # Days held (best-effort — holding dict may not carry creation date)
    days_held: int | None = None
    try:
        created = holding.get("created_at") or holding.get("initiation_date")
        if created:
            created_dt = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
            days_held = (datetime.datetime.now(datetime.timezone.utc) - created_dt).days
    except Exception:
        pass

    stop_loss   = SELL_RULES["stop_loss_pct"]
    take_profit = SELL_RULES["take_profit_pct"]
    sell_weak   = SELL_RULES["sell_weak_value_below"]
    sell_yt     = SELL_RULES["sell_yield_trap"]
    sell_lq     = SELL_RULES["sell_low_quality_below"]
    min_days    = SELL_RULES["min_days_held_before_value_exit"]

    base = {
        "percent_change":  percent_change,
        "value_metric":    value_metric,
        "quality_score":   quality_score,
        "yield_trap_flag": yield_trap_flag,
    }

    # ── Hard sells ────────────────────────────────────────────────────────────

    if percent_change is not None and percent_change <= stop_loss:
        return {
            **base,
            "should_sell": True,
            "reason":   f"stop loss breached ({percent_change:.1%} ≤ {stop_loss:.1%})",
            "severity": "hard",
        }

    if sell_yt and yield_trap_flag and value_metric is not None and value_metric < sell_weak:
        return {
            **base,
            "should_sell": True,
            "reason":   f"yield trap with weak value_metric={value_metric:.3f} < {sell_weak}",
            "severity": "hard",
        }

    if quality_score is not None and quality_score < sell_lq:
        return {
            **base,
            "should_sell": True,
            "reason":   f"quality_score {quality_score:.3f} below floor {sell_lq}",
            "severity": "hard",
        }

    # ── Soft sells ────────────────────────────────────────────────────────────

    if percent_change is not None and percent_change >= take_profit:
        return {
            **base,
            "should_sell": True,
            "reason":   f"take profit triggered ({percent_change:.1%} ≥ {take_profit:.1%})",
            "severity": "soft",
        }

    if value_metric is not None and value_metric < sell_weak:
        if days_held is None or days_held >= min_days:
            days_str = f"{days_held}d" if days_held is not None else "unknown days"
            return {
                **base,
                "should_sell": True,
                "reason":   f"value_metric={value_metric:.3f} < {sell_weak} (held {days_str})",
                "severity": "soft",
            }

    return {
        **base,
        "should_sell": False,
        "reason":   "no sell condition met",
        "severity": None,
    }


# ---------------------------------------------------------------------------
# Sell cycle
# ---------------------------------------------------------------------------

def make_sales() -> list[str]:
    """
    Evaluate all non-ETF holdings for sell conditions.

    Hard sells (stop-loss, yield-trap, quality floor) execute immediately.
    Soft sells (take-profit, weak value) are optionally held by sentiment.
    Sentiment can only override soft sells — never hard sells.
    """
    sold: list[str] = []

    try:
        holdings = rb.build_holdings()
    except Exception as e:
        logger.error(f"Could not fetch holdings: {e}")
        return sold

    try:
        agg_df = read_data_as_pd("agg_data")
    except Exception:
        agg_df = None

    scanned    = 0
    hard_sells: dict[str, dict] = {}
    soft_sells: dict[str, dict] = {}

    for symbol, data in holdings.items():
        if symbol in ETFS:
            continue
        if float(data.get("quantity", 0)) <= 0:
            continue

        scanned += 1

        metrics_row = None
        if agg_df is not None and not agg_df.empty and "symbol" in agg_df.columns:
            row = agg_df[agg_df["symbol"] == symbol]
            if not row.empty:
                metrics_row = row.iloc[0]

        decision = evaluate_sell_candidate(symbol, data, metrics_row)

        if not decision["should_sell"]:
            continue

        if decision["severity"] == "hard":
            hard_sells[symbol] = decision
        else:
            soft_sells[symbol] = decision

    logger.info(
        f"Sell scan: {scanned} holdings scanned | "
        f"{len(hard_sells)} hard | {len(soft_sells)} soft | "
        f"{scanned - len(hard_sells) - len(soft_sells)} no-action"
    )

    # ── Execute hard sells ────────────────────────────────────────────────────
    for symbol, decision in hard_sells.items():
        pct = decision.get("percent_change")
        pct_str = f" | P/L={pct:.1%}" if pct is not None else ""
        logger.info(f"HARD SELL {symbol} | {decision['reason']}{pct_str}")
        quantity = float(holdings[symbol].get("quantity", 0))
        if _place_sell(symbol, quantity):
            sold.append(symbol)

    # ── Soft sells with optional sentiment override ───────────────────────────
    held_on_sentiment: set[str] = set()
    sentiment_results: dict[str, dict] = {}

    if soft_sells:
        if USE_SENTIMENT_ANALYSIS:
            soft_df = pd.DataFrame([
                {"symbol": sym, **{k: None for k in METRIC_KEYS}}
                for sym in soft_sells
            ])
            stocks_data = _build_stocks_data(soft_df, action="sell")
            try:
                sentiment_results = get_batch_sentiment_recommendations(stocks_data, action="sell")
            except Exception:
                logger.error("Batch sentiment failed for soft sells — executing all", exc_info=True)

            for sym, result in sentiment_results.items():
                if result["recommendation"] == "YES" and result["confidence"] >= CONFIDENCE_THRESHOLD:
                    logger.info(
                        f"HOLD {sym} — sentiment overrides soft sell "
                        f"({result['confidence']}%): {result['reasoning']}"
                    )
                    held_on_sentiment.add(sym)

        for symbol, decision in soft_sells.items():
            if symbol in held_on_sentiment:
                continue
            pct = decision.get("percent_change")
            pct_str = f" | P/L={pct:.1%}" if pct is not None else ""
            logger.info(f"SOFT SELL {symbol} | {decision['reason']}{pct_str}")
            quantity = float(holdings[symbol].get("quantity", 0))
            if _place_sell(symbol, quantity):
                sold.append(symbol)

    logger.info(
        f"Sell summary: {scanned} scanned | "
        f"{len(hard_sells)} hard | {len(soft_sells)} soft candidates | "
        f"{len(held_on_sentiment)} held on sentiment | "
        f"{len(sold)} executed | "
        f"{len(hard_sells) + len(soft_sells) - len(sold)} skipped/no-action"
    )
    return sold


# ---------------------------------------------------------------------------
# Buy cycle
# ---------------------------------------------------------------------------

def make_buys(df: pd.DataFrame, is_first_iteration: bool = True) -> tuple[list, list, list]:
    """
    Execute buy orders.
    Returns (purchased, skipped, failed).
    """
    total_cash   = get_available_cash()
    etf_amount   = total_cash * INDEX_PCT
    stock_amount = total_cash - etf_amount
    logger.info(f"Allocating ${etf_amount:.2f} to ETFs, ${stock_amount:.2f} to stocks")

    # ETF buys — first iteration only
    if is_first_iteration and etf_amount > 0 and (AUTO_APPROVE or confirm(f"Buy ETFs (${etf_amount:,.2f})?")):
        per_etf = etf_amount / max(len(ETFS), 1)
        for etf in ETFS:
            try:
                if AUTO_APPROVE or confirm(f"Buy ${per_etf:,.2f} of {etf}?"):
                    res = rb.orders.order_buy_fractional_by_price(etf, per_etf)
                    logger.info(f"ETF {etf}: {res.get('state') if res else 'None'}")
            except Exception as e:
                logger.error(f"ETF buy failed for {etf}: {e}")

    if df.empty or stock_amount <= 0:
        logger.warning("No stock picks or no funds for stocks")
        return [], [], []

    # Pre-filter by value_metric
    total_before = len(df)
    df["value_metric"] = pd.to_numeric(df["value_metric"], errors="coerce").fillna(0.0)

    logger.info(f"value_metric dtype: {df['value_metric'].dtype}")
    logger.info(f"value_metric max: {df['value_metric'].max()}")
    logger.info(
        "Top value_metric rows:\n%s",
        df[["symbol", "value_metric"]]
        .sort_values("value_metric", ascending=False)
        .head(10)
        .to_string(index=False)
    )
    candidates = df[df["value_metric"] >= METRIC_THRESHOLD].copy()
    logger.info(f"Pre-filter: {total_before} → {len(candidates)} stocks (value_metric ≥ {METRIC_THRESHOLD})")

    if candidates.empty:
        logger.warning(f"No stocks pass value_metric ≥ {METRIC_THRESHOLD}")
        return [], df["symbol"].tolist(), []

    # Load portfolio context once before the loop
    holdings        = get_current_positions()
    portfolio_value = get_portfolio_value()
    try:
        agg_df = read_data_as_pd("agg_data")
    except Exception:
        agg_df = None

    # Fast path — no sentiment
    if not USE_SENTIMENT_ANALYSIS:
        purchased, skipped, failed = [], [], []
        total_value = candidates["value_metric"].sum()
        for _, row in candidates.iterrows():
            symbol = row["symbol"]
            cash   = get_available_cash() * (1 - INDEX_PCT)
            if cash < RISK_LIMITS["min_order_amount"]:
                logger.info(f"Cash ${cash:.2f} below min order ${RISK_LIMITS['min_order_amount']:.2f} — exiting buy loop")
                break
            alloc = (row["value_metric"] / total_value) * cash if total_value else 0

            ok, reason, adj_alloc = can_buy_symbol(
                symbol, alloc, holdings, agg_df, portfolio_value, cash
            )
            if not ok:
                logger.info(f"Skipping {symbol}: {reason}")
                skipped.append(symbol)
                continue

            try:
                if AUTO_APPROVE or confirm(f"Buy ${adj_alloc:,.2f} of {symbol}?"):
                    if _place_buy(symbol, adj_alloc):
                        purchased.append(symbol)
                        time.sleep(0.5)
                    else:
                        failed.append(symbol)
            except Exception as e:
                logger.error(f"Order failed for {symbol}: {e}")
                failed.append(symbol)
        return purchased, skipped, failed

    # Batch sentiment analysis
    logger.info(f"Running batch sentiment on {len(candidates)} candidates...")
    stocks_data = _build_stocks_data(candidates, action="buy")
    try:
        sentiment_results = get_batch_sentiment_recommendations(stocks_data, action="buy")
    except Exception:
        logger.error("Batch sentiment failed — all candidates skipped", exc_info=True)
        return [], candidates["symbol"].tolist(), []

    purchased, skipped, failed = [], [], []
    total_value = candidates["value_metric"].sum()

    for _, row in candidates.iterrows():
        symbol = row["symbol"]
        result = sentiment_results.get(
            symbol,
            {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": "No result"},
        )

        logger.info(
            f"{'='*60}\nBUY {symbol} | {result['recommendation']} "
            f"{result['confidence']:.1f}% | {result['reasoning']}\n{'='*60}"
        )

        if result["recommendation"] == "NO" or result["confidence"] < CONFIDENCE_THRESHOLD:
            logger.info(f"Skipping {symbol}")
            skipped.append(symbol)
            continue

        cash = get_available_cash() * (1 - INDEX_PCT)
        if cash < RISK_LIMITS["min_order_amount"]:
            logger.info(f"Cash ${cash:.2f} below min order ${RISK_LIMITS['min_order_amount']:.2f} — exiting buy loop")
            break

        alloc = (row["value_metric"] / total_value) * cash if total_value else 0

        ok, reason, adj_alloc = can_buy_symbol(
            symbol, alloc, holdings, agg_df, portfolio_value, cash
        )
        if not ok:
            logger.info(f"Skipping {symbol}: {reason}")
            skipped.append(symbol)
            continue

        try:
            if AUTO_APPROVE or confirm(
                f"Buy ${adj_alloc:,.2f} of {symbol}? ({row['value_metric']/total_value:.1%})"
            ):
                if _place_buy(symbol, adj_alloc):
                    purchased.append(symbol)
                    time.sleep(0.5)
                else:
                    failed.append(symbol)
        except Exception as e:
            logger.error(f"Order failed for {symbol}: {e}")
            failed.append(symbol)

    logger.info(
        f"Buy summary: {len(purchased)} bought, {len(skipped)} skipped, {len(failed)} failed"
    )
    logger.info(f"Cash remaining: ${get_available_cash():,.2f}")
    return purchased, skipped, failed


# ---------------------------------------------------------------------------
# Strategy loop
# ---------------------------------------------------------------------------

def run_daily_strat() -> None:
    logger.info(f"=== Daily Investment Strategy {datetime.datetime.now():%Y-%m-%d %H:%M} ===")
    if USE_SENTIMENT_ANALYSIS:
        logger.info(f"Sentiment ON | METRIC_THRESHOLD={METRIC_THRESHOLD} | CONFIDENCE={CONFIDENCE_THRESHOLD}%")

    if not AUTO_APPROVE and not confirm("Generate new picks and run strategy?"):
        logger.info("Cancelled")
        return

    try:
        skip_data = "--skip-data" in sys.argv
        if not skip_data:
            update_industry_valuations(verbose=True)
            add_funds_to_account()
            refresh = AUTO_APPROVE or confirm("Generate fresh data? (takes several minutes)")
        else:
            logger.info("--skip-data: using existing CSVs")
            refresh = False

        df = generate_daily_undervalued_stocks(refresh=refresh)
    except Exception as e:
        logger.error(f"Strategy setup failed: {e}")
        if not AUTO_APPROVE:
            input("Press Enter to exit...")
        return

    permanently_skipped: set[str] = set()

    for iteration in range(1, 11):
        logger.info(f"\n{'='*60}\nITERATION {iteration}/10 | skipped so far: {len(permanently_skipped)}\n{'='*60}")

        if permanently_skipped:
            df = df[~df["symbol"].isin(permanently_skipped)].copy()

        if df.empty:
            logger.info("No remaining candidates — exiting")
            break

        cash = get_available_cash()
        if cash < RISK_LIMITS["min_order_amount"]:
            logger.info(f"Cash ${cash:.2f} below min order ${RISK_LIMITS['min_order_amount']:.2f} — skipping to sell phase")
            try:
                logger.info("=== SELL PHASE (cash exhausted) ===")
                make_sales()
            except Exception as e:
                logger.error(f"Sell phase error: {e}")
            break

        made_buys = made_sells = False

        try:
            logger.info("=== BUY PHASE ===")
            purchased, skipped, failed = make_buys(df, is_first_iteration=(iteration == 1))
            if purchased:
                made_buys = True
            permanently_skipped.update(skipped)
            permanently_skipped.update(failed)
        except Exception as e:
            logger.error(f"Buy phase error (iter {iteration}): {e}")

        try:
            logger.info("=== SELL PHASE ===")
            sold = make_sales()
            if sold:
                made_sells = True
        except Exception as e:
            logger.error(f"Sell phase error (iter {iteration}): {e}")

        if not made_buys and not made_sells:
            logger.info("No activity this iteration — exiting loop")
            break

    logger.info(
        f"\n{'='*60}\n"
        f"STRATEGY COMPLETE\n"
        f"Final cash: ${get_available_cash():,.2f}\n"
        f"Total skipped: {len(permanently_skipped)}\n"
        f"{'='*60}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python main.py [--skip-data] [--help]")
        print("  --skip-data   Reuse existing CSV files instead of regenerating")
        return

    login()
    run_daily_strat()


if __name__ == "__main__":
    main()
