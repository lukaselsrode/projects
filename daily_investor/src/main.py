import os
import sys
import time
import datetime
import logging
import pyotp
import pandas as pd
import robin_stocks.robinhood as rb
from dotenv import load_dotenv

from source_data import get_data as generate_daily_undervalued_stocks
from sentiments import get_news_for_tickers_by_symbol, reddit_sentiments_for_tickers
from sentiment_analysis import (
    get_sentiment_recommendation,
    get_batch_sentiment_recommendations,
)
from util import (
    update_industry_valuations,
    read_data_as_pd,
    SELLOFF_THRESHOLD,
    WEEKLY_INVESTMENT,
    AUTO_APPROVE,
    ETFS,
    INDEX_PCT,
    USE_SENTIMENT_ANALYSIS,
    CONFIDENCE_THRESHOLD,
    METRIC_THRESHOLD,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('investment_bot.log')
    ]
)
logger = logging.getLogger("investment_bot")

load_dotenv()

DATA_DIRECTORY = os.path.join("/".join(os.path.abspath(__file__).split("/")[:-2]), "data")

global CASH_AVAILABLE


# ==================== HELPER FUNCTIONS ====================

def login():
    username = os.getenv("RB_ACCT")
    password = os.getenv("RB_CREDS")

    if not username or not password:
        error_msg = ("\n" + "="*50 + "\n"
                    "ERROR: Missing required environment variables\n"
                    "Please set the following environment variables:\n"
                    "- RB_ACCT: Your Robinhood username/email\n"
                    "- RB_CREDS: Your Robinhood password\n"
                    "\nOptional (for automatic MFA):\n"
                    "- RB_MFA_SECRET: Your MFA secret for TOTP generation\n"
                    "="*50 + "\n")
        logger.error(error_msg)
        raise ValueError("Missing required environment variables")

    mfa_secret = os.getenv("RB_MFA_SECRET")
    mfa_code = None

    if mfa_secret:
        logger.info("Using MFA secret from environment variable")
        try:
            mfa_code = pyotp.TOTP(mfa_secret).now()
            logger.info(f"Generated MFA code: {mfa_code}")
        except Exception as e:
            logger.error(f"Error generating MFA code: {e}")

    try:
        logger.info("Attempting to log in...")
        rb.login(username=username, password=password, mfa_code=mfa_code, store_session=True)
        logger.info("Successfully logged in!")
    except Exception as e:
        logger.error(f"Login failed: {e}")
        if "mfa_required" in str(e).lower() and not mfa_code:
            mfa_code = input("Enter MFA code: ").strip()
            rb.login(username=username, password=password, mfa_code=mfa_code, store_session=True)
            logger.info("Successfully logged in with MFA code!")
        else:
            raise


def confirm(prompt: str) -> bool:
    if AUTO_APPROVE:
        logger.info(f"AUTO-APPROVED: {prompt}")
        return True
    response = input(f"{prompt} [y/n] ").strip().lower()
    return response in ('y', 'yes')


def add_funds_to_account() -> None:
    if get_available_cash() < float(WEEKLY_INVESTMENT):
        available_cash = get_available_cash()
        amount_needed = float(WEEKLY_INVESTMENT) - available_cash
        if confirm(f"Not Enough Cash Available: ${available_cash:,.2f} < ${float(WEEKLY_INVESTMENT):,.2f}\nAdd ${amount_needed:,.2f} to reach weekly investment target?"):
            try:
                bank_accounts = rb.get_linked_bank_accounts()
                if not bank_accounts:
                    logger.warning("No linked bank accounts found. Cannot add funds.")
                    return
                ach = bank_accounts[0].get('url')
                if not ach:
                    logger.warning("No ACH URL found in first bank account. Cannot add funds.")
                    return
                resp = rb.deposit_funds_to_robinhood_account(ach, round(amount_needed, 2))
                logger.info(f"Deposit response: {resp}")
                logger.info(f"Request To Deposit ${amount_needed:,.2f} : {resp.get('state')}")
            except Exception as e:
                logger.error(f"Failed to add funds: {e}")
    else:
        logger.info(f"Not Adding Funds: Enough cash available ({get_available_cash()} > {WEEKLY_INVESTMENT})")


def sell(symbol: str, quantity: float):
    if not AUTO_APPROVE and not confirm(f"Confirm sell order for {quantity} shares of {symbol}?"):
        logger.info(f"Cancelled sell order for {symbol}")
        return None
    return rb.order_sell_market(symbol, quantity)


