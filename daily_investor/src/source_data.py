"""
source_data.py — Stock universe generation and fundamental data collection.

Key fixes vs original:
  - Removed dead get_reddit_data() and get_portfolio_data() stubs
  - Ticker validation now allows dots (BRK.B, BF.B) — was incorrectly using isalpha()
  - safe_float and DATA_DIRECTORY imported from util (no more duplication)
  - AGG_DATA_COLUMNS / METRIC_KEYS imported from util (single definition)
  - Reddit merge in get_data() removed — reddit data was never reliably populated
    and added unnecessary complexity; news is the active sentiment signal
"""

import os
import time

import pandas as pd
import requests
import robin_stocks.robinhood as rb
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from sentiments import get_news_for_tickers_by_symbol
from util import (
    AGG_DATA_COLUMNS,
    DATA_DIRECTORY,
    DIVIDEND_THRESHOLD,
    IGNORE_NEGATIVE_PB,
    IGNORE_NEGATIVE_PE,
    METRIC_KEYS,
    METRIC_THRESHOLD,
    get_investment_ratios,
    read_data_as_pd,
    safe_float,
    store_data_as_csv,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Stock universe
# ---------------------------------------------------------------------------

_INDEX_URLS = [
    "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "https://en.wikipedia.org/wiki/Nasdaq-100",
    "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
    "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "https://en.wikipedia.org/wiki/Russell_2000_Index",
]

_WIKI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
}

_ROBINHOOD_TAGS = [
    "100-most-popular",
    "upcoming-earnings",
    "new-on-robinhood",
    "technology",
    "finance",
    "healthcare",
    "energy",
]

_VALID_TICKER_RE = __import__("re").compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")


def _is_valid_ticker(symbol: str) -> bool:
    """Accept standard US equity tickers including dot-suffixed ones (BRK.B, BF.B)."""
    return bool(symbol and isinstance(symbol, str) and _VALID_TICKER_RE.match(symbol))


def _scrape_wikipedia_tickers(url: str) -> set[str]:
    try:
        resp = requests.get(url, headers=_WIKI_HEADERS, timeout=15)
        soup = BeautifulSoup(resp.content, "html.parser")
        table = soup.find("table", {"class": "wikitable sortable"})
        if not table:
            return set()
        symbols: set[str] = set()
        for row in table.find_all("tr")[1:]:
            for cell in row.find_all("td"):
                text = cell.text.strip()
                if _is_valid_ticker(text):
                    symbols.add(text)
        return symbols
    except Exception as e:
        print(f"Wikipedia scrape failed for {url}: {e}")
        return set()


def gen_symbols_list(force_refresh: bool = False) -> list[str]:
    if not force_refresh:
        cached = read_data_as_pd("stock_tickers")
        if cached is not None and not cached.empty and "symbol" in cached.columns:
            return cached["symbol"].tolist()

    # Wikipedia indices
    all_symbols: set[str] = set()
    for url in _INDEX_URLS:
        print(f"Scraping {url}")
        all_symbols.update(_scrape_wikipedia_tickers(url))

    # Robinhood sources
    rb_sources = [
        rb.get_top_movers_sp500("down"),
        rb.get_top_movers(),
        rb.get_top_100(),
        rb.get_top_movers_sp500("up"),
    ]
    for tag in _ROBINHOOD_TAGS:
        try:
            stocks = rb.get_all_stocks_from_market_tag(tag)
            if stocks:
                rb_sources.append(stocks)
                print(f"  Tag '{tag}': {len(stocks)} stocks")
            time.sleep(0.5)
        except Exception as e:
            print(f"  Tag '{tag}' failed: {str(e)[:50]}")

    invalid = 0
    for source in rb_sources:
        for item in (source or []):
            sym = item.get("symbol", "")
            if _is_valid_ticker(sym):
                all_symbols.add(sym)
            else:
                invalid += 1

    print(f"Universe: {len(all_symbols)} valid tickers ({invalid} invalid skipped)")
    store_data_as_csv("stock_tickers", ["symbol"], [[s] for s in sorted(all_symbols)])
    return sorted(all_symbols)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _dividend_income_score(dividend_yield: float) -> tuple[float, bool]:
    """Return (income_score, yield_trap_flag)."""
    if not dividend_yield or dividend_yield <= 0:
        return 0.0, False
    if dividend_yield >= 0.10:          # Suspiciously high — probable trap
        return 0.0, True
    if dividend_yield >= DIVIDEND_THRESHOLD:
        return min(dividend_yield / DIVIDEND_THRESHOLD, 1.5), False
    return 0.0, False


def _quality_score(
    pe_ratio: float | None,
    pb_ratio: float | None,
    volume: float,
    dividend_yield: float,
) -> float:
    score = 0.0
    if pe_ratio is not None and pe_ratio > 0:
        score += 0.5
    if pe_ratio is not None and 0 < pe_ratio < 5:   # Distress signal
        score -= 0.4
    if pb_ratio is not None and pb_ratio > 0:
        score += 0.2
    if volume >= 1_000_000:
        score += 0.3
    elif volume < 100_000:
        score -= 0.3
    if dividend_yield >= 0.10:
        score -= 0.6
    elif 0.02 <= dividend_yield <= 0.06:
        score += 0.2
    return round(score, 3)


