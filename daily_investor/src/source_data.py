import os
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import robin_stocks.robinhood as rb
from util import (
    get_investment_ratios,
    store_data_as_csv,
    read_data_as_pd,
    IGNORE_NEGATIVE_PE,
    IGNORE_NEGATIVE_PB,
    DIVIDEND_THRESHOLD,
    METRIC_THRESHOLD,
)
from sentiments import reddit_sentiments_for_tickers, get_news_for_tickers_by_symbol

load_dotenv()

# Define Wikipedia pages to scrape for index components
INDEX_URLS = [
    'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
    'https://en.wikipedia.org/wiki/Nasdaq-100',
    'https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average',
    'https://en.wikipedia.org/wiki/List_of_S%26P_400_companies',      # S&P MidCap 400
    'https://en.wikipedia.org/wiki/Russell_2000_Index',                    # Russell 2000
]
        
WIKIPEDIA_REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
DATA_DIRECTORY = os.path.join("/".join(os.path.abspath(__file__).split("/")[:-2]), "data")


def gen_symbols_list(force_refresh: bool) -> list[str]:    
    if not force_refresh:
        stored_symbols = read_data_as_pd('stock_tickers')
        if stored_symbols is not None and not stored_symbols.empty:
            return stored_symbols['symbol'].tolist()
    
    # Aux function to scrape wikipedia tables
    def get_table_data(url):
        # requires user agent now.. 
        response = requests.get(url, headers=WIKIPEDIA_REQUEST_HEADERS)
        print('Extracting table data from', url)
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', {'class': 'wikitable sortable'})
        rows = table.find_all('tr')[1:]
        data = []
        for row in rows:
            cols = row.find_all('td')
            cols = list(set([ele.text.strip() for ele in cols if ele.text.strip() and all(i.isupper() for i in ele.text.strip())]))
            data += cols
        return set(data)
    

    # Get components from all indices and combine into a single set
    index_components = set()
    for url in INDEX_URLS:
        index_components.update(get_table_data(url))
    
    # Get Robinhood data from multiple sources
    robinhood_sources = [
        rb.get_top_movers_sp500("down"),
        rb.get_top_movers(),
        rb.get_top_100(),
        rb.get_top_movers_sp500("up")
    ]
    
    # Add stocks from Robinhood market tags for broader coverage
    robinhood_market_tags = [
        '100-most-popular',
        'upcoming-earnings',
        'new-on-robinhood',
        'technology',
        'finance',
        'healthcare',
        'energy',
    ]
    
    print(f"Fetching stocks from {len(robinhood_market_tags)} Robinhood market tags...")
    for tag in robinhood_market_tags:
        try:
            tag_stocks = rb.get_all_stocks_from_market_tag(tag)
            if tag_stocks:
                robinhood_sources.append(tag_stocks)
                print(f"  ✅ {tag}: {len(tag_stocks)} stocks")
                time.sleep(0.5)  # Rate limit between API calls
            else:
                print(f"  ⚠️ {tag}: No stocks returned")
        except Exception as e:
            print(f"  ❌ {tag}: Error fetching - {str(e)[:50]}")
    
    # Validate tickers before including them
    all_robinhood_stocks = []
    invalid_count = 0
    
    for source in robinhood_sources:
        for item in source:
            symbol = item.get("symbol")
            # Basic validation: must be string, not empty, reasonable length
            if (symbol and isinstance(symbol, str) and 
                len(symbol) >= 1 and len(symbol) <= 5 and
                symbol.isalpha() and symbol.isupper()):
                all_robinhood_stocks.append(symbol)
            else:
                invalid_count += 1
    
    print(f"Validated {len(all_robinhood_stocks)} Robinhood tickers, skipped {invalid_count} invalid symbols")
    
    robinhood_tickers = set(all_robinhood_stocks)
    
    # Combine all sources and filter valid symbols
    all_tickers = list([
        symbol 
        for symbol in index_components.union(robinhood_tickers)
        if symbol and isinstance(symbol, str)
    ])

    store_data_as_csv('stock_tickers',['symbol'], [[t] for t in all_tickers])
    return all_tickers


