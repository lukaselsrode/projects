"""
stock.py ~ Contains implimentation of Stock Class
"""

import time
import yfinance as yf


BEARISH_WORDS,BULLISH_WORDS = [
    'Bearish',
    'Bear',
    'Downgrade',
    'dip',
    'Fall',
    'Pain',
    'shake-up',
    'layoff',
    'end',
    'crash',
    'worst',
    'bad',
    'strike',
    'low',
    'sell',
    'overvalue',
    'charges'
    'short',
    'antitrust',
    'anti-trust',
    'miss',
    'sue',
    'cut',
    'losing',
    'loss',
    'fight',
    'concern',
    'fell',
    'sell off',
    'nightmare',
    'cut',
    'takeover',
    'jobless',
    'regulator',
    'fear',
    'meltdown',
    'Plunging',
    'lag',
    'violate'
    'cancel',
    'profitable short',
    'tumble',
    'problem',
    'slowdown',
    'failure',
    'cold water',
    'pullback'
    ],[
        'rise',
        'bullish',
        'comeback',
        'dominate',
        'top',
        'buy',
        'long',
        'rally',
        'rallied',
        'undervalued',
        'best',
        'gain',
        'oppertunity',
        'cheap',
        'ambition',
        'invest now',
        'first',
        'optimism',
        'new',
        'more',
        'pick',
        'top',
        'live',
        'invented',
        'patent',
        'recipient',
        'bull',
        'promising',
        'right',
        'envy',
        'next',
        'settle',
        'pitch',
        'gain',
        'highlight',
        'jump',
        'rocket',
        'new low',
        'fantastic',
        'bright',
        'bull',
        'win',
        'high-yield',
        'blazing',
        'surefire',
        'buy',
        'long-term',
        'love',
        'responsible',
        'likes'
    ]



class Stock:
    def __init__(self, ticker):
        self.symbol,self.src = ticker.strip(),yf.Ticker(ticker.strip())
        self.price=self.info=self.data=self.news=None

    def update(self, latency=0.05):
        time.sleep(latency)
        return self.get_price()
    
    def price_stream(self, timer=10):
        start_time, end_time = time.perf_counter(), 0
        while (end_time - start_time) <= timer:
            yield self.update()
            end_time = time.perf_counter()
        else:
            yield None

    def get_info(self):
        self.info=self.src.info, self.src.actions, self.src.shares, self.src.earnings
        return self.info

    def get_news(self):
        self.news = self.src.news
        self.news = list(filter(lambda x: 'relatedTickers' in x.keys(), self.news))
        return list(map(lambda i: (i['title'],i['publisher'],i['relatedTickers']), self.news))
    
    def get_price(self):
        return 0
    
    def get_related(self):
        rv = []
        for r in self.get_news():
            rv.extend([i.replace('^','').replace('0P0001','').replace('.TO','').replace('=F','').replace('=X','') for i in r[2]] if r[2] not in rv else None)
        return set(rv)    
    
    def get_headlines(self):
        return list(map(lambda x: x[0],self.get_news()))
    
    def get_data(self):
        if not self.data:
            self.data = yf.download(self.symbol)
        return self.data

    def bearish_count(self,text):
        bears=list(map(lambda x:x.lower(),BEARISH_WORDS))
        txt = ''.join(list(map(lambda x:x.lower(),text)))
        return len(list(filter(lambda b: b in txt,bears)))

    def bullish_count(self,text):
        bulls=list(map(lambda x:x.lower(),BULLISH_WORDS))
        txt = ''.join(list(map(lambda x:x.lower(),text)))
        return len(list(filter(lambda b: b in txt,bulls)))

    def perception_score_msg(self,text):
        return self.bullish_count(text) - self.bearish_count(text)

    def p_score(self):
        return sum(list(map( lambda x: self.perception_score_msg(x),self.get_headlines())))

    def reset(self):
        self = Stock(self.symbol)
