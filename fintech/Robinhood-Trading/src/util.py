import robin_stocks as rb
import metrics
import json
from stock import Stock

# login to accout
# TODO - json file


def login():
    f = open('../data/client_secrets.json',)
    data = json.load(f)
    username, password = data['client'], data['client_secret']
    rb.robinhood.login(username, password)
    f.close()
    return

# TODO - schedular to make it run every market day
# https: // datatofish.com/python-script-windows-scheduler/

"""
# Test tickers
#top_100 = [Stock(i['symbol']) for i in robin_stocks.get_top_100()]
top_movers = [Stock(i['symbol']) for i in robin_stocks.get_top_movers()]
top_down = [Stock(i['symbol'])
            for i in robin_stocks.get_top_movers_sp500('down')]
reports_soon = [Stock(i['symbol']) for i in robin_stocks.get_watchlist_by_name(
    'Upcoming Earnings')['results']]
saved = [Stock(i['symbol']) for i in robin_stocks.get_watchlist_by_name(
    'My First List')['results']]
arg = [Stock(i['symbol'])
       for i in robin_stocks.get_watchlist_by_name('Agriculture')['results']]
eng = [Stock(i['symbol']) for i in robin_stocks.get_watchlist_by_name(
    'Energy & Water')['results']]
holding = [Stock(i)
           for i in list(robin_stocks.account.build_holdings().keys())]
swingers = [Stock(i['symbol']) for i in robin_stocks.get_watchlist_by_name(
    'Daily Movers')['results']]

"""



TO_SELL = {
    'SPCE': 34,

}


def check_to_sell(selling=TO_SELL):
    holdings = robin_stocks.build_holdings()
    for k, v in selling.items():
        stock = Stock(k)
        # if meets price then sell
        if stock.price > v:
            qsell = float(holdings[k]['quantity'])
            robin_stocks.order(
                k, quantity=qsell, orderType='market', side='sell', trigger='immediate')
            print(f'{stock.symbol} SOLD at {stock.price}')
    return


def filterby_long_term_metrics(stocks):
    rv = []
    for s in stocks:
        # try getting a metric for a stock
        try:
            cagr, sratio = metrics.calc_cagr(s), metrics.calc_sharpe_ratio(s)
            if sratio > 0 and cagr > 0:
                rv.append(s)
        except:
            pass
    return rv


def filter_by_price(stocks, price_celling):
    rv = []
    for s in stocks:
        if s.update() <= price_celling:
            rv.append(s)
    return rv