def make_sales() -> list:
    """Execute sell orders. Returns list of sold symbols.

    Flow:
      1. Scan holdings for threshold breaches — O(n) with zero API calls.
      2. If sentiment is enabled, batch all candidates in one async round-trip
         and use the results as a hold-check (YES + high confidence → keep).
      3. Execute sell orders for confirmed candidates.
    """
    sold_symbols = []
    try:
        holdings = rb.build_holdings()
    except Exception as e:
        logger.error(f"Failed to fetch holdings for sales: {e}")
        return sold_symbols

    # --- Step 1: identify threshold-breaching candidates (no API calls yet) ---
    candidates: dict[str, dict] = {}   # symbol → holdings data
    for symbol, data in holdings.items():
        if symbol in ETFS:
            continue
        quantity = float(data.get('quantity', 0))
        if quantity <= 0:
            continue
        percent_change = float(data.get("percent_change", 0))
        if abs(percent_change) > SELLOFF_THRESHOLD:
            candidates[symbol] = data

    if not candidates:
        logger.info("No stocks meet selloff threshold — nothing to sell")
        return sold_symbols

    logger.info(f"{len(candidates)} stock(s) breach selloff threshold: {list(candidates)}")

    # --- Step 2: batch sentiment hold-check (single async round-trip) ---
    holds: set[str] = set()
    sentiment_results: dict[str, dict] = {}

    if USE_SENTIMENT_ANALYSIS:
        # Build a minimal DataFrame from candidates dict so _build_stocks_data can be reused
        candidates_df = pd.DataFrame([
            {"symbol": sym, **{k: None for k in ['pe_ratio', 'pb_ratio', 'dividend_yield',
                                                   'volume', 'pe_comp', 'pb_comp', 'div_comp',
                                                   'value_metric', 'buy_to_sell_ratio',
                                                   'industry', 'sector']}}
            for sym in candidates
        ])
        stocks_data = _build_stocks_data(candidates_df, action="sell")
        try:
            sentiment_results = get_batch_sentiment_recommendations(stocks_data, action="sell")
        except Exception as e:
            logger.error(f"Batch sentiment failed for sell candidates — proceeding without sentiment", exc_info=True)

        for sym, result in sentiment_results.items():
            if (result["recommendation"] == "YES" and
                    result["confidence"] >= CONFIDENCE_THRESHOLD):
                pct = float(candidates[sym].get("percent_change", 0))
                logger.info(
                    f"HOLD {sym} — positive sentiment overrides {pct:.2f}% swing "
                    f"(confidence {result['confidence']}%): {result['reasoning']}"
                )
                holds.add(sym)

    # --- Step 3: execute sells for non-held candidates ---
    to_sell = {sym: data for sym, data in candidates.items() if sym not in holds}

    if not to_sell:
        logger.info("All threshold-breaching stocks held on sentiment — nothing to sell")
        return sold_symbols

    logger.info(f"Executing sell orders for {len(to_sell)} stock(s)")

    for symbol, data in to_sell.items():
        quantity = float(data.get('quantity', 0))
        if quantity <= 0:
            continue

        pct = float(data.get("percent_change", 0))
        sentiment = sentiment_results.get(symbol, {})
        reason = (
            f"Price change ({pct:.2f}%) exceeds threshold ({SELLOFF_THRESHOLD}%)"
            + (f". Sentiment: {sentiment.get('recommendation')} ({sentiment.get('confidence')}%)"
               if sentiment else "")
        )

        logger.info(f"\n{'='*50}")
        logger.info(f"SELLING {symbol}")
        logger.info(f"  Qty        : {quantity}")
        logger.info(f"  Price      : ${float(data.get('last_trade_price', 0)):.2f}")
        logger.info(f"  Avg cost   : ${float(data.get('average_buy_price', 0)):.2f}")
        logger.info(f"  P/L        : {pct:.2f}%")
        logger.info(f"  Reason     : {reason}")

        try:
            res = sell(symbol, quantity)
            if res:
                logger.info(f"Sold {quantity} shares of {symbol}  |  state={res.get('state')}")
                sold_symbols.append(symbol)
            else:
                logger.warning(f"Sell order returned None for {symbol}")
        except Exception as e:
            logger.error(f"Sell order failed for {symbol}: {e}")

    logger.info(f"Sales complete: {len(sold_symbols)} sold, {len(holds)} held on sentiment")
    return sold_symbols


# ==================== BUY HELPERS ====================

