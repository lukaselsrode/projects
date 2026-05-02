"""
sentiments.py — News and Reddit sentiment data collection.

Key fixes vs original:
  - News processing loop bug fixed (items were processed outside the ticker loop)
  - Retry/backoff extracted into _fetch_news_with_retry — was copy-pasted 4×
  - Volume pre-filter removed (agg_data CSV already screens by volume upstream)
  - Robinhood login check simplified to a single try/except on the real call
  - reddit_sentiments_for_tickers kept unchanged (was already clean)
"""

import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import robin_stocks.robinhood as rb
import yfinance as yf


# ---------------------------------------------------------------------------
# Reddit sentiment
# ---------------------------------------------------------------------------

async def _fetch_reddit_date(session: aiohttp.ClientSession, date: str) -> tuple[str, Any]:
    try:
        async with session.get(f"https://api.tradestie.com/v1/apps/reddit?date={date}") as r:
            r.raise_for_status()
            return date, await r.json()
    except Exception as e:
        print(f"Reddit fetch error for {date}: {e}")
        return date, None


async def _get_reddit_sentiments_async(days: int = 7) -> dict:
    dates = [
        (datetime.now() - timedelta(days=i)).strftime("%m-%d-%Y")
        for i in range(min(days, 7))
    ]
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[_fetch_reddit_date(session, d) for d in dates])
    return dict(results)


def reddit_sentiments_for_tickers(tickers: list[str], days: int = 7) -> dict:
    """Return {date: [ticker_data]} for the given tickers, deduplicated per day."""
    ticker_set = set(tickers)
    raw = asyncio.run(_get_reddit_sentiments_async(days))
    rv: dict[str, list] = {}
    for day, sentiment_list in raw.items():
        if not sentiment_list:
            continue
        seen: set[str] = set()
        for item in sentiment_list:
            ticker = item.get("ticker")
            if ticker in ticker_set and ticker not in seen:
                seen.add(ticker)
                rv.setdefault(day, []).append(item)
    return rv


# ---------------------------------------------------------------------------
# News — shared helpers
# ---------------------------------------------------------------------------

def _robinhood_news(ticker: str, max_articles: int) -> list[dict]:
    """Fetch news from Robinhood. Returns [] if not logged in or on any error."""
    try:
        items = rb.robinhood.get_news(ticker) or []
        result = []
        for item in items[:max_articles]:
            result.append({
                "title": item.get("title", ""),
                "publisher": item.get("source", {}).get("name", "Robinhood"),
                "link": item.get("url", ""),
                "summary": item.get("summary", item.get("preview_text", "")),
                "pub_date": item.get("published_at", ""),
                "formatted_date": item.get("published_at", ""),
                "api_source": "robinhood",
            })
        return result
    except Exception:
        return []


def _parse_yfinance_item(item: dict) -> dict | None:
    """Convert a raw yfinance news item to our standard format."""
    content = item.get("content") or {}
    if not content:
        return None
    pub_date = content.get("pubDate") or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        formatted_date = datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%SZ").strftime("%m-%d-%Y")
    except Exception:
        formatted_date = datetime.utcnow().strftime("%m-%d-%Y")
    return {
        "title": content.get("title", "No title"),
        "publisher": (content.get("provider") or {}).get("displayName", "Unknown"),
        "link": (content.get("canonicalUrl") or {}).get("url", ""),
        "summary": content.get("summary", ""),
        "pub_date": pub_date,
        "formatted_date": formatted_date,
    }


def _parse_robinhood_item(item: dict) -> dict:
    """Robinhood items are already in our format — just pass through."""
    return {
        "title": item.get("title", "No title"),
        "publisher": item.get("publisher", "Robinhood"),
        "link": item.get("link", ""),
        "summary": item.get("summary", ""),
        "pub_date": item.get("pub_date", ""),
        "formatted_date": item.get("formatted_date", ""),
    }


def _fetch_news_with_retry(ticker: str, max_articles: int, max_retries: int = 3) -> list[dict]:
    """
    Fetch news for a single ticker via yfinance with exponential backoff,
    falling back to Robinhood on rate-limit or persistent failure.
    """
    for attempt in range(max_retries):
        if attempt > 0:
            backoff = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(backoff)
        try:
            items = (yf.Ticker(ticker).news or [])[:max_articles]
            if items:
                parsed = [_parse_yfinance_item(i) for i in items]
                return [p for p in parsed if p is not None]
            # Empty but no error — not rate limited, just no news
            if attempt == max_retries - 1:
                print(f"No news for {ticker} (normal for some stocks)")
            continue
        except Exception as e:
            msg = str(e).lower()
            is_rate_limit = "rate limit" in msg or "too many requests" in msg
            is_last = attempt == max_retries - 1
            if is_rate_limit or is_last:
                print(f"yfinance {ticker}: {'rate limited' if is_rate_limit else str(e)[:60]} — trying Robinhood")
                rb_news = _robinhood_news(ticker, max_articles)
                if rb_news:
                    return [_parse_robinhood_item(i) for i in rb_news]
                if is_last:
                    print(f"Both APIs failed for {ticker}")
                    return []
    return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_news_for_tickers_by_symbol(
    tickers: list[str],
    max_articles: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """
    Fetch news for all tickers. Returns {symbol: [article, ...]}.

    No volume pre-filtering here — callers should pass an already-screened
    list (source_data.py filters by volume via agg_data fundamentals).
    """
    result: dict[str, list] = {}
    batch_size = 10

    print(f"Fetching news for {len(tickers)} tickers in batches of {batch_size}...")

    for batch_start in range(0, len(tickers), batch_size):
        batch = tickers[batch_start: batch_start + batch_size]
        batch_num = (batch_start // batch_size) + 1
        total_batches = (len(tickers) + batch_size - 1) // batch_size
        print(f"News batch {batch_num}/{total_batches} ({len(batch)} tickers)...")

        for ticker in batch:
            result[ticker] = _fetch_news_with_retry(ticker, max_articles)
            time.sleep(random.uniform(0.1, 0.3))

        if batch_start + batch_size < len(tickers):
            time.sleep(2)

    return result