from stock import Stock
import networkx as nx
from selenium import webdriver
from bs4 import BeautifulSoup
import seaborn as sns
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import argparse



def find_scores(G:nx.Graph, starters:list[Stock]) -> list[Stock]:
    scores = []
    list(map(lambda x: add_parent_node(G, x, scores), starters))
    return sorted(scores, key=lambda x: x[1])


def add_parent_node(G: nx.Graph, n: Stock, scores: list[tuple]) -> list[tuple]:
    root, children = n.symbol, list(map(lambda x: Stock(x), list(n.get_related())))
    G.add_node(root)
    #print("compiling general market perception data on:", root)
    children_syms = [i.symbol for i in children if i.symbol != root]
    list(map(lambda x: G.add_node(x), children_syms))
    list(map(lambda x: G.add_edge(x, root), children_syms))
    scores.append((root, n.p_score()))
    list(map(lambda x: add_child_node(x, scores), children))
    #print("\n")
    return scores


def add_child_node(n:Stock, scores:list[tuple]) -> list[tuple]:
    entry = (n.symbol, n.p_score())
    if entry not in scores:
        #print(f"\t{n.symbol} mentioned in article, pulling data..")
        scores.append(entry)
    return scores


screener_url = 'https://www.investing.com/stock-screener/'


urls = [
'top-stock-gainers',
'top-stock-losers',
'most-active-stocks',
'52-week-low',
'52-week-high'    
]


def interpret_stock_category(info:str,default_urls:list[str]=urls):
    base = 'https://www.investing.com/equities/'
    assert len(info.split(' ')) == 1, 'Use one word description please'
    key_words = [i.split('-') for i in default_urls]
    similar = [i for i in key_words if info in i]
    if len(similar) == 1:
        return base + '-'.join(similar[0])
    elif not similar:
        print('Try Another Description...')
        return
    print('Choose Best Description:')
    similar = [(e,'-'.join(i)) for e,i in enumerate(similar)]
    [print(i) for i in similar]
    print('\t Input Number: \n')
    ans=int(input().strip())
    return base + list(filter(lambda x: ans in x,similar))[0][1]


def find_tickers_on_webpage(url:str) -> list[str]:
    driver=webdriver.Chrome('/usr/bin/chromedriver')
    driver.get(url)
    soup = BeautifulSoup(driver.page_source,features="lxml")
    data = set(filter(lambda x: x != '' and len(x) > 1, [''.join([j for j in i.getText() if j.isupper()])  for i in soup.find_all('td')]))
    return data

def generate_tickers(info:str):
    cate = interpret_stock_category(info)
    return  find_tickers_on_webpage(cate) if cate else None

def pick_stocks(Graph:nx.Graph,seed_tickers:list[str],show:bool=False) -> list[Stock]:
    seed_stocks = list(map(lambda x: Stock(x) if isinstance(x,str) else x ,seed_tickers))
    #print(f"Initializing Program Data ... \n")
    scores = find_scores(Graph, seed_stocks)
    raw = list(map(lambda x: x[1], scores))
    good_thresh, avg_thresh, trash_thresh = np.mean(raw) + np.std(raw), np.mean(raw), 0

    def bound_data(data: list[int or float], lb: float or None, ub: float or None):
        if ub and not lb:
            return list(
                filter(
                    lambda x: x != None,
                    list(map(lambda x: x[0] if x[1] <= ub else None, data)),
                )
            )
        if lb and not ub:
            return list(
                filter(
                    lambda x: x != None,
                    list(map(lambda x: x[0] if x[1] >= lb else None, data)),
                )
            )
        if lb and ub:
            return list(
                filter(
                    lambda x: x != None,
                    list(
                        map(lambda x: x[0] if x[1] > lb and x[1] <= ub else None, data)
                    ),
                )
            )

    reds, oranges, yellows, greens = (
        bound_data(scores, lb=None, ub=trash_thresh),
        bound_data(scores, lb=trash_thresh, ub=avg_thresh),
        bound_data(scores, lb=avg_thresh, ub=good_thresh),
        bound_data(scores, lb=good_thresh, ub=None),
    )
    if show:
        pos = nx.spring_layout(Graph)
        nx.draw_networkx_nodes(Graph, pos, nodelist=reds, node_color="red")
        nx.draw_networkx_nodes(Graph, pos, nodelist=oranges, node_color="orange")
        nx.draw_networkx_nodes(Graph, pos, nodelist=yellows, node_color="yellow")
        nx.draw_networkx_nodes(Graph, pos, nodelist=greens, node_color="green")
        nx.draw_networkx_edges(Graph, pos, width=1.0, alpha=0.5)
        nx.draw_networkx_labels(Graph, pos, font_size=10, font_color="black")
        plt.tight_layout()
        plt.axis("off")
        plt.show()
    return greens

def show_stock_pick_analysis(stock:Stock, det:int=150) -> None:
    print(f"Selected: {stock.symbol} ~ downloading data..")
    data, ticker, related = stock.get_data(), stock.symbol, list(stock.get_related())
    print(f"\nRecent news headlines mentioning {ticker} \n {'-'*det}"), [
        print(i) for i in stock.get_headlines()
    ], print("-" * det), print(f"\nAlso mentions: \t {related} \n")    
    df=mk_stock_dataframe(ticker,related,data)
    plot_data(df)


def plot_data(df):
    sns.lineplot(df)
    plt.show()    
    
def mk_stock_dataframe(ticker:str,related:list[str],data):
    df_analysis = pd.DataFrame(columns=[ticker, *related])
    df_analysis[ticker] = data["Close"]
    for c in df_analysis.columns:
        dat = Stock(c).get_data()['Close']
        df_analysis[c] = dat
    return df_analysis



def run(G: nx.Graph,i_stocks:list[str],depth:int) -> list[str]:
    stocks = list(map(lambda x: Stock(x), pick_stocks(G,i_stocks,show=True)))   
    for i in range(1,depth):
        stocks = list(set(list(map(lambda x: Stock(x), pick_stocks(G,stocks,show=True)))))
    print(f"\n BEST PERCIVED STOCKS SIMILAR TO {i_stocks} \n {[i.symbol for i in stocks]}")         
    list(map(lambda x: show_stock_pick_analysis(x),stocks))
    return sorted([(i.symbol,i.p_score()) for i in stocks],key=lambda x:x[1],reverse=True)


def main():
    parser = argparse.ArgumentParser(description='Find General Market Perceptions of selected and related Stocks in various News Publications')
    parser.add_argument('--l',type=str)  
    parser.add_argument('--r',type=int)
    args = parser.parse_args()
    initial_stocks = list(generate_tickers(args.l)) if args.l else ['TSLA']
    print(f'Initial Seed Stocks: \n \t {initial_stocks} \n')
    recursion_depth=args.r if args.r else 1
    G = nx.Graph()
    Chosen=run(G,initial_stocks,recursion_depth)
    print('Best Stocks According to Recent News ~ (stock_ticker,perception_score):\n')
    [print(i) for i in Chosen]


if __name__ == "__main__":
    main()

