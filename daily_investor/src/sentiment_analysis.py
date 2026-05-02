"""
sentiment_analysis.py — Batch async + single-stock Claude sentiment analysis.

Two paths:
  - Batch async (buy candidates): get_batch_sentiment_recommendations()
    Chunks stocks into BATCH_SIZE groups, dispatches all concurrently via
    asyncio.gather() + Semaphore, exponential backoff on rate limits.

  - Single-stock LangGraph (sell hold-check, backward compat): get_sentiment_recommendation()
    Short-circuits to END without calling Claude when no valid data exists.
"""

import asyncio
import datetime
import logging
import os
import random
import re
from typing import Literal

import anthropic
import robin_stocks.robinhood as rb
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict
from dotenv import load_dotenv

load_dotenv()

from util import CONFIDENCE_THRESHOLD, METRIC_KEYS, read_data_as_pd

logger = logging.getLogger("investment_bot")

# ---------------------------------------------------------------------------
# Batch config
# ---------------------------------------------------------------------------

BATCH_SIZE     = 6   # stocks per Claude prompt
MAX_CONCURRENT = 5   # semaphore cap on parallel calls
MAX_RETRIES    = 5   # exponential-backoff attempts per batch

# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------

class SentimentAnalysisState(TypedDict):
    symbol: str
    action: Literal["buy", "sell"]
    news_sentiment: dict
    reddit_sentiment: dict
    position_info: dict
    fundamental_metrics: dict
    analysis: str
    recommendation: Literal["YES", "NO", "NEUTRAL"]
    confidence: float
    reasoning: str
    skip_analysis: bool  # True → jump to END without calling Claude


# ---------------------------------------------------------------------------
# Client initialisation
# ---------------------------------------------------------------------------

def _make_langchain_model() -> ChatAnthropic | None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set — sentiment analysis disabled")
        return None
    return ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0.3)


def _make_async_client() -> anthropic.AsyncAnthropic | None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    return anthropic.AsyncAnthropic()


_lc_model     = _make_langchain_model()
_async_client = _make_async_client()

# ---------------------------------------------------------------------------
# Shared prompt helpers
# ---------------------------------------------------------------------------

_SCORING_GUIDE = """\
Scoring guide:
- PE_COMP/PB_COMP > 1 → cheaper than sector threshold (positive signal)
- YIELD_TRAP=True → dividend likely caused by price collapse (major warning)
- VALUE_METRIC combines value + quality + income; higher is better
- Buy/Sell Ratio > 1 supports buying; < 1 is a warning sign"""


def _format_news(news_data: dict, symbol: str) -> str:
    lines = []
    for a in news_data.get(symbol, [])[:3]:
        if not isinstance(a, dict):
            continue
        title   = a.get("title", "")
        pub     = a.get("publisher", "")
        date    = a.get("formatted_date", "")
        summary = a.get("summary", "")
        if title and pub:
            lines += [
                f"• {title[:100]}",
                f"  Publisher: {pub}  Date: {date}",
                f"  Summary: {summary[:200]}",
            ]
    return "\n".join(lines) if lines else "No news articles found"


def _valuation_block(symbol: str, f: dict, news_text: str) -> str:
    return (
        f"STOCK: {symbol}\n"
        f"FUNDAMENTAL METRICS:\n"
        f"  PE={f.get('pe_ratio','N/A')}  PB={f.get('pb_ratio','N/A')}\n"
        f"  Dividend Yield={f.get('dividend_yield','N/A')}  Volume={f.get('volume','N/A')}\n"
        f"  Industry={f.get('industry','N/A')}  Sector={f.get('sector','N/A')}\n\n"
        f"VALUATION:\n"
        f"  PE_COMP={f.get('pe_comp','N/A')}  PB_COMP={f.get('pb_comp','N/A')}\n"
        f"  VALUE_SCORE={f.get('value_score','N/A')}  INCOME_SCORE={f.get('income_score','N/A')}\n"
        f"  QUALITY_SCORE={f.get('quality_score','N/A')}  YIELD_TRAP={f.get('yield_trap_flag','N/A')}\n"
        f"  VALUE_METRIC={f.get('value_metric','N/A')}\n\n"
        f"ANALYST: Buy/Sell Ratio={f.get('buy_to_sell_ratio','N/A')}\n\n"
        f"NEWS:\n{news_text}"
    )


# ---------------------------------------------------------------------------
# Response parsing (shared by both paths)
# ---------------------------------------------------------------------------