def _load_news_for_symbol(symbol: str, news_df: pd.DataFrame | None = None) -> dict:
    """Return cached news dict for symbol. Accepts a pre-loaded DataFrame to avoid repeated I/O."""
    try:
        if news_df is None:
            news_df = read_data_as_pd('news')
        if news_df is not None and not news_df.empty:
            symbol_news = news_df[news_df['symbol'] == symbol]['news']
            if not symbol_news.empty:
                return {symbol: symbol_news.iloc[0] if len(symbol_news) == 1 else symbol_news.tolist()}
    except Exception as e:
        logger.debug(f"Could not load news for {symbol}: {e}")
    return {}


def _build_stocks_data(candidates: pd.DataFrame, action: str = "buy") -> list[dict]:
    """
    Build the list of stock dicts consumed by get_batch_sentiment_recommendations.
    Both CSVs are loaded once and reused across all symbols.
    """
    # Load both CSVs once
    try:
        agg_df = read_data_as_pd('agg_data')
    except Exception:
        agg_df = None
    try:
        news_df = read_data_as_pd('news')
    except Exception:
        news_df = None

    metric_keys = ['pe_ratio', 'pb_ratio', 'dividend_yield', 'volume',
                   'pe_comp', 'pb_comp', 'div_comp', 'value_metric',
                   'buy_to_sell_ratio', 'industry', 'sector']

    stocks_data = []
    for _, row in candidates.iterrows():
        symbol = row['symbol']

        if agg_df is not None and not agg_df.empty:
            agg_row = agg_df[agg_df['symbol'] == symbol]
            if not agg_row.empty:
                r = agg_row.iloc[0]
                fundamentals = {k: r.get(k) for k in metric_keys}
            else:
                fundamentals = {k: row.get(k) for k in metric_keys}
        else:
            fundamentals = {k: row.get(k) for k in metric_keys}

        stocks_data.append({
            "symbol": symbol,
            "action": action,
            "fundamental_metrics": fundamentals,
            "news_sentiment": _load_news_for_symbol(symbol, news_df),
        })

    return stocks_data


