# Lukas Elsrode - Calculation and data proecssing file
import numpy as np
import pandas as pd 
import matplotlib.pyplot as plt
import matplotlib

def get_prices(Stock):
    ''' returns np array of all-time closing prices
    '''
    df = Stock.get_data()
    return pd.to_numeric(df['Close'])

def show_prices(Stock):
    '''Plots prices as function of time
    '''
    prices = get_prices(Stock)
    dates = matplotlib.dates.date2num(prices.index)
    plt.plot(dates, prices)
    plt.title(Stock.symbol + 'Price vs. t')
    plt.savefig(Stock.symbol + 'Hist.png')
    return

# returns of every day
def return_series(Stock, show=False):
    '''returns a np array of returns from previous day
    '''
    series = get_prices(Stock)
    if series == None:
        return None

    shifted_series = series.shift(1, axis=0)
    rv = series/shifted_series - 1

    if show:
        rv.hist()
        plt.title('Daily Returns of ' + Stock.symbol)
        plt.show()
    return rv

# log of that daily return
def log_return_series(Stock, show=False):
    series = get_prices(Stock)
    shifted_series = series.shift(1, axis=0)
    rv = pd.Series(np.log(series/shifted_series))
    if show:
        rv.hist()
        plt.title('Daily Log Returns of ' + Stock.symbol)
        plt.show()
    return rv
# years since company tradable


def get_years_passed(Stock):
    series = get_prices(Stock)
    # curr and start date
    curr, start = series.index[-1], series.index[0]
    curr, start = str(curr), str(start)
    curr, start = curr.split('-'), start.split('-')
    curr[2], start[2] = curr[2][0:2], start[2][0:2]
    # double map lists and sum
    res = list(map(lambda c, s: int(c) - int(s), curr, start))
    fac = [1, 1/12, 1/365.25]
    return sum(list(map(lambda r, f: r*f, fac, res)))


def calc_annulized_volitilty(Stock):
    '''how volitile are daily earnings ?
    '''
    returns = log_return_series(Stock)
    years_past = get_years_passed(Stock)
    entries_per_year = returns.shape[0]/years_past
    return returns.std() * np.sqrt(entries_per_year)


def calc_cagr(Stock):
    '''Calculate Compounded annual growth rate
    '''
    series = get_prices(Stock)
    value_factor = series.iloc[-1] / series.iloc[0]
    year_past = get_years_passed(Stock)
    return (value_factor ** (1/year_past)) - 1


def calc_sharpe_ratio(Stock, benchmark_rate=1.1):
    '''Risk free rate of return 
    '''
    cagr = calc_cagr(Stock)
    volitily = calc_annulized_volitilty(Stock)
    return (cagr - benchmark_rate)/volitily





INFLATION_RATE=7.1  # Rate of inflation
BASE_RATE=3.0       # Base growth rate of S&NP500
MARGINAL_RATE=1.0   # The % amount we call our 'smallest increment'

# Benchmarks for ROI to sellout/cashout on - 'we've reached out target' 
BENCHMARKS = {
    'gamble': MARGINAL_RATE,
    'guess': BASE_RATE,
    'good': MARGINAL_RATE + BASE_RATE,
    'certrain':2*BASE_RATE,
}


def valid_cashout_return(roi,pi=INFLATION_RATE,description='gamble'):
    if roi - pi >= BENCHMARKS[description]:
        return True
    return False

