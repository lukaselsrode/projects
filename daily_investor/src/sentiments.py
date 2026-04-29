import aiohttp
import asyncio
import time
import random
import yfinance as yf
import robin_stocks.robinhood as rb
from datetime import datetime, timedelta
from typing import Dict, Any, List

async def fetch(session, date):
    try:
        async with session.get(f'https://api.tradestie.com/v1/apps/reddit?date={date}') as r:
            r.raise_for_status()
            return date, await r.json()
    except Exception as e:
        print(f"Error for {date}: {e}")
        return date, None

async def get_reddit_sentiments(days=7):
    dates = [(datetime.now() - timedelta(days=i)).strftime('%m-%d-%Y') 
             for i in range(min(days, 7))]
    
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[fetch(session, d) for d in dates])
        return dict(results)

def get_reddit_sentiments_sync(days=7):
    return asyncio.run(get_reddit_sentiments(days))

def reddit_sentiments_for_tickers(tickers, days=7):
    """Get sentiment data for specific tickers, ensuring no duplicates per day.
    
    Args:
        tickers (list/set): List of ticker symbols to filter for
        days (int): Number of days of data to fetch (max 7)
        
    Returns:
        dict: {date: [ticker_data]}, with no duplicate tickers per date
    """
    ticker_set = set(tickers)
    rv = {}
    
    for day, sentiment_list in get_reddit_sentiments_sync(days).items():
        seen_tickers = set()
        for data in sentiment_list:
            ticker = data.get('ticker')
            if ticker in ticker_set and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                if day not in rv:
                    rv[day] = [data]
                else:
                    rv[day].append(data)
    return rv



def get_robinhood_news_fallback(ticker: str, max_articles: int = 3) -> List[Dict[str, Any]]:
    """
    Fallback to Robinhood news API when yfinance is rate limited
    Returns news in the same format as yfinance for consistency
    Note: Only works after Robinhood login, returns empty during data generation
    """
    try:
        # Check if Robinhood is logged in (avoid errors during data generation)
        try:
            rb.robinhood.load_account_profile()
        except:
            # Not logged in yet, return empty during data generation
            return []
        
        # Get news from Robinhood (fixed API path)
        news_items = rb.robinhood.get_news(ticker) or []
        
        # Convert Robinhood format to match yfinance format
        formatted_news = []
        for item in news_items[:max_articles]:
            formatted_item = {
                'title': item.get('title', ''),
                'publisher': item.get('source', {}).get('name', 'Robinhood'),
                'link': item.get('url', ''),
                'summary': item.get('summary', item.get('preview_text', '')),
                'pub_date': item.get('published_at', ''),
                'formatted_date': item.get('published_at', ''),
                'api_source': 'robinhood'
            }
            formatted_news.append(formatted_item)
        
        return formatted_news
        
    except Exception as e:
        print(f"Robinhood news fallback failed for {ticker}: {str(e)[:50]}")
        return []