def get_classical_evaluation_metrics(symbol: str, stock_data) -> list:
    # Validate input types
    if not isinstance(stock_data, dict):
        print(f"Error: stock_data for {symbol} is not a dict: {type(stock_data)}")
        return
    
    stock = stock_data
    try:
        # Check for required fields, Skip if both industry and sector are missing, or volume is zero
        if not all(key in stock for key in ['industry', 'sector', 'volume', 'pe_ratio', 'pb_ratio']) or (not stock.get('industry') and not stock.get('sector')) or not int(float(stock.get('volume', 0))):       
            return
        
        # Get thresholds based on sector/industry
        pe_threshold, pb_threshold = get_investment_ratios(stock.get("sector"), stock.get("industry"))
        
        # Safely parse ratios with error handling
        pe_ratio_raw = stock.get("pe_ratio")
        pb_ratio_raw = stock.get("pb_ratio")
        dividend_yield = float(stock.get("dividend_yield") or 0)
        
        # Handle missing/invalid ratios
        pe_ratio = float(pe_ratio_raw) if pe_ratio_raw is not None and pe_ratio_raw != '' and str(pe_ratio_raw).lower() != 'nan' else None
        pb_ratio = float(pb_ratio_raw) if pb_ratio_raw is not None and pb_ratio_raw != '' and str(pb_ratio_raw).lower() != 'nan' else None

        
        # Skip if negative ratios should be ignored
        if (pe_ratio is not None and pe_ratio < 0 and IGNORE_NEGATIVE_PE) or (pb_ratio is not None and pb_ratio < 0 and IGNORE_NEGATIVE_PB):
            print('negative ratios')
            return
        
        # Calculate value metric components
        pe_component = (pe_threshold / pe_ratio) if (pe_ratio is not None and pe_ratio > 0 and pe_ratio < pe_threshold) else 0
        pb_component = (pb_threshold / pb_ratio) if (pb_ratio is not None and pb_ratio > 0 and pb_ratio < pb_threshold) else 0
        div_component = (dividend_yield / DIVIDEND_THRESHOLD) if (dividend_yield > DIVIDEND_THRESHOLD) else 0
        
        # Calculate final value metric
        value_metric = round(pe_component + pb_component + div_component, 3)

        # Get buy/sell ratings for the stock with better error handling
        buy_to_sell_ratio = None
        try:
            # Only call ratings API if we have a valid symbol
            if symbol and isinstance(symbol, str) and len(symbol) > 0:
                ratings = rb.stocks.get_ratings(symbol)
                # Handle None or invalid responses
                if ratings and isinstance(ratings, dict) and 'summary' in ratings:
                    summary = ratings.get('summary')
                    if summary and isinstance(summary, dict):
                        num_buy = summary.get('num_buy_ratings', 0)
                        num_sell = ratings.get('num_sell_ratings', 1)  # Get from ratings level
                        buy_to_sell_ratio = num_buy / (num_sell or 1)
                    else:
                        # No summary data available
                        pass
                else:
                    # No ratings data available (common for many stocks)
                    pass
            else:
                # Invalid symbol, skip ratings
                pass
        except Exception as e:
            # Ratings API errors are common, don't spam logs
            if "404" not in str(e) and "None" not in str(e):
                print(f"Warning: Could not get ratings for {symbol}: {str(e)[:50]}")
        
        data = [
            stock.get('industry'),
            stock.get('sector'),
            stock.get('volume'),
            pe_ratio,
            pb_ratio,
            dividend_yield,
            pe_component,
            pb_component,
            div_component,
            value_metric,
            buy_to_sell_ratio,
        ]

        return data

        
    except Exception as e:
        print(f"Error calculating value metric for stock {symbol}: {str(e)}")
        return


