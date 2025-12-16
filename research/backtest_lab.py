
import pandas as pd
import pandas_ta as ta
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import requests
import os
import numpy as np

# INJECTED API KEY
FMP_KEY = "kJiLuNDZJowFPhyRfURr0CUza9fGvmmR"

# AI STRATEGY
import pandas_ta as ta
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import numpy as np

def get_sma(series, length):
    return ta.sma(pd.Series(series), length=length).to_numpy()

def get_ema(series, length):
    return ta.ema(pd.Series(series), length=length).to_numpy()

def get_rsi(close, length):
    return ta.rsi(pd.Series(close), length=length).to_numpy()

class MomentumStrategy(Strategy):
    def init(self):
        self.sma20 = self.I(get_sma, self.data.Close, 20)
        self.sma50 = self.I(get_sma, self.data.Close, 50)

    def next(self):
        if crossover(self.sma20, self.sma50):
            self.buy(size=0.10, sl=0.95 * self.data.Close[-1], tp=1.05 * self.data.Close[-1])
        elif crossover(self.sma50, self.sma20):
            self.sell(size=0.10, sl=1.05 * self.data.Close[-1], tp=0.95 * self.data.Close[-1])

# DATA ENGINE (FMP)
def get_clean_data(symbol):
    if not FMP_KEY: return None
    
    # Fetch 2 years of daily data
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}?timeseries=500&apikey={FMP_KEY}"
    
    try:
        res = requests.get(url, timeout=5).json()
        if 'historical' not in res: return None
        
        df = pd.DataFrame(res['historical'])
        
        # FMP is Newest First -> Flip to Oldest First
        df = df.iloc[::-1].reset_index(drop=True)
        
        # Renaissance Columns for Backtesting.py (Capitalized)
        df = df.rename(columns={
            'date': 'Date', 'open': 'Open', 'high': 'High', 
            'low': 'Low', 'close': 'Close', 'volume': 'Volume'
        })
        
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
        
        # Ensure numeric
        cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
        
        return df if len(df) > 100 else None
    except: return None

def run_test(symbols):
    if isinstance(symbols, str): symbols = [symbols]
    results = []
    
    # Ensure chart directory exists
    if not os.path.exists("charts_kk"): os.makedirs("charts_kk")
    
    for sym in symbols:
        data = get_clean_data(sym)
        if data is None: continue
        try:
            # Dynamically name the strategy for the report
            MomentumStrategy.__name__ = f"{sym}_Strategy"
            
            # Run Backtest
            bt = Backtest(data, MomentumStrategy, cash=100000, commission=.002)
            stats = bt.run()
            
            results.append({
                "Symbol": sym, 
                "Return": stats['Return [%]'], 
                "WinRate": stats['Win Rate [%]'], 
                "Drawdown": stats['Max. Drawdown [%]']
            })
        except Exception as e: 
            print(f"Backtest Error on {sym}: {e}")
            pass
        
    if not results: return None
    
    return {
        "Return [%]": np.mean([r['Return'] for r in results]),
        "Win Rate [%]": np.nanmean([r['WinRate'] for r in results]),
        "Max. Drawdown [%]": np.mean([r['Drawdown'] for r in results]),
        "# Trades": 0
    }