def get_news_for_tickers_by_symbol(
    tickers: List[str],
    max_articles: int = 3
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Returns:
        { 'AAPL': [ {title, publisher, link, summary, pub_date, formatted_date}, ... ], ... }
    """
    result: Dict[str, List[Dict[str, Any]]] = {}
    
    # Filter out low-volume stocks (unlikely to have news anyway)
    # This reduces API calls dramatically for penny stocks and illiquid securities
    high_volume_tickers = []
    for ticker in tickers:
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info
            volume = info.get('averageVolume', 0) or info.get('volume', 0) or 0
            # Only fetch news for stocks with decent trading volume
            if volume and volume > 500000:  # 500k+ daily volume (more aggressive filtering)
                high_volume_tickers.append(ticker)
            else:
                result[ticker] = []  # Empty news for low-volume stocks
        except:
            result[ticker] = []  # Empty news if we can't get volume
    
    print(f"News filtering: {len(tickers)} total tickers → {len(high_volume_tickers)} high-volume tickers (will fetch news)")
    
    # Process in smaller batches to avoid rate limiting
    batch_size = 10  # Reduced from 20 to be more conservative
    filtered_tickers = high_volume_tickers  # Use filtered list
    print(f"Fetching news for {len(filtered_tickers)} high-volume tickers in batches of {batch_size}...")
    
    for i in range(0, len(filtered_tickers), batch_size):
        batch = filtered_tickers[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(filtered_tickers) + batch_size - 1) // batch_size
        
        print(f"Processing news batch {batch_num}/{total_batches} ({len(batch)} tickers)...")
        
        for ticker in batch:
            result[ticker] = []
            max_retries = 3
            news_items = []
            
            for attempt in range(max_retries):
                try:
                    # Exponential backoff: 1s, 2s, 4s between retries
                    if attempt > 0:
                        backoff_time = (2 ** attempt) + random.uniform(0, 1)  # Add jitter
                        print(f"BACKOFF:yfinance:{ticker}: Waiting {backoff_time:.1f}s before retry {attempt + 1}")
                        time.sleep(backoff_time)
                    
                    ticker_obj = yf.Ticker(ticker)
                    news_items = (ticker_obj.news or [])[:max_articles]
                    if news_items:  # If we got news, break out of retry loop
                        break
                    elif attempt == max_retries - 1:  # Last attempt and still no news
                        print(f"WARNING:yfinance:{ticker}: No news available (this is normal for some stocks)")
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'rate limited' in error_msg or 'too many requests' in error_msg:
                        if attempt < max_retries - 1:
                            # Try Robinhood fallback on rate limit
                            print(f"FALLBACK:yfinance:{ticker}: Rate limited, trying Robinhood news...")
                            time.sleep(1)  # Brief pause before fallback
                            robinhood_news = get_robinhood_news_fallback(ticker, max_articles)
                            if robinhood_news:
                                print(f"SUCCESS:yfinance:{ticker}: Robinhood fallback found {len(robinhood_news)} articles")
                                news_items = robinhood_news
                                break
                            else:
                                # No Robinhood news, continue with backoff
                                backoff_time = (2 * (1.5 ** attempt)) + random.uniform(0, 1)  # Less aggressive
                                print(f"RATE_LIMIT:yfinance:{ticker}: No Robinhood news. Waiting {backoff_time:.1f}s before retry {attempt + 1}")
                                time.sleep(backoff_time)
                                continue
                        else:
                            print(f"FALLBACK:yfinance:{ticker}: Final attempt, trying Robinhood news...")
                            robinhood_news = get_robinhood_news_fallback(ticker, max_articles)
                            if robinhood_news:
                                print(f"SUCCESS:yfinance:{ticker}: Robinhood fallback found {len(robinhood_news)} articles")
                                news_items = robinhood_news
                            else:
                                print(f"ERROR:yfinance:{ticker}: Both APIs failed, giving up")
                    elif 'failed to retrieve news' in error_msg:
                        if attempt == max_retries - 1:  # Only print on final attempt
                            print(f"FALLBACK:yfinance:{ticker}: Failed to retrieve, trying Robinhood news...")
                            robinhood_news = get_robinhood_news_fallback(ticker, max_articles)
                            if robinhood_news:
                                print(f"SUCCESS:yfinance:{ticker}: Robinhood fallback found {len(robinhood_news)} articles")
                                news_items = robinhood_news
                            else:
                                print(f"ERROR:yfinance:{ticker}: Failed to retrieve news and received faulty response instead.")
                        else:
                            print(f"RETRY:yfinance:{ticker}: Attempt {attempt + 1} failed, retrying...")
                    else:
                        if attempt == max_retries - 1:  # Only print on final attempt
                            print(f"FALLBACK:yfinance:{ticker}: Error occurred, trying Robinhood news...")
                            robinhood_news = get_robinhood_news_fallback(ticker, max_articles)
                            if robinhood_news:
                                print(f"SUCCESS:yfinance:{ticker}: Robinhood fallback found {len(robinhood_news)} articles")
                                news_items = robinhood_news
                            else:
                                print(f"ERROR:yfinance:{ticker}: {str(e)}")
                    continue
            
            # Add small delay between tickers to avoid rate limiting
            time.sleep(random.uniform(0.1, 0.3))  # Reduced for faster processing
        
        # Add delay between batches
        if i + batch_size < len(filtered_tickers):
            print(f"Batch {batch_num} completed, waiting 2 seconds before next batch...")
            time.sleep(2)  # Reduced from 5 seconds
        
        # Process news items if we got any
        for item in news_items:
            # Handle both yfinance and Robinhood formats
            if item.get("api_source") == "robinhood":
                # Robinhood format (already processed)
                pub_date = item.get("pub_date", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
                formatted_date = item.get("formatted_date", datetime.utcnow().strftime("%m-%d-%Y"))
                
                result[ticker].append({
                    "title": item.get("title", "No title"),
                    "publisher": item.get("publisher", "Robinhood"),
                    "link": item.get("link", ""),
                    "summary": item.get("summary", ""),
                    "pub_date": pub_date,
                    "formatted_date": formatted_date,
                })
            else:
                # Original yfinance format processing
                content = item.get("content", {}) or {}
                if not content:
                    continue

                pub_date = content.get("pubDate") or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

                # Keep both raw and formatted date (optional but often useful)
                try:
                    date_obj = datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%SZ")
                    formatted_date = date_obj.strftime("%m-%d-%Y")
                except Exception:
                    formatted_date = datetime.utcnow().strftime("%m-%d-%Y")

                result[ticker].append({
                    "title": content.get("title", "No title"),
                    "publisher": (content.get("provider") or {}).get("displayName", "Unknown"),
                    "link": (content.get("canonicalUrl") or {}).get("url", ""),
                    "summary": content.get("summary", ""),
                    "pub_date": pub_date,
                    "formatted_date": formatted_date,
                })

    return result