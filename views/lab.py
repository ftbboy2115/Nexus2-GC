"""
Module: Dashboard View - Strategy Lab (FMP Edition)
Version: 2.4.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-14

Changelog:
- v2.4.0: Switched Data Engine from yfinance (Broken) to FMP (Robust).
          Injects FMP_API_KEY into the generated backtest file.
"""
import streamlit as st
import importlib
import sys
import os
import numpy as np

# --- ARCHITECTURE FIX: Import from 'research' package ---
try:
    from research import strategy_factory
except ImportError:
    strategy_factory = None

# Safe Import for Backtest Lab
try:
    from research import backtest_lab
except ImportError:
    backtest_lab = None
except SyntaxError:
    backtest_lab = None

def write_strategy_file(code_content):
    # We grab the API Key from the current environment to inject it
    fmp_key = os.environ.get("FMP_API_KEY", "")

    template = r"""
import pandas as pd
import pandas_ta as ta
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import requests
import os
import numpy as np

# INJECTED API KEY
FMP_KEY = "{{FMP_KEY}}"

# AI STRATEGY
{{STRATEGY}}

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
"""
    # Replace placeholders
    final = template.replace("{{STRATEGY}}", code_content)
    final = final.replace("{{FMP_KEY}}", fmp_key)

    # Write to 'research' directory
    target_path = os.path.join("research", "backtest_lab.py")
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(final)

def render():
    st.header("🧪 AI Strategy R&D Lab")

    if not strategy_factory:
        st.error("⚠️ Critical: 'research.strategy_factory' could not be imported.")
        return

    # 1. INPUTS
    col_in1, col_in2 = st.columns([3, 1])
    with col_in1:
        user_idea = st.text_area("Describe idea:", height=100, placeholder="e.g. 'Use 10 EMA'")
    with col_in2:
        test_tickers = st.text_input("Validation Tickers:", value="NVDA, TSLA, PLTR")
        target_list = [t.strip() for t in test_tickers.split(",")]

    # 2. ACTION
    if st.button("✨ Run Optimization Loop"):
        st.session_state['optimization_log'] = []

        with st.status("AI Team is optimizing...", expanded=True) as status:
            current_code = st.session_state.get('current_strategy_code', None)
            stats = None

            for i in range(1, 4):
                st.write(f"**🔄 Iteration {i}/3**")

                # A. MANAGER LOGIC
                if i == 1:
                    context = f"PREVIOUS CODE:\n{current_code}\n\nFEEDBACK: {user_idea}" if current_code else ""
                    plan = strategy_factory.run_manager_agent(user_idea, context=context)
                else:
                    if stats:
                        plan = f"Refine: Return {stats['Return [%]']:.2f}%, WR {stats['Win Rate [%]']:.2f}%."
                    else:
                        plan = "Previous run crashed. Try simpler strategy."

                # B. CODER LOGIC
                instr = (f"{plan}\n\nCRITICAL RULES:\n1. Name class 'MomentumStrategy(Strategy)'.\n2. ALWAYS use `self.buy(size=0.10, sl=..., tp=...)`.\n3. Use `self.data.Close`.")
                code = strategy_factory.run_coder_agent(instr)

                st.session_state['current_strategy_code'] = code
                write_strategy_file(code)

                # C. BACKTEST LOGIC
                try:
                    # Reload module
                    module_name = 'research.backtest_lab'
                    if module_name in sys.modules:
                        import research.backtest_lab as bt_lab
                        importlib.reload(bt_lab)
                        backtest_lab = bt_lab
                    else:
                        from research import backtest_lab

                    if backtest_lab:
                        stats = backtest_lab.run_test(target_list)

                        if stats:
                            res_str = f"Iter {i}: Ret {stats['Return [%]']:.2f}% | WR {stats['Win Rate [%]']:.2f}%"
                            st.session_state['optimization_log'].append(res_str)
                            st.write(f"📊 {res_str}")
                            if stats['Return [%]'] > 20: break
                    else:
                        st.error("Could not load backtest module.")
                        stats = None

                except Exception as e:
                    st.error(f"Crash: {e}")
                    stats = None

            status.update(label="Optimization Complete!", state="complete")

    # 3. HISTORY DISPLAY
    if st.session_state.get('optimization_log'):
        st.subheader("History")
        for log in st.session_state['optimization_log']: st.text(log)

    if st.session_state.get('current_strategy_code'):
        with st.expander("View Code"): st.code(st.session_state['current_strategy_code'], language='python')