def _parse_response(text: str) -> dict:
    result = {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": "Could not parse response"}
    for line in text.strip().split("\n"):
        u = line.strip().upper()
        if u.startswith("RECOMMENDATION:"):
            rec = u.split(":", 1)[1].strip()
            if rec in ("YES", "NO", "NEUTRAL"):
                result["recommendation"] = rec
        elif u.startswith("CONFIDENCE:"):
            try:
                result["confidence"] = float(u.split(":", 1)[1].strip().replace("%", ""))
            except ValueError:
                pass
        elif u.startswith("REASONING:"):
            result["reasoning"] = line.split(":", 1)[1].strip()
    return result


# ---------------------------------------------------------------------------
# Batch async path
# ---------------------------------------------------------------------------

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore


def _build_batch_prompt(batch: list[dict], action: str) -> tuple[str, str]:
    system = (
        f"You are a financial sentiment analyst. For each stock, decide whether to {action.upper()} it.\n"
        "Reply for EVERY stock in this EXACT format, nothing else:\n\n"
        "STOCK: <SYMBOL>\nRECOMMENDATION: <YES|NO|NEUTRAL>\n"
        "CONFIDENCE: <0-100>%\nREASONING: <one sentence>\n---\n\n"
        + _SCORING_GUIDE
    )
    blocks = [
        _valuation_block(
            item["symbol"],
            item.get("fundamental_metrics", {}),
            _format_news(item.get("news_sentiment", {}), item["symbol"]),
        )
        for item in batch
    ]
    user = f"Analyze these {len(batch)} stocks for {action.upper()}:\n\n" + "\n\n---\n\n".join(blocks)
    return system, user


def _parse_batch_response(raw: str, batch: list[dict]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for block in re.split(r"\n---+\n?", raw.strip()):
        block = block.strip()
        if not block:
            continue
        sym_m = re.search(r"STOCK:\s*([A-Z.\-]+)", block, re.IGNORECASE)
        if not sym_m:
            continue
        symbol = sym_m.group(1).upper()
        results[symbol] = _parse_response(block)

    for item in batch:
        sym = item["symbol"]
        if sym not in results:
            logger.warning(f"No result parsed for {sym} — defaulting NEUTRAL")
            results[sym] = {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": "Missing from Claude response"}

    return results


async def _call_batch_async(
    batch: list[dict],
    action: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, dict]:
    if not _async_client:
        return {}

    system_prompt, user_prompt = _build_batch_prompt(batch, action)

    for attempt in range(MAX_RETRIES):
        async with semaphore:
            try:
                response = await _async_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return _parse_batch_response(response.content[0].text, batch)

            except anthropic.RateLimitError:
                wait = (2 ** attempt) * (1 + random.random())
                logger.warning(f"Rate-limited (attempt {attempt+1}/{MAX_RETRIES}), sleeping {wait:.1f}s")
                await asyncio.sleep(wait)

            except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
                wait = (2 ** attempt) * (1 + random.random())
                logger.warning(f"Transient error: {exc} — sleeping {wait:.1f}s")
                await asyncio.sleep(wait)

            except Exception as exc:
                logger.error(f"Unrecoverable batch error: {exc}")
                break

    return {
        item["symbol"]: {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": "API error after retries"}
        for item in batch
    }


async def _run_all_batches(stocks_data: list[dict], action: str) -> dict[str, dict]:
    semaphore = _get_semaphore()
    chunks = [stocks_data[i: i + BATCH_SIZE] for i in range(0, len(stocks_data), BATCH_SIZE)]
    logger.info(f"Dispatching {len(chunks)} batch(es) for {len(stocks_data)} stocks")
    chunk_results = await asyncio.gather(*[_call_batch_async(c, action, semaphore) for c in chunks])
    merged: dict[str, dict] = {}
    for r in chunk_results:
        merged.update(r)
    return merged


def get_batch_sentiment_recommendations(
    stocks_data: list[dict],
    action: str = "buy",
) -> dict[str, dict]:
    """
    Analyze multiple stocks in one async round-trip.

    Args:
        stocks_data: list of {symbol, fundamental_metrics, news_sentiment}
        action: "buy" or "sell"
    Returns:
        {symbol: {recommendation, confidence, reasoning}}
    """
    if not _async_client:
        logger.warning("Async client unavailable — falling back to per-stock analysis")
        return {
            item["symbol"]: get_sentiment_recommendation(item["symbol"], action)
            for item in stocks_data
        }

    try:
        asyncio.get_running_loop()
        # Already inside a running loop (e.g. Jupyter) — offload to thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _run_all_batches(stocks_data, action)).result()
    except RuntimeError:
        # No running loop — safe to call asyncio.run() directly
        return asyncio.run(_run_all_batches(stocks_data, action))


# ---------------------------------------------------------------------------
# Single-stock LangGraph path (sell hold-check + backward compat)
# ---------------------------------------------------------------------------

def _load_fundamentals(symbol: str) -> tuple[dict, bool]:
    try:
        agg_df = read_data_as_pd("agg_data")
        if agg_df is not None and not agg_df.empty:
            row = agg_df[agg_df["symbol"] == symbol]
            if not row.empty:
                r = row.iloc[0]
                return {k: r.get(k) for k in METRIC_KEYS}, True
    except Exception as e:
        logger.error(f"Error loading fundamentals for {symbol}: {e}")
    return {k: None for k in METRIC_KEYS}, False


def _load_news(symbol: str) -> tuple[dict, bool]:
    try:
        news_df = read_data_as_pd("news")
        if news_df is not None and not news_df.empty:
            rows = news_df[news_df["symbol"] == symbol]["news"]
            if not rows.empty:
                return {symbol: rows.iloc[0] if len(rows) == 1 else rows.tolist()}, True
    except Exception as e:
        logger.error(f"Error loading news for {symbol}: {e}")
    return {}, False


def _process_position(positions: list, symbol: str) -> dict:
    pos = next((p for p in positions if p.get("symbol") == symbol), None)
    if not pos:
        return {"has_position": False}
    try:
        try:
            price = float(rb.stocks.get_latest_price(symbol)[0])
        except Exception:
            price = 0.0
        qty = float(pos.get("quantity", 0))
        avg = float(pos.get("average_buy_price", 0))
        return {
            "has_position": qty > 0,
            "quantity": qty,
            "average_buy_price": avg,
            "current_price": price,
            "current_value": qty * price,
            "cost_basis": qty * avg,
            "unrealized_pl": (price - avg) * qty,
            "unrealized_pl_pct": ((price / avg) - 1) * 100 if avg else 0,
            "days_held": (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.datetime.fromisoformat(pos.get("created_at", "").replace("Z", "+00:00"))
            ).days,
        }
    except Exception as e:
        return {"has_position": False, "error": str(e)}


def gather_sentiments(state: SentimentAnalysisState) -> dict:
    symbol = state["symbol"]
    logger.info(f"Gathering sentiments for {symbol}...")

    try:
        positions = rb.get_all_positions()
    except Exception:
        positions = []

    fundamentals, has_fundamentals = _load_fundamentals(symbol)
    news_data, has_news = _load_news(symbol)

    has_meaningful = (
        has_fundamentals
        and fundamentals.get("pe_ratio") is not None
        and fundamentals.get("pb_ratio") is not None
    )

    if not has_news and not has_meaningful:
        logger.warning(f"No valid data for {symbol} — skipping Claude call")
        return {
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": "No valid news or fundamental data available",
            "skip_analysis": True,
        }

    return {
        "news_sentiment":      news_data,
        "reddit_sentiment":    {},
        "position_info":       _process_position(positions, symbol),
        "fundamental_metrics": fundamentals,
        "skip_analysis":       False,
    }


def analyze_sentiment(state: SentimentAnalysisState) -> dict:
    symbol = state["symbol"]
    action = state["action"]

    if not _lc_model:
        return {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": "Model not initialised"}

    news_text = _format_news(state["news_sentiment"], symbol)
    block = _valuation_block(symbol, state["fundamental_metrics"], news_text)

    system = (
        f"You are a financial sentiment analyst. Determine whether to {action.upper()} {symbol}.\n"
        + _SCORING_GUIDE
    )
    user = (
        f"Analyze the following for {symbol} ({action.upper()}):\n\n{block}\n\n"
        "Respond EXACTLY:\n"
        "RECOMMENDATION: [YES/NO/NEUTRAL]\n"
        "CONFIDENCE: [0-100]%\n"
        "REASONING: [2-3 sentences with specific metric values]"
    )

    try:
        response = _lc_model.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        result = _parse_response(response.content)
        result["analysis"] = response.content
        if result["confidence"] < CONFIDENCE_THRESHOLD:
            return {
                "recommendation": "NEUTRAL",
                "confidence": result["confidence"],
                "reasoning": f"Confidence {result['confidence']}% below threshold {CONFIDENCE_THRESHOLD}%",
            }
        return result
    except Exception as e:
        logger.error(f"Sentiment analysis failed for {symbol}: {e}")
        return {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": f"Analysis error: {e}"}


def _route_after_gather(state: SentimentAnalysisState) -> str:
    return END if state.get("skip_analysis", False) else "analyze_sentiment"


def _build_workflow() -> object:
    wf = StateGraph(SentimentAnalysisState)
    wf.add_node("gather_sentiments", gather_sentiments)
    wf.add_node("analyze_sentiment", analyze_sentiment)
    wf.add_conditional_edges(
        "gather_sentiments",
        _route_after_gather,
        {"analyze_sentiment": "analyze_sentiment", END: END},
    )
    wf.add_edge("analyze_sentiment", END)
    wf.set_entry_point("gather_sentiments")
    return wf.compile()


_workflow = _build_workflow()


def get_sentiment_recommendation(symbol: str, action: str) -> dict:
    """Single-stock path — used for sell hold-checks and backward compatibility."""
    initial: SentimentAnalysisState = {
        "symbol": symbol,
        "action": action,
        "news_sentiment": {},
        "reddit_sentiment": {},
        "position_info": {},
        "fundamental_metrics": {},
        "analysis": "",
        "recommendation": "NEUTRAL",
        "confidence": 0.0,
        "reasoning": "",
        "skip_analysis": False,
    }
    try:
        final = _workflow.invoke(initial)
        return {
            "recommendation": final["recommendation"],
            "confidence":     final["confidence"],
            "reasoning":      final["reasoning"],
        }
    except Exception as e:
        logger.error(f"Workflow error for {symbol}: {e}")
        return {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": f"Workflow error: {e}"}