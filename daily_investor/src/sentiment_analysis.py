"""
Sentiment Analysis Module using LangGraph and Claude
Handles news sentiment analysis for stock trading decisions
"""

import os
import datetime
import logging
import asyncio
import random
import re
import pandas as pd
import robin_stocks.robinhood as rb
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import anthropic

from util import CONFIDENCE_THRESHOLD, METRIC_THRESHOLD, read_data_as_pd

logger = logging.getLogger("investment_bot")

# ==================== BATCH CONFIG ====================

BATCH_SIZE = 6          # stocks per Claude prompt
MAX_CONCURRENT = 5      # parallel API calls via semaphore
MAX_RETRIES = 5         # exponential-backoff retry limit


# ==================== LANGGRAPH SENTIMENT ANALYSIS ====================

class SentimentAnalysisState(TypedDict):
    """State for sentiment analysis workflow"""
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
    # Sentinel set by gather_sentiments when it already has a final answer
    # (no data / error). When True the workflow skips the Claude API call.
    skip_analysis: bool


def initialize_sentiment_model():
    """Initialize Claude model for sentiment analysis (LangChain – single-stock path)"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set. Sentiment analysis will be disabled.")
        return None
    return ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0.3)


def initialize_async_client() -> anthropic.AsyncAnthropic | None:
    """Initialize native async Anthropic client used for batch calls."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.AsyncAnthropic(api_key=api_key)


# Module-level singletons
sentiment_model = initialize_sentiment_model()
async_client = initialize_async_client()


# ==================== DATA PROCESSING (unchanged) ====================

def process_sentiment_data(data: dict, data_type: str, symbol: str) -> tuple[dict, bool]:
    processed = {}
    if symbol in data:
        items = data[symbol]
        if items and isinstance(items, list):
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            processed[today] = items
            return processed, True
    if not data or not any(items for items in data.values() if items):
        return processed, False
    for date, items in data.items():
        if not items:
            continue
        for item in items:
            if item:
                if isinstance(item, str):
                    if date not in processed:
                        processed[date] = []
                    processed[date].append({'content': item, 'ticker': symbol})
                elif item.get('ticker') == symbol:
                    if date not in processed:
                        processed[date] = []
                    processed[date].append(item)
    return processed, bool(processed)


def process_position_data(positions: list, symbol: str) -> dict:
    position = next((p for p in positions if p.get('symbol') == symbol), None)
    if not position:
        return {
            'has_position': False,
            'quantity': 0.0,
            'average_buy_price': 0.0,
            'current_value': 0.0,
            'unrealized_pl': 0.0,
            'days_held': 0
        }
    try:
        try:
            current_price = float(rb.stocks.get_latest_price(symbol)[0])
        except Exception:
            current_price = 0.0
        quantity = float(position.get('quantity', 0))
        avg_price = float(position.get('average_buy_price', 0))
        return {
            'has_position': quantity > 0,
            'quantity': quantity,
            'average_buy_price': avg_price,
            'current_price': current_price,
            'current_value': quantity * current_price,
            'cost_basis': quantity * avg_price,
            'unrealized_pl': (current_price - avg_price) * quantity,
            'unrealized_pl_pct': ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0,
            'days_held': (datetime.datetime.now(datetime.timezone.utc) -
                         datetime.datetime.fromisoformat(
                             position.get('created_at', '').replace('Z', '+00:00')
                         )).days
        }
    except Exception as e:
        logger.error(f"Error processing position data for {symbol}: {e}")
        return {'has_position': False, 'error': str(e)}


# ==================== SHARED PROMPT HELPERS ====================

def _build_valuation_block(symbol: str, fundamentals: dict, news_text: str) -> str:
    """Return the per-stock section used inside both single and batch prompts."""
    return f"""STOCK: {symbol}
FUNDAMENTAL METRICS:
  PE Ratio: {fundamentals.get('pe_ratio', 'N/A')}
  PB Ratio: {fundamentals.get('pb_ratio', 'N/A')}
  Dividend Yield: {fundamentals.get('dividend_yield', 'N/A')}%
  Volume: {fundamentals.get('volume', 'N/A')}
  Industry: {fundamentals.get('industry', 'N/A')}
  Sector: {fundamentals.get('sector', 'N/A')}

VALUATION SCORES:
  PE_COMP: {fundamentals.get('pe_comp', 'N/A')}  |  PB_COMP: {fundamentals.get('pb_comp', 'N/A')}  |  DIV_COMP: {fundamentals.get('div_comp', 'N/A')}
  VALUE_METRIC: {fundamentals.get('value_metric', 'N/A')}

ANALYST RATINGS:
  Buy/Sell Ratio: {fundamentals.get('buy_to_sell_ratio', 'N/A')}

NEWS SENTIMENT:
{news_text}"""


