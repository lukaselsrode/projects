import os
import datetime
import logging
import pyotp
import pandas as pd
import robin_stocks.robinhood as rb
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from source_data import generate_daily_undervalued_stocks
from sentiments import get_news_for_tickers, reddit_sentiments_for_tickers
from util import (
    update_industry_valuations,
    SELLOFF_THRESHOLD,
    WEEKLY_INVESTMENT,
    AUTO_APPROVE,
    ETFS,
    INDEX_PCT,
    USE_SENTIMENT_ANALYSIS,
    CONFIDENCE_THRESHOLD,
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


# ==================== LANGGRAPH SENTIMENT ANALYSIS ====================

class SentimentAnalysisState(TypedDict):
    """State for sentiment analysis workflow"""
    symbol: str
    action: Literal["buy", "sell"]
    news_sentiment: dict
    reddit_sentiment: dict
    analysis: str
    recommendation: Literal["YES", "NO", "NEUTRAL"]
    confidence: float
    reasoning: str

def initialize_sentiment_model():
    """Initialize the Claude model for sentiment analysis"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set. Sentiment analysis will be disabled.")
        return None
    return ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0.3)

# Initialize model at module level
sentiment_model = initialize_sentiment_model() if USE_SENTIMENT_ANALYSIS else None

def gather_sentiments(state: SentimentAnalysisState) -> dict:
    """Gather sentiment data from news and reddit"""
    symbol = state["symbol"]
    logger.info(f"Gathering sentiments for {symbol}...")
    
    # Initialize default return value
    result = {
        "news_sentiment": {},
        "reddit_sentiment": {},
        "analysis": "",
        "recommendation": "NEUTRAL",
        "confidence": 0.0,
        "reasoning": ""
    }
    
    try:
        # Get news data
        try:
            news_data = get_news_for_tickers([symbol]) or {}
            logger.debug(f"Raw news data for {symbol}: {news_data}")
        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            news_data = {}
        
        # Get Reddit data with error handling
        try:
            reddit_data = reddit_sentiments_for_tickers([symbol]) or {}
            logger.debug(f"Raw reddit data for {symbol}: {reddit_data}")
        except Exception as e:
            logger.error(f"Error fetching Reddit data for {symbol}: {e}")
            reddit_data = {}
        
        # Check if we have any valid data
        has_news = bool(news_data) and any(articles for articles in news_data.values() if articles)
        has_reddit = bool(reddit_data) and any(sentiments for sentiments in reddit_data.values() if sentiments)
        
        if not has_news and not has_reddit:
            logger.warning(f"No valid sentiment data available for {symbol}")
            result.update({
                "recommendation": "NEUTRAL",
                "confidence": 0.0,
                "reasoning": "No valid news or social media data available for analysis."
            })
            return result
        
        # Process news data if available
        processed_news = {}
        if has_news:
            for date, articles in news_data.items():
                if not articles:
                    continue
                for article in articles:
                    if article and article.get('ticker') == symbol:
                        if date not in processed_news:
                            processed_news[date] = []
                        processed_news[date].append(article)
        
        # Process Reddit data if available
        processed_reddit = {}
        if has_reddit:
            for date, sentiments in reddit_data.items():
                if not sentiments:
                    continue
                for sentiment in sentiments:
                    if sentiment and sentiment.get('ticker') == symbol:
                        if date not in processed_reddit:
                            processed_reddit[date] = []
                        processed_reddit[date].append(sentiment)
        
        result.update({
            "news_sentiment": processed_news,
            "reddit_sentiment": processed_reddit
        })
        
    except Exception as e:
        logger.error(f"Unexpected error in gather_sentiments for {symbol}: {e}")
        result.update({
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": f"Error processing sentiment data: {str(e)}"
        })
    
    return result


def analyze_sentiment(state: SentimentAnalysisState) -> dict:
    """Use Claude to analyze sentiment and provide recommendation"""
    symbol = state["symbol"]
    action = state["action"]
    news = state["news_sentiment"]
    reddit = state["reddit_sentiment"]
    
    if not sentiment_model:
        logger.warning("Sentiment model not initialized. Returning neutral recommendation.")
        return {
            "analysis": "Sentiment analysis unavailable",
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": "Sentiment model not initialized"
        }
    
    # Build the prompt for Claude
    system_prompt = """You are a financial sentiment analyst. Analyze news and social media sentiment 
    to provide clear buy/sell recommendations. Consider:
    
    1. Overall sentiment tone (positive/negative/neutral)
    2. Volume and recency of mentions
    3. Credibility of sources
    4. Specific concerns or opportunities mentioned
    5. Consistency across sources
    6. Recent trends vs historical sentiment
    
    Provide a clear YES or NO recommendation with confidence level (0-100%) and reasoning."""
    
    user_prompt = f"""Analyze the following sentiment data for {symbol} to determine if I should {action.upper()} this stock:

NEWS SENTIMENT:
{format_news_data(news, symbol)}

REDDIT SENTIMENT:
{format_reddit_data(reddit, symbol)}

Based on this data, should I {action.upper()} {symbol}?

Respond in this exact format:
RECOMMENDATION: [YES/NO/NEUTRAL]
CONFIDENCE: [0-100]%
REASONING: [2-3 sentences explaining your recommendation]"""
    
    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = sentiment_model.invoke(messages)
        analysis_text = response.content
        
        # Parse the response
        recommendation, confidence, reasoning = parse_claude_response(analysis_text)
        
        logger.info(f"Sentiment Analysis for {symbol}: {recommendation} ({confidence}% confidence)")
        
        return {
            "analysis": analysis_text,
            "recommendation": recommendation,
            "confidence": confidence,
            "reasoning": reasoning
        }
        
    except Exception as e:
        logger.error(f"Error analyzing sentiment for {symbol}: {e}")
        return {
            "analysis": f"Error: {str(e)}",
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": f"Analysis failed: {str(e)}"
        }

def format_news_data(news_data: dict, symbol: str) -> str:
    """Format news data for Claude analysis"""
    if not news_data:
        return "No news data available"
    
    formatted = []
    news_count = 0
    
    for date, articles in sorted(news_data.items(), reverse=True):
        date_articles = [a for a in articles if a.get('ticker') == symbol]
        
        if date_articles:
            formatted.append(f"\n{date}:")
            for article in date_articles:
                news = article.get('news', {})
                title = news.get('title', 'N/A')
                summary = news.get('summary', 'N/A')
                publisher = news.get('publisher', 'N/A')
                
                formatted.append(f"  • {title}")
                formatted.append(f"    Publisher: {publisher}")
                formatted.append(f"    Summary: {summary}")
                news_count += 1
    
    if news_count == 0:
        return f"No recent news found for {symbol}"
    
    return f"Total articles: {news_count}\n" + "\n".join(formatted)

def format_reddit_data(reddit_data: dict, symbol: str) -> str:
    """Format reddit sentiment data for Claude analysis"""
    if not reddit_data:
        return "No reddit data available"
    
    formatted = []
    total_comments = 0
    sentiment_scores = []
    
    for date, sentiments in sorted(reddit_data.items(), reverse=True):
        symbol_sentiments = [s for s in sentiments if s.get('ticker') == symbol]
        
        if symbol_sentiments:
            formatted.append(f"\n{date}:")
            for sent in symbol_sentiments:
                sentiment = sent.get('sentiment', 'N/A')
                score = sent.get('sentiment_score', 0)
                comments = sent.get('no_of_comments', 0)
                
                formatted.append(f"  • Sentiment: {sentiment} (Score: {score:.3f})")
                formatted.append(f"    Comments: {comments}")
                
                total_comments += comments
                sentiment_scores.append(score)
    
    if not sentiment_scores:
        return f"No reddit sentiment found for {symbol}"
    
    avg_score = sum(sentiment_scores) / len(sentiment_scores)
    overall_sentiment = "Bullish" if avg_score > 0.1 else "Bearish" if avg_score < -0.1 else "Neutral"
    
    summary = (f"Total comments tracked: {total_comments}\n"
               f"Average sentiment score: {avg_score:.3f} ({overall_sentiment})\n"
               f"Data points: {len(sentiment_scores)} days")
    
    return summary + "\n" + "\n".join(formatted)

def parse_claude_response(response: str) -> tuple:
    """Parse Claude's response to extract recommendation, confidence, and reasoning"""
    lines = response.strip().split("\n")
    
    recommendation = "NEUTRAL"
    confidence = 50.0
    reasoning = "Unable to parse response"
    
    for line in lines:
        line = line.strip()
        if line.startswith("RECOMMENDATION:"):
            rec = line.split(":", 1)[1].strip().upper()
            if rec in ["YES", "NO", "NEUTRAL"]:
                recommendation = rec
        elif line.startswith("CONFIDENCE:"):
            try:
                conf_str = line.split(":", 1)[1].strip().replace("%", "")
                confidence = float(conf_str)
            except:
                pass
        elif line.startswith("REASONING:"):
            reasoning = line.split(":", 1)[1].strip()
    
    return recommendation, confidence, reasoning

def build_sentiment_workflow():
    """Build the LangGraph workflow for sentiment analysis"""
    workflow = StateGraph(SentimentAnalysisState)
    
    # Add nodes
    workflow.add_node("gather", gather_sentiments)
    workflow.add_node("analyze", analyze_sentiment)
    
    # Set entry point and edges
    workflow.set_entry_point("gather")
    workflow.add_edge("gather", "analyze")
    workflow.add_edge("analyze", END)
    
    return workflow.compile()

# Initialize the sentiment workflow
sentiment_workflow = build_sentiment_workflow() if USE_SENTIMENT_ANALYSIS else None

def get_sentiment_recommendation(symbol: str, action: Literal["buy", "sell"]) -> dict:
    """Get sentiment-based trading recommendation"""
    if not USE_SENTIMENT_ANALYSIS:
        logger.info("Sentiment analysis is disabled (USE_SENTIMENT_ANALYSIS=False)")
        return {
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": "Sentiment analysis disabled"
        }
    
    if not sentiment_workflow:
        logger.warning("Sentiment workflow not initialized")
        return {
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": "Workflow not initialized"
        }
    
    initial_state = {
        "symbol": symbol,
        "action": action,
        "news_sentiment": {},
        "reddit_sentiment": {},
        "analysis": "",
        "recommendation": "NEUTRAL",
        "confidence": 0.0,
        "reasoning": ""
    }
    
    try:
        final_state = sentiment_workflow.invoke(initial_state)
        
        # Check if confidence meets threshold
        if final_state["confidence"] < CONFIDENCE_THRESHOLD:
            logger.info(f"Confidence {final_state['confidence']}% is below threshold of {CONFIDENCE_THRESHOLD}%")
            return {
                "recommendation": "NEUTRAL",
                "confidence": final_state["confidence"],
                "reasoning": f"Confidence level {final_state['confidence']}% is below threshold of {CONFIDENCE_THRESHOLD}%"
            }
            
        return {
            "recommendation": final_state["recommendation"],
            "confidence": final_state["confidence"],
            "reasoning": final_state["reasoning"]
        }
    except Exception as e:
        logger.error(f"Error running sentiment workflow for {symbol}: {e}")
        return {
            "recommendation": "NEUTRAL",
            "confidence": 0.0,
            "reasoning": f"Workflow error: {str(e)}"
        }



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
            logger.error("Please check your RB_MFA_SECRET environment variable")
    else:
        mfa_msg = ("\n" + "="*50 + "\n"
                  "MFA REQUIRED\n"
                  "To skip this prompt in the future, set RB_MFA_SECRET environment variable\n"
                  "with your MFA secret for automatic code generation.\n"
                  "="*50 + "\n")
        logger.info(mfa_msg)
    
    try:
        logger.info("Attempting to log in...")
        rb.login(
            username=username,
            password=password,
            mfa_code=mfa_code,
            store_session=True
        )
        logger.info("Successfully logged in!")
    except Exception as e:
        logger.error(f"Login failed: {e}")
        if "mfa_required" in str(e).lower() and not mfa_code:
            logger.info("\nMFA code is required. Please enter the code from your authenticator app.")
            mfa_code = input("Enter MFA code: ").strip()
            rb.login(
                username=username,
                password=password,
                mfa_code=mfa_code,
                store_session=True
            )
            logger.info("Successfully logged in with MFA code!")
        else:
            raise


def confirm(prompt: str) -> bool:
    """Get user confirmation, auto-approve if configured"""
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
            bank_accounts = rb.get_linked_bank_accounts()
            ach = bank_accounts[0].get('url') 
            resp = rb.deposit_funds_to_robinhood_account(ach, round(amount_needed, 2))
            logger.info(f"Deposit response: {resp}")
            logger.info(f"Request To Deposit ${amount_needed:,.2f} : {resp.get('state')}")
    else:
        logger.info(f"Not Adding Funds To Account, Enough Cash Available: {get_available_cash()} > {WEEKLY_INVESTMENT}")


def sell(symbol: str, quantity: float):
    if not AUTO_APPROVE and not confirm(f"Confirm sell order for {quantity} shares of {symbol}?"):
        logger.info(f"Cancelled sell order for {symbol}")
        return None
    return rb.order_sell_market(symbol, quantity)


def make_sales():
    to_sell = {
        k: v for k, v in rb.build_holdings().items()
        if abs(float(v.get("percent_change", 0))) > SELLOFF_THRESHOLD 
        and k not in ETFS
    }
    
    if not to_sell:
        logger.info("No stocks to sell")
        return
        
    for symbol, data in to_sell.items():
        quantity = float(data.get('quantity', 0))
        if quantity <= 0:
            continue
            
        if AUTO_APPROVE or confirm(f"Sell {quantity} of {symbol}?"):
            res = sell(symbol, quantity)
            logger.info(f'Sell order response for {symbol}: {res}')
    
    logger.info('Sales completed')


def make_buys(df: pd.DataFrame):
    def calculate_allocations():
        total_cash = get_available_cash()
        etf_amount = total_cash * INDEX_PCT
        stock_amount = total_cash - etf_amount
        return etf_amount, stock_amount

    def make_etf_buys(amount: float):
        if amount <= 0:
            logger.info("No funds allocated to ETFs")
            return
            
        etf_count = len(ETFS)
        if etf_count == 0:
            logger.warning("No ETFs configured")
            return
            
        per_etf = amount / etf_count
        
        for etf in ETFS:
            if AUTO_APPROVE or confirm(f'Buy ${per_etf:,.2f} of {etf}?'):
                res = rb.orders.order_buy_fractional_by_price(etf, per_etf)
                if res is None:
                    logger.warning(f"Order Response for {etf}: None")
                else:
                    logger.info(f"Order Response for {etf}: {res.get('state')} - {res}")

    def make_picked_buys(amount: float):
        if amount <= 0:
            logger.info("No funds allocated to picked stocks")
            return
            
        if df.empty:
            logger.warning("No stock picks available")
            return
            
        total_agg_value = df['AggValue'].sum()
        if total_agg_value == 0:
            logger.warning("Total aggregation value is zero, cannot allocate funds")
            return
            
        for _, row in df.iterrows():
            symbol = row['Symbol']
            allocation = (row['AggValue'] / total_agg_value) * amount
            
            # Sentiment analysis check
            if USE_SENTIMENT_ANALYSIS:
                logger.info(f"\n{'='*60}")
                logger.info(f"SENTIMENT ANALYSIS FOR BUYING {symbol}")
                logger.info(f"{'='*60}")
                
                sentiment_result = get_sentiment_recommendation(symbol, "buy")
                
                logger.info(f"Recommendation: {sentiment_result['recommendation']}")
                logger.info(f"Confidence: {sentiment_result['confidence']:.1f}%")
                logger.info(f"Reasoning: {sentiment_result['reasoning']}")
                logger.info(f"{'='*60}\n")
                
                # Skip if sentiment says NO
                if sentiment_result['recommendation'] == "NO":
                    logger.info(f"Skipping purchase of {symbol} based on sentiment analysis (NO recommendation)")
                    continue
            
            if AUTO_APPROVE or confirm(f'Buy ${allocation:,.2f} of {symbol}? (Weight: {row["AggValue"]/total_agg_value:.1%})'):
                res = rb.orders.order_buy_fractional_by_price(symbol, allocation)
                if res is None:
                    logger.warning(f"Order Response for {symbol}: None")
                else:
                    logger.info(f"Order Response for {symbol}: {res.get('state')}")

    etf_amount, stock_amount = calculate_allocations()
    logger.info(f"Allocation: ${etf_amount:,.2f} to ETFs ({INDEX_PCT:.0%}), ${stock_amount:,.2f} to picked stocks ({(1-INDEX_PCT):.0%})")
    
    if etf_amount > 0 and (AUTO_APPROVE or confirm(f'Buy ETFs (${etf_amount:,.2f})?')):
        make_etf_buys(etf_amount)
    
    if stock_amount > 0 and (AUTO_APPROVE or confirm(f'Buy Picked Stocks (${stock_amount:,.2f})?')):
        make_picked_buys(stock_amount)


def wipe_data():
    if confirm(f'Wipe Data Directory ?'):
        for f in os.listdir(DATA_DIRECTORY):
            fname = '/'.join([DATA_DIRECTORY,f])
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
        logger.info("SENTIMENT ANALYSIS ENABLED")
        logger.info("="*60)
    
    if not AUTO_APPROVE and not confirm("Wipe data directory and generate new picks?"):
        logger.info("Operation cancelled by user")
        return
    
    try:
        wipe_data()
        update_valuations()
        add_funds_to_account()
        df = generate_daily_undervalued_stocks()
        make_buys(df) 
        make_sales()
    except Exception as e:
        logger.error(f"Error in daily strategy: {e}")
        if not AUTO_APPROVE:
            input("Press Enter to exit...")


def get_available_cash() -> float:
    cash = float(rb.account.build_user_profile().get('cash', 0))
    
    try:
        open_orders = rb.orders.get_all_open_stock_orders()
        committed_cash = 0.0
        
        def process_market_order(order):
            amount_fields = [
                ('executed_notional', 'amount'),
                ('total_notional', 'amount'),
                ('dollar_based_amount', 'amount')
            ]
            
            for field, subfield in amount_fields:
                if order.get(field) and order[field].get(subfield):
                    return float(order[field][subfield])
            return 0.0
            
        def process_limit_order(order):
            quantity = float(order.get('quantity', 0))
            price = float(order.get('price', 0))
            return quantity * price
            
        order_processors = {
            'market': process_market_order,
            'limit': process_limit_order
        }
        
        for order in open_orders:
            if order.get('side') != 'buy' or order.get('state') not in ['confirmed', 'queued', 'unconfirmed']:
                continue
                
            order_type = order.get('type')
            if order_type == 'market' and order.get('extended_hours', True):
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
    login()
    CASH_AVAILABLE = get_available_cash()
    run_daily_strat()


if __name__ == "__main__": 
    main()