def make_buys(df: pd.DataFrame, is_first_iteration: bool = True) -> tuple:
    """Execute buy orders with batch sentiment analysis. Returns (purchased, skipped, failed)."""
    total_cash = get_available_cash()
    etf_amount = total_cash * INDEX_PCT
    stock_amount = total_cash - etf_amount
    logger.info(f"Allocating ${etf_amount:.2f} to ETFs, ${stock_amount:.2f} to picked stocks")

    # ----- ETF buys (first iteration only) -----
    def make_etf_buys(amount: float):
        if amount <= 0:
            return
        etf_count = len(ETFS)
        if etf_count == 0:
            logger.warning("No ETFs configured")
            return
        per_etf = amount / etf_count
        for etf in ETFS:
            try:
                if AUTO_APPROVE or confirm(f'Buy ${per_etf:,.2f} of {etf}?'):
                    res = rb.orders.order_buy_fractional_by_price(etf, per_etf)
                    logger.info(f"ETF order {etf}: {res.get('state') if res else 'None'}")
            except Exception as e:
                logger.error(f"Failed to buy ETF {etf}: {e}")

    if is_first_iteration and etf_amount > 0 and (AUTO_APPROVE or confirm(f'Buy ETFs (${etf_amount:,.2f})?')):
        make_etf_buys(etf_amount)

    if df.empty or stock_amount <= 0:
        logger.warning("No stock picks available or no funds allocated to stocks")
        return [], [], []

    # ----- Pre-filter by value_metric -----
    total_before = len(df)
    candidates = df[df['value_metric'] >= METRIC_THRESHOLD].copy()
    logger.info(
        f"Pre-filter: {total_before} → {len(candidates)} stocks with value_metric >= {METRIC_THRESHOLD}"
    )

    if candidates.empty:
        logger.warning(f"No stocks pass value_metric >= {METRIC_THRESHOLD}. Nothing to buy.")
        return [], list(df['symbol']), []

    if not USE_SENTIMENT_ANALYSIS:
        # Fast path — no sentiment, just buy by weight
        purchased_stocks, skipped_stocks, failed_stocks = [], [], []
        total_value = candidates['value_metric'].sum()
        remaining = stock_amount
        for _, row in candidates.iterrows():
            symbol = row['symbol']
            allocation = (row['value_metric'] / total_value) * remaining if total_value > 0 else 0
            try:
                if AUTO_APPROVE or confirm(f'Buy ${allocation:,.2f} of {symbol}?'):
                    res = rb.orders.order_buy_fractional_by_price(symbol, allocation)
                    if res is None:
                        failed_stocks.append(symbol)
                    else:
                        logger.info(f"Order {symbol}: {res.get('state')}")
                        purchased_stocks.append(symbol)
                        remaining -= allocation
            except Exception as e:
                logger.error(f"Order failed for {symbol}: {e}")
                failed_stocks.append(symbol)
        return purchased_stocks, skipped_stocks, failed_stocks

    # ----- Batch sentiment analysis (single API round-trip per BATCH_SIZE stocks) -----
    logger.info(f"Running batch sentiment analysis on {len(candidates)} candidates...")
    stocks_data = _build_stocks_data(candidates, action="buy")

    try:
        sentiment_results = get_batch_sentiment_recommendations(stocks_data, action="buy")
    except Exception as e:
        logger.error(f"Batch sentiment analysis failed — all candidates will be skipped", exc_info=True)
        sentiment_results = {
            row['symbol']: {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": "Batch error"}
            for _, row in candidates.iterrows()
        }

    # ----- Execute orders based on batch results -----
    purchased_stocks, skipped_stocks, failed_stocks = [], [], []
    total_value = candidates['value_metric'].sum()

    for _, row in candidates.iterrows():
        symbol = row['symbol']
        sentiment_result = sentiment_results.get(
            symbol,
            {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": "No result returned"}
        )

        logger.info(f"{'='*60}")
        logger.info(f"BUY DECISION: {symbol}")
        logger.info(f"  Recommendation : {sentiment_result['recommendation']}")
        logger.info(f"  Confidence     : {sentiment_result['confidence']:.1f}%")
        logger.info(f"  Reasoning      : {sentiment_result['reasoning']}")
        logger.info(f"{'='*60}")

        # Skip on low-confidence or explicit NO
        if (sentiment_result['confidence'] < CONFIDENCE_THRESHOLD or
                sentiment_result['recommendation'] == "NO"):
            logger.info(f"Skipping {symbol} (recommendation={sentiment_result['recommendation']}, "
                        f"confidence={sentiment_result['confidence']:.1f}%)")
            skipped_stocks.append(symbol)
            continue

        # Re-fetch real available cash before every order — catches pending orders draining balance
        remaining_stock_amount = get_available_cash() * (1 - INDEX_PCT)
        if remaining_stock_amount < 1.0:
            logger.info(f"Cash exhausted (${remaining_stock_amount:.2f} remaining after ETF reserve) — stopping buys")
            break

        allocation = (row['value_metric'] / total_value) * remaining_stock_amount if total_value > 0 else 0
        if allocation < 0.01:
            logger.info(f"Allocation for {symbol} too small (${allocation:.4f}) — skipping")
            skipped_stocks.append(symbol)
            continue

        try:
            if AUTO_APPROVE or confirm(
                f'Buy ${allocation:,.2f} of {symbol}? (Weight: {row["value_metric"]/total_value:.1%})'
            ):
                res = rb.orders.order_buy_fractional_by_price(symbol, allocation)
                if res is None:
                    # Fractional shares not available — fall back to 1 whole share
                    logger.warning(f"{symbol}: fractional order unavailable, retrying as market order (qty=1)")
                    try:
                        res = rb.orders.order_buy_market(symbol, 1)
                    except Exception as fallback_exc:
                        logger.error(f"{symbol}: market order fallback also failed: {fallback_exc}")
                        res = None

                if res is None:
                    logger.warning(f"Both order attempts failed for {symbol} — skipping")
                    failed_stocks.append(symbol)
                else:
                    logger.info(f"Order {symbol}: {res.get('state')}")
                    purchased_stocks.append(symbol)
                    time.sleep(0.5)   # brief pause — Robinhood order API rate limit
        except Exception as e:
            logger.error(f"Order failed for {symbol}: {e}")
            failed_stocks.append(symbol)

    logger.info(
        f"Purchase summary: {len(purchased_stocks)} bought, "
        f"{len(skipped_stocks)} skipped, {len(failed_stocks)} failed"
    )
    logger.info(f"Remaining cash: ${get_available_cash():,.2f}")
    return purchased_stocks, skipped_stocks, failed_stocks


def wipe_data():
    if confirm('Wipe Data Directory?'):
        for f in os.listdir(DATA_DIRECTORY):
            fname = '/'.join([DATA_DIRECTORY, f])
            try:
                os.remove(fname)
                logger.debug(f'Removed file: {fname}')
            except Exception as e:
                logger.error(f'Error removing file {fname}: {e}')
        logger.info('Data Directory Cleared')


def update_valuations():
    update_industry_valuations(verbose=True)


def run_daily_strat():
    date = datetime.datetime.now()
    logger.info(f'Running Automated Investment Strategy for {date}')

    if USE_SENTIMENT_ANALYSIS:
        logger.info("="*60)
        logger.info(f"SENTIMENT ANALYSIS ENABLED  |  METRIC_THRESHOLD={METRIC_THRESHOLD}  |  CONFIDENCE_THRESHOLD={CONFIDENCE_THRESHOLD}")
        logger.info("="*60)

    if not AUTO_APPROVE and not confirm("Wipe data directory and generate new picks?"):
        logger.info("Operation cancelled by user")
        return

    try:
        skip_data_gen = '--skip-data' in sys.argv
        if not skip_data_gen:
            update_valuations()
            add_funds_to_account()
            generate_fresh = AUTO_APPROVE or confirm("Generate fresh data and news? This may take several minutes...")
        else:
            logger.info("Skipping data generation (using existing CSV files)")
            generate_fresh = False

        df = generate_daily_undervalued_stocks(refresh=generate_fresh)
    except Exception as e:
        logger.error(f"Error in strategy setup: {e}")
        if not AUTO_APPROVE:
            input("Press Enter to exit...")
        return

    permanently_skipped: set = set()
    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        logger.info(f"\n{'='*60}")
        logger.info(f"STRATEGY ITERATION {iteration}/{max_iterations}")
        logger.info(f"Permanently skipped so far: {sorted(permanently_skipped)}")
        logger.info(f"{'='*60}\n")

        if permanently_skipped:
            df = df[~df['symbol'].isin(permanently_skipped)].copy()

        if df.empty:
            logger.info("No remaining stocks to analyze. Exiting loop.")
            break

        cash = get_available_cash()
        logger.info(f"Available cash at iteration start: ${cash:,.2f}")
        if cash < 1.0:
            logger.info("Cash exhausted. Exiting loop.")
            break

        made_buys = made_sells = False

        # BUY PHASE
        try:
            logger.info("=== STARTING BUY ANALYSIS ===")
            purchased, skipped, failed = make_buys(df, is_first_iteration=(iteration == 1))
            logger.info("=== BUY ANALYSIS COMPLETE ===")
            if purchased:
                made_buys = True
            permanently_skipped.update(skipped)
            permanently_skipped.update(failed)
        except Exception as e:
            logger.error(f"Error in buy analysis (iteration {iteration}): {e}")

        # SELL PHASE
        try:
            logger.info("=== STARTING SALES ANALYSIS ===")
            sold = make_sales()
            logger.info("=== SALES ANALYSIS COMPLETE ===")
            if sold:
                made_sells = True
        except Exception as e:
            logger.error(f"Error in sales analysis (iteration {iteration}): {e}")

        if not made_buys and not made_sells:
            logger.info(f"No buys or sells in iteration {iteration}. Exiting loop.")
            break

    logger.info(f"\n{'='*60}")
    logger.info(f"STRATEGY COMPLETE: {iteration} iteration(s)")
    logger.info(f"Permanently skipped: {sorted(permanently_skipped)}")
    logger.info(f"Final available cash: ${get_available_cash():,.2f}")
    logger.info(f"{'='*60}\n")


def get_available_cash() -> float:
    cash = float(rb.account.build_user_profile().get('cash', 0))

    try:
        open_orders = rb.orders.get_all_open_stock_orders()
        committed_cash = 0.0

        def process_market_order(order):
            for field, subfield in [('executed_notional', 'amount'), ('total_notional', 'amount'), ('dollar_based_amount', 'amount')]:
                if order.get(field) and order[field].get(subfield):
                    return float(order[field][subfield])
            return 0.0

        def process_limit_order(order):
            return float(order.get('quantity', 0)) * float(order.get('price', 0))

        order_processors = {'market': process_market_order, 'limit': process_limit_order}

        for order in open_orders:
            if order.get('side') != 'buy' or order.get('state') not in ['confirmed', 'queued', 'unconfirmed']:
                continue
            order_type = order.get('type')
            if order_type == 'market' and order.get('extended_hours', False):
                continue
            processor = order_processors.get(order_type)
            if processor:
                committed_cash += processor(order)

        available_cash = cash - committed_cash

    except Exception as e:
        logger.warning(f"Could not fetch pending orders. Using full cash balance. Error: {e}")
        available_cash = cash

    logger.info(f"Available cash: ${available_cash:,.2f} (Total: ${cash:,.2f}, Pending: ${(cash - available_cash):,.2f})")
    return max(0, available_cash)


def main():
    global CASH_AVAILABLE

    if '--help' in sys.argv or '-h' in sys.argv:
        print("Usage: python main.py [options]")
        print("Options:")
        print("  --skip-data    Skip data generation and use existing CSV files")
        print("  --help, -h     Show this help message")
        return

    login()
    CASH_AVAILABLE = get_available_cash()
    run_daily_strat()


if __name__ == "__main__":
    main()