def format_news_data(news_data: dict, symbol: str) -> str:
    if not news_data:
        return "No news data available"
    formatted = []
    news_count = 0
    for article in news_data.get(symbol, [])[:3]:
        if isinstance(article, dict):
            title = article.get('title', 'No title')
            publisher = article.get('publisher', 'Unknown')
            date = article.get('formatted_date', 'Unknown')
            summary = article.get('summary', 'No summary')
            if title and publisher and date and summary:
                formatted.append(f"• {title[:100]}...")
                formatted.append(f"  Publisher: {publisher}")
                formatted.append(f"  Date: {date}")
                formatted.append(f"  Summary: {summary[:200]}...")
                news_count += 1
    return "\n".join(formatted) if news_count else "No news articles found"


# ==================== ASYNC BATCH ANALYSIS ====================

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore


def _build_batch_prompt(batch: list[dict], action: str) -> str:
    """Build a single prompt that asks Claude to rate multiple stocks at once."""
    system = (
        f"You are a financial sentiment analyst. For each stock below, decide whether to {action.upper()} it. "
        "Use the fundamental metrics, valuation scores, and news data provided. "
        "Reply for every stock in this EXACT format with no extra text between blocks:\n\n"
        "STOCK: <SYMBOL>\n"
        "RECOMMENDATION: <YES|NO|NEUTRAL>\n"
        "CONFIDENCE: <0-100>%\n"
        "REASONING: <one sentence>\n"
        "---\n\n"
        "Scoring guide:\n"
        "- PE_COMP/PB_COMP > 1.0 → cheaper than sector average (positive for buying)\n"
        "- VALUE_METRIC ≥ 2.0 with PE_COMP or PB_COMP > 1 → strong fundamental buy case\n"
        "- VALUE_METRIC = 0 and no positive news → weak case\n"
        "- Buy/Sell Ratio > 1 supports buying; < 1 is a warning sign"
    )

    stock_blocks = []
    for item in batch:
        news_text = format_news_data(item.get("news_sentiment", {}), item["symbol"])
        block = _build_valuation_block(item["symbol"], item.get("fundamental_metrics", {}), news_text)
        stock_blocks.append(block)

    user_msg = (
        f"Analyze these {len(batch)} stocks for {action.upper()} decisions:\n\n"
        + "\n\n---\n\n".join(stock_blocks)
    )
    return system, user_msg


