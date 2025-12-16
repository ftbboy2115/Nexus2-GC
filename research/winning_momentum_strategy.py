
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import os
import numpy as np

# ==============================================================================
# 1. THE AI-GENERATED STRATEGY
# ==============================================================================
import pandas_ta as ta
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

def get_ta(df, kind, **kwargs):
    indicator = df.ta(kind=kind, **kwargs)
    if isinstance(indicator, pd.DataFrame): indicator = indicator.iloc[:, 0]
    return indicator.to_numpy()

class MomentumStrategy(Strategy):
    ema_length = 10
    rsi_length = 14
    rsi_threshold = 50

    def init(self):
        self.ema = self.I(get_ta, self.data.df, kind='ema', length=self.ema_length)
        self.rsi = self.I(get_ta, self.data.df, kind='rsi', length=self.rsi_length)

    def next(self):
        price = self.data.Close[-1]
        current_ema = self.ema[-1]
        current_rsi = self.rsi[-1]

        # Buy condition: Price above EMA AND RSI above threshold
        if price > current_ema and current_rsi > self.rsi_threshold:
            if not self.position:  # If not already in a position
                self.buy()

        # Sell condition: Price below EMA OR RSI below threshold
        elif price < current_ema or current_rsi < self.rsi_threshold:
            if self.position:  # If currently in a position
                self.position.close()

# ==============================================================================
# 2. DATA ENGINE
# ==============================================================================
def get_clean_data(symbol):
    try:
        df = yf.download(symbol, period="2y", interval="1d", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if len(df) < 100: return None
        return df
    except: return None

# ==============================================================================
# 3. PORTFOLIO EXECUTION LOOP
# ==============================================================================
def run_test(symbols):
    # Ensure input is a list
    if isinstance(symbols, str): symbols = [symbols]
    
    results = []
    print(f"\n🧪 STARTING PORTFOLIO TEST ON: {', '.join(symbols)}")
    
    for sym in symbols:
        data = get_clean_data(sym)
        if data is None: continue
        
        try:
            # We assume the class is always named 'MomentumStrategy'
            bt = Backtest(data, MomentumStrategy, cash=100000, commission=.002)
            stats = bt.run()
            
            results.append({
                "Symbol": sym,
                "Return": stats['Return [%]'],
                "WinRate": stats['Win Rate [%]'],
                "Drawdown": stats['Max. Drawdown [%]'],
                "Trades": stats['# Trades']
            })
            print(f"   🔹 {sym}: {stats['Return [%]']:.2f}% Ret | {stats['Win Rate [%]']:.2f}% WR")
            
        except Exception as e:
            print(f"   ⚠️ Failed on {sym}: {e}")

    if not results: return None

    # Calculate Averages
    avg_return = np.mean([r['Return'] for r in results])
    avg_wr = np.nanmean([r['WinRate'] for r in results]) if results else 0
    avg_dd = np.mean([r['Drawdown'] for r in results])
    total_trades = sum([r['Trades'] for r in results])
    
    agg_stats = {
        "Return [%]": avg_return,
        "Win Rate [%]": avg_wr if not np.isnan(avg_wr) else 0,
        "Max. Drawdown [%]": avg_dd,
        "# Trades": total_trades,
        "_strategy": "Portfolio Average"
    }
    
    print("-" * 40)
    print(f"📊 PORTFOLIO RESULT: Avg Return: {avg_return:.2f}% | Avg WR: {agg_stats['Win Rate [%]']:.2f}%")
    print("-" * 40)
    
    return agg_stats

if __name__ == "__main__":
    run_test(["NVDA", "TSLA", "PLTR"])