def get_robinhood_data(stocks : list[str], force_refresh: bool) -> pd.DataFrame:

    if not force_refresh:
        return read_data_as_pd('robinhood_data')
    rv=[]
    fundementals_data={}
    
    # Use batch API calls for better performance
    print(f"Fetching fundamentals for {len(stocks)} stocks using batch API...")
    
    # Process in batches of 50 to avoid API limits
    batch_size = 50
    total_batches = (len(stocks) + batch_size - 1) // batch_size
    
    for i in range(0, len(stocks), batch_size):
        batch = stocks[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        
        try:
            print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} stocks)...")
            rb_result = rb.get_fundamentals(batch)
            
            # Process batch results
            if rb_result and isinstance(rb_result, list):
                for item in rb_result:
                    if item and isinstance(item, dict) and 'symbol' in item:
                        symbol = item['symbol']
                        fundementals_data[symbol] = item
                    # None items are already filtered by robin_stocks library
            else:
                print(f"  ⚠️ Batch {batch_num} returned no data")
                
        except Exception as e:
            print(f"  ❌ Batch {batch_num} failed: {str(e)[:50]}")
            continue
    
    print(f"Successfully fetched fundamentals for {len(fundementals_data)} stocks")
    
    for symbol, data in fundementals_data.items(): 
        if value_metrics := get_classical_evaluation_metrics(symbol, data):
            value_metrics.insert(0,symbol)
            rv.append(value_metrics)

    store_data_as_csv(
        'robinhood_data',
        [
            'symbol',
            'industry',
            'sector',
            'volume',
            'pe_ratio',
            'pb_ratio',
            'dividend_yield',
            'pe_comp',
            'pb_comp',
            'div_comp',
            'value_metric',
            'buy_to_sell_ratio'
        ],
        rv
    )
    time.sleep(1)
    return read_data_as_pd('robinhood_data')


def get_reddit_data(stocks: list[str], days: int) -> pd.DataFrame:
    print(f"Getting Reddit Data from {days} back")
    raw_data = reddit_sentiments_for_tickers(stocks,days)
    for k,v in raw_data.items():
        print(f"{k} ==> {v}")
    return 


def get_news_data(stocks: list[str], max_num_articles: int, force_refresh: bool) -> pd.DataFrame:
    if force_refresh:
        news_by_symbol = get_news_for_tickers_by_symbol(stocks, max_articles=max_num_articles)
        news_df=pd.DataFrame(
            [{"symbol": sym, "news": articles} for sym, articles in news_by_symbol.items()]
        )
        store_data_as_csv(
            'news',
            ['symbol','news'],
            news_df
        )

    return read_data_as_pd('news')


def get_portfolio_data() -> pd.DataFrame:
    return


def get_data(
        refresh: bool,
) -> pd.DataFrame:
    tickers = gen_symbols_list(refresh)
    metrics = get_robinhood_data(tickers,refresh)
    news_df = get_news_data(tickers,1,refresh)
    
    # Handle None DataFrames
    if metrics is None or metrics.empty:
        print("Warning: No robinhood data available")
        return pd.DataFrame()
    
    # Merge metrics with news (handle None news_df)
    if news_df is not None and not news_df.empty:
        result = metrics.merge(news_df, on='symbol',how="left")
    else:
        result = metrics.copy()
    
    # Try to fetch and merge with reddit data if available
    try:
        reddit_df = read_data_as_pd('reddit')
        if reddit_df is None or reddit_df.empty:
            # Fetch reddit data if not cached
            print("Fetching reddit sentiment data...")
            reddit_data = reddit_sentiments_for_tickers(tickers, days=1)
            if reddit_data:
                reddit_df = pd.DataFrame([
                    {"symbol": sym, "reddit": data} 
                    for sym, data in reddit_data.items()
                ])
                store_data_as_csv('reddit', ['symbol', 'reddit'], reddit_df)
                print(f"Fetched reddit data for {len(reddit_df)} symbols")
        
        if reddit_df is not None and not reddit_df.empty:
            result = result.merge(reddit_df, on='symbol',how="left")
    except Exception as e:
        print(f"Warning: Could not fetch/merge reddit data: {e}")
    
    # Store the final aggregated data as the single source of truth
    if refresh and not result.empty:
        store_data_as_csv('agg_data','',result)
        time.sleep(1)
    
    # Always return the latest agg_data as the source of truth
    agg_data = read_data_as_pd('agg_data')
    return agg_data if agg_data is not None else result

if __name__ == "__main__":
    df=get_data(False)
    print(df)