async def _call_claude_batch_async(
    batch: list[dict],
    action: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, dict]:
    """Send one batched prompt to Claude and parse per-symbol results."""
    if not async_client:
        return {}

    system_prompt, user_prompt = _build_batch_prompt(batch, action)

    for attempt in range(MAX_RETRIES):
        async with semaphore:
            try:
                response = await async_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw_text = response.content[0].text
                return _parse_batch_response(raw_text, batch)

            except anthropic.RateLimitError:
                sleep_time = (2 ** attempt) * (1 + random.random())
                logger.warning(
                    f"Rate-limited on batch ({[s['symbol'] for s in batch]}). "
                    f"Sleeping {sleep_time:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                await asyncio.sleep(sleep_time)

            except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
                sleep_time = (2 ** attempt) * (1 + random.random())
                logger.warning(
                    f"Transient error on batch: {exc}. "
                    f"Sleeping {sleep_time:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                await asyncio.sleep(sleep_time)

            except Exception as exc:
                logger.error(f"Unrecoverable error in batch call: {exc}")
                break

    # All retries exhausted — return NEUTRAL for every symbol in batch
    return {
        item["symbol"]: {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": "API error after retries"}
        for item in batch
    }


def _parse_batch_response(raw: str, batch: list[dict]) -> dict[str, dict]:
    """Parse Claude's multi-stock response into {symbol: result} dict."""
    results: dict[str, dict] = {}
    # Split on the separator between stock blocks
    blocks = re.split(r'\n---+\n?', raw.strip())

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        symbol_match = re.search(r'STOCK:\s*([A-Z.\-]+)', block, re.IGNORECASE)
        rec_match = re.search(r'RECOMMENDATION:\s*(YES|NO|NEUTRAL)', block, re.IGNORECASE)
        conf_match = re.search(r'CONFIDENCE:\s*(\d+(?:\.\d+)?)\s*%?', block, re.IGNORECASE)
        reason_match = re.search(r'REASONING:\s*(.+)', block, re.IGNORECASE | re.DOTALL)

        if not symbol_match:
            continue

        symbol = symbol_match.group(1).upper()
        recommendation = rec_match.group(1).upper() if rec_match else "NEUTRAL"
        confidence = float(conf_match.group(1)) if conf_match else 0.0
        reasoning = reason_match.group(1).strip().split('\n')[0] if reason_match else "No reasoning provided"

        results[symbol] = {
            "recommendation": recommendation,
            "confidence": confidence,
            "reasoning": reasoning,
        }

    # Fill in NEUTRAL for any symbol Claude missed
    for item in batch:
        sym = item["symbol"]
        if sym not in results:
            logger.warning(f"No result parsed for {sym} in batch — defaulting NEUTRAL")
            results[sym] = {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": "Not found in Claude response"}

    return results


async def _run_all_batches_async(
    stocks_data: list[dict],
    action: str,
) -> dict[str, dict]:
    """Chunk stocks_data into batches and run all concurrently."""
    semaphore = _get_semaphore()
    chunks = [stocks_data[i:i + BATCH_SIZE] for i in range(0, len(stocks_data), BATCH_SIZE)]
    logger.info(f"Dispatching {len(chunks)} batch(es) for {len(stocks_data)} stocks (batch_size={BATCH_SIZE}, max_concurrent={MAX_CONCURRENT})")

    tasks = [_call_claude_batch_async(chunk, action, semaphore) for chunk in chunks]
    chunk_results = await asyncio.gather(*tasks)

    merged: dict[str, dict] = {}
    for result in chunk_results:
        merged.update(result)
    return merged


def get_batch_sentiment_recommendations(stocks_data: list[dict], action: str = "buy") -> dict[str, dict]:
    """
    Public entry point for batch analysis.

    Args:
        stocks_data: list of dicts, each with keys:
            symbol, action (optional), fundamental_metrics, news_sentiment
        action: "buy" or "sell" (default "buy")

    Returns:
        {symbol: {recommendation, confidence, reasoning}}
    """
    if not async_client:
        logger.warning("Async client not available — falling back to per-stock analysis")
        return {
            item["symbol"]: get_sentiment_recommendation(item["symbol"], action)
            for item in stocks_data
        }

    # Always run on a fresh event loop to avoid closed/running loop issues.
    # asyncio.run() creates a new loop, runs the coroutine, and closes it cleanly.
    # For the rare case we're already inside a running loop (e.g. Jupyter/notebooks),
    # we offload to a thread so asyncio.run() gets its own clean loop there.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None  # No running loop — safe to call asyncio.run() directly

    if loop is not None and loop.is_running():
        import concurrent.futures
        logger.debug("Running inside existing event loop — offloading batch to thread")
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run_all_batches_async(stocks_data, action))
            return future.result()
    else:
        return asyncio.run(_run_all_batches_async(stocks_data, action))


# ==================== SINGLE-STOCK PATH (kept for sales + backward compat) ====================

def gather_sentiments(state: SentimentAnalysisState) -> dict:
    """Gather sentiment data from news and fundamental metrics"""
    symbol = state["symbol"]
    logger.info(f"Gathering sentiments for {symbol}...")

    try:
        open_positions = rb.get_all_positions()
    except Exception as e:
        logger.warning(f"Could not get positions (may not be logged in): {e}")
        open_positions = []

    result = {
        "news_sentiment": {},
        "reddit_sentiment": {},
        "order_history": {},
        "fundamental_metrics": {},
        "analysis": "",
        "recommendation": "NEUTRAL",
        "confidence": 0.0,
        "reasoning": ""
    }

    try:
        try:
            from util import read_data_as_pd
            news_df = read_data_as_pd('news')
            if news_df is not None and not news_df.empty:
                symbol_news = news_df[news_df['symbol'] == symbol]['news']
                if not symbol_news.empty:
                    news_data = {symbol: symbol_news.iloc[0] if len(symbol_news) == 1 else symbol_news.tolist()}
                else:
                    news_data = {}
            else:
                news_data = {}
        except Exception as e:
            logger.error(f"Error reading cached news for {symbol}: {e}")
            news_data = {}

        reddit_data = {}

        try:
            position_info = process_position_data(open_positions, symbol)
        except Exception as e:
            logger.error(f"Error processing position data for {symbol}: {e}")
            position_info = {}

        try:
            agg_df = read_data_as_pd('agg_data')
            if agg_df is not None and not agg_df.empty:
                symbol_row = agg_df[agg_df['symbol'] == symbol]
                if not symbol_row.empty:
                    row = symbol_row.iloc[0]
                    fundamental_metrics = {
                        'pe_ratio': row.get('pe_ratio'),
                        'pb_ratio': row.get('pb_ratio'),
                        'dividend_yield': row.get('dividend_yield'),
                        'volume': row.get('volume'),
                        'pe_comp': row.get('pe_comp'),
                        'pb_comp': row.get('pb_comp'),
                        'div_comp': row.get('div_comp'),
                        'value_metric': row.get('value_metric'),
                        'buy_to_sell_ratio': row.get('buy_to_sell_ratio'),
                        'industry': row.get('industry'),
                        'sector': row.get('sector')
                    }
                else:
                    fundamental_metrics = {k: None for k in [
                        'pe_ratio', 'pb_ratio', 'dividend_yield', 'volume',
                        'pe_comp', 'pb_comp', 'div_comp', 'value_metric',
                        'buy_to_sell_ratio'
                    ]}
                    fundamental_metrics.update({'industry': 'Unknown', 'sector': 'Unknown'})
                    logger.warning(f"Stock {symbol} not found in aggregated data")
            else:
                fundamental_metrics = {}
                logger.warning("No aggregated data available")
        except Exception as e:
            logger.error(f"Error reading fundamental metrics for {symbol}: {e}")
            fundamental_metrics = {k: None for k in [
                'pe_ratio', 'pb_ratio', 'dividend_yield', 'volume',
                'pe_comp', 'pb_comp', 'div_comp', 'value_metric', 'buy_to_sell_ratio'
            ]}
            fundamental_metrics.update({'industry': 'Error', 'sector': 'Error'})

        processed_news, has_news = process_sentiment_data(news_data, "news", symbol)
        processed_reddit, _ = process_sentiment_data(reddit_data, "reddit", symbol)

        has_meaningful_fundamentals = (
            fundamental_metrics and
            fundamental_metrics.get('pe_ratio') is not None and
            fundamental_metrics.get('pb_ratio') is not None
        )

        if not has_news and not has_meaningful_fundamentals:
            logger.warning(f"No valid data available for {symbol} — skipping sentiment analysis")
            result.update({
                "recommendation": "NEUTRAL",
                "confidence": 0.0,
                "reasoning": "No valid news or fundamental data available for analysis.",
                "skip_analysis": True,
            })
            return result

        result.update({
            "news_sentiment": processed_news,
            "reddit_sentiment": processed_reddit,
            "position_info": position_info,
            "fundamental_metrics": fundamental_metrics,
            "skip_analysis": False,
        })

    except Exception as e:
        logger.error(f"Unexpected error in gather_sentiments for {symbol}: {e}")
        result.update({
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": f"Error processing sentiment data: {str(e)}",
            "skip_analysis": True,
        })

    return result


def analyze_sentiment(state: SentimentAnalysisState) -> dict:
    """Use Claude to analyze sentiment and provide recommendation (single-stock, LangChain path)"""
    symbol = state["symbol"]
    action = state["action"]
    news = state["news_sentiment"]
    fundamentals = state["fundamental_metrics"]

    if not sentiment_model:
        return {
            "analysis": "Sentiment analysis unavailable",
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": "Sentiment model not initialized"
        }

    system_prompt = (
        f"You are a financial sentiment analyst. Analyze the provided news sentiment and "
        f"fundamental metrics to determine if I should {action.upper()} this stock.\n\n"
        "Focus on:\n"
        "1. News sentiment and credibility\n"
        "2. Fundamental metrics (P/E ratio, P/B ratio, volume, value metric)\n"
        "3. Overall market sentiment trends\n"
        "4. Recent news impact on stock price\n"
        "5. Analyst recommendations (buy/sell ratio)\n\n"
        "Provide a clear recommendation with confidence level."
    )

    news_text = format_news_data(news, symbol)
    valuation_block = _build_valuation_block(symbol, fundamentals, news_text)

    user_prompt = (
        f"Analyze the following data for {symbol} to determine if I should {action.upper()} this stock.\n\n"
        + valuation_block
        + "\n\nVALUATION SCORE GUIDE:\n"
        "- PE_COMP/PB_COMP > 1.0: Stock CHEAPER than sector average (good for buying)\n"
        "- PE_COMP/PB_COMP = 0: Not cheap enough to score — may be fairly/overvalued\n"
        "- VALUE_METRIC ≥ 2.0 with PE_COMP or PB_COMP > 1: Strong fundamental buy case\n"
        "- Buy/Sell Ratio > 1 supports buying; < 1 is a warning sign\n\n"
        "Respond in this EXACT format:\n"
        "RECOMMENDATION: [YES/NO/NEUTRAL]\n"
        "CONFIDENCE: [0-100]%\n"
        "REASONING: [2-3 sentences referencing specific metric values]"
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]

    try:
        response = sentiment_model.invoke(messages)
        final_state = parse_claude_response(response.content, symbol)
        final_state["analysis"] = response.content

        if final_state["confidence"] < CONFIDENCE_THRESHOLD:
            return {
                "recommendation": "NEUTRAL",
                "confidence": final_state["confidence"],
                "reasoning": f"Confidence {final_state['confidence']}% below threshold {CONFIDENCE_THRESHOLD}%"
            }
        return final_state

    except Exception as e:
        logger.error(f"Error in sentiment analysis for {symbol}: {e}")
        return {
            "analysis": f"Error: {str(e)}",
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": f"Analysis failed: {str(e)}"
        }


def parse_claude_response(response: str, symbol: str) -> dict:
    try:
        lines = response.strip().split('\n')
        result = {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": "Could not parse response"}
        for line in lines:
            line = line.strip().upper()
            if line.startswith("RECOMMENDATION:"):
                rec = line.split(":", 1)[1].strip()
                if rec in ["YES", "NO", "NEUTRAL"]:
                    result["recommendation"] = rec
            elif line.startswith("CONFIDENCE:"):
                conf_str = line.split(":", 1)[1].strip().replace("%", "")
                try:
                    result["confidence"] = float(conf_str)
                except ValueError:
                    pass
            elif line.startswith("REASONING:"):
                result["reasoning"] = line.split(":", 1)[1].strip()
        return result
    except Exception as e:
        logger.error(f"Error parsing Claude response for {symbol}: {e}")
        return {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": f"Parse error: {str(e)}"}


def _route_after_gather(state: SentimentAnalysisState) -> str:
    """Skip Claude entirely when gather_sentiments already produced a final answer."""
    if state.get("skip_analysis", False):
        logger.debug(f"Short-circuiting workflow for {state['symbol']} — no Claude call needed")
        return END
    return "analyze_sentiment"


def create_sentiment_workflow():
    workflow = StateGraph(SentimentAnalysisState)
    workflow.add_node("gather_sentiments", gather_sentiments)
    workflow.add_node("analyze_sentiment", analyze_sentiment)
    # Conditional: only call Claude when gather_sentiments has real data to analyse
    workflow.add_conditional_edges(
        "gather_sentiments",
        _route_after_gather,
        {"analyze_sentiment": "analyze_sentiment", END: END},
    )
    workflow.add_edge("analyze_sentiment", END)
    workflow.set_entry_point("gather_sentiments")
    return workflow.compile()


sentiment_workflow = create_sentiment_workflow()


def get_sentiment_recommendation(symbol: str, action: str) -> dict:
    """
    Single-stock sentiment recommendation (kept for sell path + backward compat).

    Args:
        symbol: Stock symbol
        action: "buy" or "sell"
    Returns:
        {recommendation, confidence, reasoning}
    """
    initial_state = {
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
        final_state = sentiment_workflow.invoke(initial_state)
        return {
            "recommendation": final_state["recommendation"],
            "confidence": final_state["confidence"],
            "reasoning": final_state["reasoning"]
        }
    except Exception as e:
        logger.error(f"Error in sentiment workflow for {symbol}: {e}")
        return {"recommendation": "NEUTRAL", "confidence": 0.0, "reasoning": f"Workflow error: {str(e)}"}