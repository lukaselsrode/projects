import aiohttp
import asyncio
import yfinance as yf
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


def get_news_for_tickers(tickers: List[str], max_articles: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch recent news for multiple tickers.
    
    Args:
        tickers (List[str]): List of stock ticker symbols
        max_articles (int): Maximum number of articles per ticker
        
    Returns:
        Dict[str, List[Dict[str, Any]]]: {date: [{'ticker': str, 'news': Dict}]}
    """
    result = {}
    
    for ticker in tickers:
        try:
            ticker_obj = yf.Ticker(ticker)
            news_items = ticker_obj.news[:max_articles]
            
            for item in news_items:
                content = item.get('content', {})
                if not content:
                    continue
                    
                # Get the publication date, fallback to current time if not available
                pub_date = content.get('pubDate', '')
                if not pub_date:
                    pub_date = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                
                # Format the date to match your reddit sentiment format (MM-DD-YYYY)
                try:
                    date_obj = datetime.strptime(pub_date, '%Y-%m-%dT%H:%M:%SZ')
                    formatted_date = date_obj.strftime('%m-%d-%Y')
                except:
                    formatted_date = datetime.utcnow().strftime('%m-%d-%Y')
                
                if formatted_date not in result:
                    result[formatted_date] = []
                    
                result[formatted_date].append({
                    'ticker': ticker,
                    'news': {
                        'title': content.get('title', 'No title'),
                        'publisher': content.get('provider', {}).get('displayName', 'Unknown'),
                        'link': content.get('canonicalUrl', {}).get('url', ''),
                        'summary': content.get('summary', ''),
                        'pub_date': pub_date
                    }
                })
                
        except Exception as e:
            print(f"Error fetching news for {ticker}: {str(e)}")
    
    # Sort by date (newest first)
    return dict(sorted(result.items(), reverse=True))
