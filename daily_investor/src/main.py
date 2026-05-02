"""
main.py — Daily investment strategy entry point.

Responsibilities:
  - Robinhood login
  - Fund top-up
  - Buy cycle: pre-filter → batch sentiment → execute orders
  - Sell cycle: threshold scan → batch sentiment hold-check → execute sells
  - Iteration loop until cash exhausted or no more candidates
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
    SELLOFF_THRESHOLD,
    USE_SENTIMENT_ANALYSIS,
    WEEKLY_INVESTMENT,
    read_data_as_pd,
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
# Sell cycle
# ---------------------------------------------------------------------------

def make_sales() -> list[str]:
    """
    Sell stocks whose price has moved beyond SELLOFF_THRESHOLD.
    Sentiment used only as a hold-check — not a proactive sweep.
    """
    sold: list[str] = []

    try:
        holdings = rb.build_holdings()
    except Exception as e:
        logger.error(f"Could not fetch holdings: {e}")
        return sold

    # Step 1 — find threshold-breaching positions (zero API calls)
    candidates: dict[str, dict] = {
        symbol: data
        for symbol, data in holdings.items()
        if symbol not in ETFS
        and float(data.get("quantity", 0)) > 0
        and abs(float(data.get("percent_change", 0))) > SELLOFF_THRESHOLD
    }

    if not candidates:
        logger.info("No stocks breach selloff threshold — nothing to sell")
        return sold

    logger.info(f"{len(candidates)} stock(s) breach threshold: {list(candidates)}")

    # Step 2 — batch sentiment hold-check
    holds: set[str] = set()
    sentiment_results: dict[str, dict] = {}

    if USE_SENTIMENT_ANALYSIS:
        candidates_df = pd.DataFrame([
            {"symbol": sym, **{k: None for k in METRIC_KEYS}}
            for sym in candidates
        ])
        stocks_data = _build_stocks_data(candidates_df, action="sell")
        try:
            sentiment_results = get_batch_sentiment_recommendations(stocks_data, action="sell")
        except Exception:
            logger.error("Batch sentiment failed for sell candidates — proceeding without", exc_info=True)

        for sym, result in sentiment_results.items():
            if result["recommendation"] == "YES" and result["confidence"] >= CONFIDENCE_THRESHOLD:
                pct = float(candidates[sym].get("percent_change", 0))
                logger.info(
                    f"HOLD {sym} — sentiment overrides {pct:.2f}% swing "
                    f"({result['confidence']}%): {result['reasoning']}"
                )
                holds.add(sym)

    # Step 3 — execute sells
    to_sell = {sym: data for sym, data in candidates.items() if sym not in holds}
    if not to_sell:
        logger.info("All candidates held on sentiment — nothing to sell")
        return sold

    for symbol, data in to_sell.items():
        quantity = float(data.get("quantity", 0))
        pct      = float(data.get("percent_change", 0))
        sentiment = sentiment_results.get(symbol, {})
        logger.info(
            f"SELL {symbol} | qty={quantity} | P/L={pct:.2f}% "
            f"| sentiment={sentiment.get('recommendation','N/A')} ({sentiment.get('confidence','N/A')}%)"
        )
        if _place_sell(symbol, quantity):
            sold.append(symbol)

    logger.info(f"Sales complete: {len(sold)} sold, {len(holds)} held on sentiment")
    return sold


# ---------------------------------------------------------------------------
# Buy cycle
# ---------------------------------------------------------------------------

def make_buys(df: pd.DataFrame, is_first_iteration: bool = True) -> tuple[list, list, list]:
    """
    Execute buy orders.
    Returns (purchased, skipped, failed).
    """
    total_cash  = get_available_cash()
    etf_amount  = total_cash * INDEX_PCT
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

    # Fast path — no sentiment
    if not USE_SENTIMENT_ANALYSIS:
        purchased, skipped, failed = [], [], []
        total_value = candidates["value_metric"].sum()
        for _, row in candidates.iterrows():
            symbol = row["symbol"]
            cash   = get_available_cash() * (1 - INDEX_PCT)
            if cash < 1.0:
                break
            alloc  = (row["value_metric"] / total_value) * cash if total_value else 0
            try:
                if AUTO_APPROVE or confirm(f"Buy ${alloc:,.2f} of {symbol}?"):
                    if _place_buy(symbol, alloc):
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

        # Re-fetch cash before every order — pending orders drain the balance in real time
        cash = get_available_cash() * (1 - INDEX_PCT)
        if cash < 1.0:
            logger.info("Cash exhausted — stopping buys")
            break

        alloc = (row["value_metric"] / total_value) * cash if total_value else 0
        if alloc < 0.01:
            logger.info(f"Allocation for {symbol} too small (${alloc:.4f}) — skipping")
            skipped.append(symbol)
            continue

        try:
            if AUTO_APPROVE or confirm(f"Buy ${alloc:,.2f} of {symbol}? ({row['value_metric']/total_value:.1%})"):
                if _place_buy(symbol, alloc):
                    purchased.append(symbol)
                    time.sleep(0.5)  # Robinhood order rate limit
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
        if cash < 1.0:
            logger.info("Cash exhausted — exiting")
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