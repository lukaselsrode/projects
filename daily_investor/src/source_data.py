import os
import requests
import datetime
import csv
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from util import get_investment_ratios
import robin_stocks.robinhood as rb
from util import (
    get_investment_ratios,
    IGNORE_NEGATIVE_PE,
    IGNORE_NEGATIVE_PB,
    DIVIDEND_THRESHOLD,
    METRIC_THRESHOLD,
)

load_dotenv()

WIKIPEDIA_REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
DATA_DIRECTORY = os.path.join("/".join(os.path.abspath(__file__).split("/")[:-2]), "data")

def generate_daily_buy_list():
    def fetch_fundamentals():
        def gen_symbols_list():
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
            
            # Define Wikipedia pages to scrape for index components
            INDEX_URLS = [
                'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
                'https://en.wikipedia.org/wiki/Nasdaq-100',
                'https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average'
            ]
            
            # Get components from all indices and combine into a single set
            index_components = set()
            for url in INDEX_URLS:
                index_components.update(get_table_data(url))
            
            # Get Robinhood data and combine into a single set
            robinhood_sources = [
                rb.get_top_movers_sp500("down"),
                rb.get_top_movers(),
                rb.get_top_100(),
                rb.get_top_movers_sp500("up")
            ]
            robinhood_tickers = {
                item["symbol"] 
                for source in robinhood_sources 
                for item in source
            }
            
            # Combine all sources and filter valid symbols
            return {
                symbol 
                for symbol in index_components.union(robinhood_tickers)
                if symbol and isinstance(symbol, str)
            }

 
        # Fetch basic fundamentals only for initial filtering, excluding any [None] results
        return {
            symbol: result 
            for symbol in gen_symbols_list() 
            for result in [rb.get_fundamentals(symbol)] 
            if result != [None]
        }

    def filter_by_underevaluation(fundamentals):
        def calculate_value_metric(stock_data):
            try:
                if not stock_data or not isinstance(stock_data, list) or not stock_data[0]:
                    return False
                
                stock = stock_data[0]  # Access the first element of fundamentals data
                
                # Check for required fields
                if not all(key in stock for key in ['industry', 'sector', 'volume', 'pe_ratio', 'pb_ratio']):
                    return False
                
                # Skip if both industry and sector are missing, or volume is zero
                if (not stock.get('industry') and not stock.get('sector')) or not int(float(stock.get('volume', 0))):
                    return False
                
                # Get thresholds based on sector/industry
                pe_threshold, pb_threshold = get_investment_ratios(stock.get("sector"), stock.get("industry"))
                
                # Safely parse ratios with error handling
                try:
                    pe_ratio = float(stock.get("pe_ratio") or float("inf"))
                    pb_ratio = float(stock.get("pb_ratio") or float("inf"))
                    dividend_yield = float(stock.get("dividend_yield") or 0)
                except (ValueError, TypeError):
                    return False
                
                # Skip if negative ratios should be ignored
                if (pe_ratio < 0 and IGNORE_NEGATIVE_PE) or (pb_ratio < 0 and IGNORE_NEGATIVE_PB):
                    return False
                
                # Calculate value metric components
                pe_component = (pe_threshold / pe_ratio) if (pe_ratio < pe_threshold and pe_ratio > 0) else 0
                pb_component = (pb_threshold / pb_ratio) if (pb_ratio < pb_threshold and pb_ratio > 0) else 0
                div_component = (dividend_yield / DIVIDEND_THRESHOLD) if (dividend_yield > DIVIDEND_THRESHOLD) else 0
                
                # Calculate final value metric
                value_metric = round(pe_component + pb_component + div_component, 3)
                
                return value_metric if value_metric > METRIC_THRESHOLD else False
                
            except Exception as e:
                print(f"Error calculating value metric for stock: {str(e)}")
                return False

        # Only include stocks that pass the undervaluation criteria, store with value_metric
        return {
            symbol: {"fundamentals": data, "value_metric": calculate_value_metric(data)}
            for symbol, data in fundamentals.items()
            if calculate_value_metric(data)
        }

    def fetch_additional_data(stock_data, symbol):
        # Get buy/sell ratings for the stock
        stock_data["ratings"] = {"buy_to_sell_ratio": None}
        ratings = rb.stocks.get_ratings(symbol)
        if ratings.get('summary'):
            summary = ratings.get('summary')
            stock_data["ratings"]["buy_to_sell_ratio"] = summary.get('num_buy_ratings') / (ratings.get('num_sell_ratings') or 1)
        return stock_data

    def get_daily_undervalued_stocks():
        basic_fundamentals = fetch_fundamentals()
        undervalued_stocks = filter_by_underevaluation(basic_fundamentals)
        # Fetch additional data for each undervalued stock
        return {
            symbol: fetch_additional_data({"fundamentals": data["fundamentals"], "value_metric": data["value_metric"]}, symbol)
            for symbol, data in sorted(
                undervalued_stocks.items(),
                key=lambda x: x[1]["value_metric"],
                reverse=True
            )
        }

    def store_daily_stocks(data):
        filename = os.path.join(
            DATA_DIRECTORY,
            f"picks_{str(datetime.datetime.now().strftime('%Y-%m-%d')).replace('-', '_')}.csv",
        )
        with open(filename, "w+", newline="") as file:
            csvwriter = csv.writer(file)
            csvwriter.writerow(["Symbol", "Value", "BuySellRatio", "AggValue"])
            for symbol, stock_data in data.items():
                value_metric = stock_data["value_metric"]
                if (buy_to_sell_ratio := stock_data["ratings"]["buy_to_sell_ratio"]) is not None:
                    csvwriter.writerow([
                        symbol,
                        value_metric,
                        buy_to_sell_ratio,
                        value_metric * buy_to_sell_ratio,  # Aggregated value based on value_metric and buy_to_sell_ratio
                    ])
        print(f"Stored Picks @ {filename}")

    store_daily_stocks(get_daily_undervalued_stocks())

def aggragate_picks():
    pick_dfs = [pd.read_csv(os.path.join(DATA_DIRECTORY,picks)) for picks in os.listdir(DATA_DIRECTORY)]
    df_all =  pd.concat(pick_dfs,axis=0)
    df_all = df_all.drop_duplicates(subset=['Symbol']).sort_values(by='AggValue',ascending=False)
    return df_all

def generate_daily_undervalued_stocks():
    generate_daily_buy_list()
    aggragate_picks()

