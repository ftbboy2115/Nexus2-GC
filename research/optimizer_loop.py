"""
Project: The Strategy Optimizer Loop (The "Unlimited Upside" Update)
Version: 2.5.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-03

Changelog:
- v2.5.0: Removed fixed Take Profit (tp) from Coder instructions.
          KK Strategy requires "letting winners run," so we rely only on the Trailing Stop.
- v2.4.2: Native Risk Management (sl=...).
"""
import os
import importlib
from dotenv import load_dotenv
import google.generativeai as genai
import backtest_lab
from strategy_factory import run_coder_agent
import numpy as np

# SETUP
load_dotenv()
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
MODEL_NAME = "gemini-2.5-flash"

def get_director_critique(stats):
    print("\n🎬 DIRECTOR: Analyzing metrics...")
    prompt = (
        "You are a Hedge Fund Risk Manager. Review the backtest stats and output a BETTER strategy description. "
        "\n\n"
        f"--- REPORT ---\n"
        f"Avg Return: {stats['Return [%]']:.2f}%\n"
        f"Avg Win Rate: {stats['Win Rate [%]']:.2f}%\n"
        f"Avg Drawdown: {stats['Max. Drawdown [%]']:.2f}%\n\n"
        "--- INSTRUCTIONS ---\n"
        "1. Diagnose the failure (e.g. 'Zero trades' -> 'Entry too strict').\n"
        "2. Propose a mathematical fix (e.g. 'Add RSI(14) > 50').\n"
        "3. Output the REVISED strategy description."
    )
    model = genai.GenerativeModel(MODEL_NAME)
    return model.generate_content(prompt).text

def rewrite_backtest_file(new_class_code):
    print("\n💾 SYSTEM: Injecting new strategy code...")

    file_template = r"""
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import os
import numpy as np

# ==============================================================================
# 1. AI STRATEGY
# ==============================================================================
{{STRATEGY_CODE_PLACEHOLDER}}

# ==============================================================================
# 2. DATA & EXECUTION
# ==============================================================================
def get_data(symbol):
    try:
        df = yf.download(symbol, period="2y", interval="1d", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df if len(df) > 100 else None
    except: return None

def run_test(symbols):
    if isinstance(symbols, str): symbols = [symbols]
    results = []
    
    if not os.path.exists("charts_kk"): os.makedirs("charts_kk")

    print(f"\n🧪 TESTING BASKET: {', '.join(symbols)}")
    
    for sym in symbols:
        data = get_data(sym)
        if data is None: continue
        
        try:
            MomentumStrategy.__name__ = f"{sym}_Strategy"
            
            bt = Backtest(data, MomentumStrategy, cash=100000, commission=.002)
            stats = bt.run()
            
            chart_path = os.path.join("charts_kk", f"{sym}_Auto_Backtest.html")
            bt.plot(filename=chart_path, open_browser=False)
            
            results.append({
                "Return": stats['Return [%]'],
                "WinRate": stats['Win Rate [%]'],
                "Drawdown": stats['Max. Drawdown [%]']
            })
            print(f"   🔹 {sym}: {stats['Return [%]']:.2f}% Ret | Saved: {chart_path}")
            
        except Exception as e:
            print(f"   ⚠️ Error {sym}: {e}")

    if not results: return None

    return {
        "Return [%]": np.mean([r['Return'] for r in results]),
        "Win Rate [%]": np.nanmean([r['WinRate'] for r in results]),
        "Max. Drawdown [%]": np.mean([r['Drawdown'] for r in results]),
        "# Trades": 0 
    }

if __name__ == "__main__":
    run_test(["NVDA", "TSLA", "PLTR"])
"""
    final_content = file_template.replace("{{STRATEGY_CODE_PLACEHOLDER}}", new_class_code)
    with open("backtest_lab.py", "w", encoding="utf-8") as f:
        f.write(final_content)
    print("✅ File updated.")

if __name__ == "__main__":
    TRAIN_BASKET = ["NVDA", "TSLA", "PLTR"]
    VALIDATION_BASKET = ["AMD", "META", "AMZN"]
    MAX_ATTEMPTS = 3
    print(f"### OPTIMIZER START ###")

    for i in range(MAX_ATTEMPTS):
        print(f"\n--- ITERATION {i+1} ---")
        try:
            importlib.reload(backtest_lab)
            stats = backtest_lab.run_test(TRAIN_BASKET)

            if stats and stats['Return [%]'] > 15.0:
                print(f"✅ Training Passed ({stats['Return [%]']:.2f}%). Running Validation...")
                val_stats = backtest_lab.run_test(VALIDATION_BASKET)

                if val_stats and val_stats['Return [%]'] > 5.0:
                    print(f"\n🏆 GOLDEN STRATEGY FOUND!")
                    break
                else:
                    print(f"❌ Validation Failed. Strategy is Overfit.")
                    stats = val_stats

        except Exception as e:
            print(f"❌ Crash: {e}")
            stats = None

        plan = get_director_critique(stats) if stats else "Create robust Momentum Strategy."

        # --- THE KK-COMPLIANT INSTRUCTIONS ---
        # ... inside the loop ...
        instruction = (
            f"{plan}\n\n"
            "CRITICAL RULES:\n"
            "1. Name class 'MomentumStrategy(Strategy)'.\n"
            "2. RISK MANAGEMENT: Use `sl=` (Stop Loss) in `self.buy()`.\n"
            "   Example: `sl = self.data.Close[-1] * 0.95`.\n"
            "3. EXIT STRATEGY: Use `self.position.close()` on technical signals.\n"
            "4. BANNED ATTRIBUTES (CRITICAL):\n"
            "   - `self.position.entry_bar` (Does not exist!)\n"
            "   - `trade.age`\n"
            "   - `self.position.entry_price`\n"
            "   - DO NOT attempt time-based exits (holding for X days) unless you use `len(self.data) - trade.entry_bar` on `self.trades` list.\n"
        )

        code = run_coder_agent(instruction)
        rewrite_backtest_file(code)