def _get_buy_to_sell_ratio(symbol: str) -> float | None:
    try:
        ratings = rb.stocks.get_ratings(symbol)
        if not isinstance(ratings, dict):
            return None
        summary = ratings.get("summary") or {}
        buys = summary.get("num_buy_ratings") or 0
        sells = summary.get("num_sell_ratings") or 0
        return buys / (sells or 1)
    except Exception as e:
        if "404" not in str(e) and "None" not in str(e):
            print(f"Ratings fetch failed for {symbol}: {str(e)[:50]}")
        return None


def _evaluate_stock(symbol: str, stock: dict) -> list | None:
    """Compute all metric columns for one stock. Returns None if stock is unscoreable."""
    if not isinstance(stock, dict):
        return None

    required = ["industry", "sector", "volume", "pe_ratio", "pb_ratio"]
    if not all(k in stock for k in required):
        return None
    if not stock.get("industry") and not stock.get("sector"):
        return None

    volume = safe_float(stock.get("volume"), 0)
    if not volume:
        return None

    pe_ratio = safe_float(stock.get("pe_ratio"))
    pb_ratio = safe_float(stock.get("pb_ratio"))
    dividend_yield_raw = safe_float(stock.get("dividend_yield"), 0.0)
    dividend_yield = dividend_yield_raw / 100 if dividend_yield_raw else 0.0

    if pe_ratio is not None and pe_ratio < 0 and IGNORE_NEGATIVE_PE:
        return None
    if pb_ratio is not None and pb_ratio < 0 and IGNORE_NEGATIVE_PB:
        return None

    pe_threshold, pb_threshold = get_investment_ratios(stock.get("sector"), stock.get("industry"))

    pe_comp = pe_threshold / pe_ratio if pe_ratio and 0 < pe_ratio < pe_threshold else 0.0
    pb_comp = pb_threshold / pb_ratio if pb_ratio and 0 < pb_ratio < pb_threshold else 0.0

    value_score = round(0.6 * pe_comp + 0.4 * pb_comp, 3)
    income_score, yield_trap_flag = _dividend_income_score(dividend_yield)
    quality = _quality_score(pe_ratio, pb_ratio, volume, dividend_yield)
    final_metric = round(0.50 * value_score + 0.30 * quality + 0.20 * income_score, 3)
    buy_to_sell = _get_buy_to_sell_ratio(symbol)

    return [
        stock.get("industry"),
        stock.get("sector"),
        volume,
        pe_ratio,
        pb_ratio,
        dividend_yield,
        pe_comp,
        pb_comp,
        value_score,
        income_score,
        quality,
        yield_trap_flag,
        final_metric,
        buy_to_sell,
    ]


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _get_robinhood_fundamentals(tickers: list[str], force_refresh: bool) -> pd.DataFrame | None:
    if not force_refresh:
        return read_data_as_pd("robinhood_data")

    batch_size = 50
    fundamentals: dict[str, dict] = {}

    print(f"Fetching fundamentals for {len(tickers)} stocks in batches of {batch_size}...")
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i: i + batch_size]
        batch_num = i // batch_size + 1
        total = (len(tickers) + batch_size - 1) // batch_size
        try:
            print(f"Batch {batch_num}/{total} ({len(batch)} stocks)...")
            result = rb.get_fundamentals(batch)
            if result and isinstance(result, list):
                for item in result:
                    if item and isinstance(item, dict) and "symbol" in item:
                        fundamentals[item["symbol"]] = item
        except Exception as e:
            print(f"Batch {batch_num} failed: {str(e)[:60]}")

    print(f"Fetched fundamentals for {len(fundamentals)} stocks")

    rows = []
    for symbol, data in fundamentals.items():
        metrics = _evaluate_stock(symbol, data)
        if metrics:
            rows.append([symbol] + metrics)

    store_data_as_csv("robinhood_data", AGG_DATA_COLUMNS, rows)
    time.sleep(1)
    return read_data_as_pd("robinhood_data")


def _get_news(tickers: list[str], force_refresh: bool) -> pd.DataFrame | None:
    if not force_refresh:
        return read_data_as_pd("news")

    # Only fetch news for liquid stocks (volume already in robinhood_data)
    rb_data = read_data_as_pd("robinhood_data")
    if rb_data is not None and not rb_data.empty and "volume" in rb_data.columns:
        liquid = rb_data[rb_data["volume"] >= 500_000]["symbol"].tolist()
        print(f"News filter: {len(tickers)} total → {len(liquid)} liquid tickers")
    else:
        liquid = tickers

    news_by_symbol = get_news_for_tickers_by_symbol(liquid, max_articles=3)

    # Ensure every ticker has an entry (empty list for low-volume ones)
    for t in tickers:
        news_by_symbol.setdefault(t, [])

    news_df = pd.DataFrame([
        {"symbol": sym, "news": articles}
        for sym, articles in news_by_symbol.items()
    ])
    store_data_as_csv("news", ["symbol", "news"], news_df)
    return read_data_as_pd("news")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_data(refresh: bool = False) -> pd.DataFrame:
    tickers = gen_symbols_list(refresh)
    metrics = _get_robinhood_fundamentals(tickers, refresh)
    news_df = _get_news(tickers, refresh)

    if metrics is None or metrics.empty:
        print("Warning: No fundamental data available")
        return pd.DataFrame()

    result = metrics if news_df is None or news_df.empty else metrics.merge(news_df, on="symbol", how="left")

    if refresh and not result.empty:
        store_data_as_csv("agg_data", "", result)
        time.sleep(1)

    agg = read_data_as_pd("agg_data")
    return agg if agg is not None else result


if __name__ == "__main__":
    df = get_data(refresh=False)
    print(df)