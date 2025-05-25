import os
import csv
import requests
import datetime
import logging
import pyotp
import pandas as pd
import robin_stocks.robinhood as rb
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from util import (
    get_investment_ratios,
    IGNORE_NEGATIVE_PE,
    IGNORE_NEGATIVE_PB,
    DIVIDEND_THRESHOLD,
    METRIC_THRESHOLD,
    SELLOFF_THRESHOLD,
    WEEKLY_INVESTMENT,
    ETFS
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
from util import get_investment_ratios



DATA_DIRECTORY = os.path.join("/".join(os.path.abspath(__file__).split("/")[:-2]), "data")
global CASH_AVAILABLE


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

def confirm(prompt_msg:str) -> bool:
    logger.info(f'{prompt_msg} [y/n]')
    return True if 'y' in input().strip().lower() else False

def generate_daily_buy_list():
    def fetch_fundamentals():
        def gen_symbols_list():
            def get_table_data(url):
                response = requests.get(url)
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
                logger.warning(f"Error calculating value metric for stock: {str(e)}")
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
        logger.info(f"Stored Picks @ {filename}")

    if confirm('Store Daily Undervalued Stocks ?'):
        store_daily_stocks(get_daily_undervalued_stocks())

def aggragate_picks():
    pick_dfs = [pd.read_csv(os.path.join(DATA_DIRECTORY,picks)) for picks in os.listdir(DATA_DIRECTORY)]
    df_all =  pd.concat(pick_dfs,axis=0)
    df_all = df_all.drop_duplicates(subset=['Symbol']).sort_values(by='AggValue',ascending=False)
    return df_all

def add_funds_to_account() -> None:
    if get_available_cash() < float(WEEKLY_INVESTMENT):
        available_cash = get_available_cash()
        amount_needed = float(WEEKLY_INVESTMENT) - available_cash
        if confirm(f"Not Enough Cash Available: ${available_cash:,.2f} < ${float(WEEKLY_INVESTMENT):,.2f}\nAdd ${amount_needed:,.2f} to reach weekly investment target?"):
            bank_accounts = rb.get_linked_bank_accounts()
            ach = bank_accounts[0].get('url') 
            resp = rb.deposit_funds_to_robinhood_account(ach, amount_needed)
            logger.info(f"Deposit response: {resp}")
            logger.info(f"Request To Deposit ${amount_needed:,.2f} : {resp.get('state')}")
    else:
        logger.info(f"Not Adding Funds To Account, Not Enough Cash Available: {get_available_cash()} > {WEEKLY_INVESTMENT}")
    
def sell(symbol:str,quantity:float):
    holdings = rb.build_holdings()
    assert symbol in holdings, f"Symbol {symbol} not found in portfolio holdings list"
    return rb.order_sell_market(symbol,quantity)

def make_sales():
    to_sell = {
        k:v
        for k, v in rb.build_holdings().items()
        # make a crappy stop loss check on same for profit 
        if abs(float(v.get("percent_change"))) > SELLOFF_THRESHOLD and k not in ETFS
    }
    if to_sell:
        for k,v in to_sell.items():
            s,q = k, float(v.get('quantity'))
            if confirm(f"Sell {q} of {s} ?"):
                res=sell(s,q)
                logger.info(f'Sell order response: {res}')
    logger.info('Sales completed')

def make_buys():
    
    def make_etf_buys():
        buy_price_etf = float(WEEKLY_INVESTMENT) / len(ETFS)
        for etf in ETFS:
            if confirm(f"Buy {buy_price_etf} of {etf}?"):
                res=rb.orders.order_buy_fractional_by_price(etf,buy_price_etf)
                logger.info(f"{etf} Buy Response: {res}")

    def make_picked_buys():
        # Get the aggregated picks with their AggValue
        picks_df = aggragate_picks()
        total_agg_value = picks_df['AggValue'].sum()
        
        if total_agg_value <= 0:
            logger.warning("No valid aggregation values found for picks")
            return
            
        # Get remaining cash
        remaining_cash = get_available_cash()
        logger.info(f"Remaining cash to invest: ${remaining_cash:,.2f}")
        
        for _, row in picks_df.iterrows():
            symbol = row['Symbol']
            # Calculate allocation based on AggValue weight
            allocation = (row['AggValue'] / total_agg_value) * remaining_cash
            
            # Confirm buy and place order with calculated amount
            if confirm(f'Buy ${allocation:,.2f} of {symbol}? (Weight: {row["AggValue"]/total_agg_value:.1%})'):
                res = rb.orders.order_buy_fractional_by_price(symbol, allocation)
                logger.info(f"Order Response for {symbol}: {res}")

    def reset_cash_available():
        global CASH_AVAILABLE
        CASH_AVAILABLE = get_available_cash()

    
    if confirm('Buy ETFs ?'):
        make_etf_buys()

    reset_cash_available()

    if confirm('Buy Picked Stocks ?'):
        make_picked_buys()
    

def wipe_data():
    if confirm(f'Wipe Data Directory ?'):
    # delete the direcotry then re-create it for futrure picks
        for f in os.listdir(DATA_DIRECTORY):
            fname = '/'.join([DATA_DIRECTORY,f])
            try:
                os.remove(fname)
                logger.debug(f'Removed file: {fname}')
            except Exception as e:
                logger.error(f'Error removing file {fname}: {e}')
        logger.info('Data Directory Cleared')


def run_daily_strat():
    date = datetime.datetime.now()
    logger.info(f'Running Automated Investment Strategy for {date}')
    wipe_data()
    generate_daily_buy_list()
    aggragate_picks()
    add_funds_to_account()
    make_buys() 
    make_sales()



def get_available_cash() -> float:
    # Get the current cash balance
    cash = float(rb.account.build_user_profile().get('cash', 0))
    
    # Get all open stock orders
    try:
        open_orders = rb.orders.get_all_open_stock_orders()
        # Calculate total amount committed to pending buy orders
        committed_cash = 0.0
        def process_market_order(order):
            # Check different possible amount fields in order of preference
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
        
        # Subtract committed cash from available cash
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