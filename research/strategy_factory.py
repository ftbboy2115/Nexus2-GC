"""
Project: Strategy Factory (Nexus Edition)
Version: 3.0.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-14

Changelog:
- v3.0.0: Updated for Nexus Architecture.
          Added STRICT anti-hallucination rules (No c_under).
"""
import os
import google.generativeai as genai
from dotenv import load_dotenv

# 1. SETUP
load_dotenv()
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("❌ GOOGLE_API_KEY not found.")

genai.configure(api_key=api_key)
# Using Flash for speed/cost, Pro for reasoning if needed
MODEL_NAME = "gemini-2.0-flash"

# 2. AGENTS

def run_manager_agent(topic, context=""):
    """ The Strategist """
    system = (
        "You are a Senior Trading Strategist. Design a specific stock strategy. "
        "1. Read the 'Context' provided below.\n"
        "2. Output a numbered list of logical conditions (e.g., 'Close > 10SMA').\n"
        "3. Be precise with numbers."
    )

    prompt = f"TASK: Design a strategy for '{topic}'.\n\nCONTEXT:\n{context}"

    model = genai.GenerativeModel(MODEL_NAME, system_instruction=system)
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {e}"

def run_coder_agent(strategy_text):
    """ The Coder: Explicit Helpers Only """
    system = (
        "You are a Python Algo-Trading Expert. Convert the strategy into a Python Class. "
        "You MUST follow this CRITICAL TEMPLATE to prevent crashes:\n\n"
        
        "1. IMPORTS:\n"
        "   import pandas_ta as ta\n"
        "   from backtesting import Backtest, Strategy\n"
        "   from backtesting.lib import crossover\n"
        "   import numpy as np\n\n"
        
        "2. CRITICAL SYNTAX RULES:\n"
        "   - NEVER use 'c_under' or 'crossunder'. They DO NOT EXIST.\n"
        "   - To check if A crosses under B, use: `crossover(B, A)` (Swap variables).\n"
        "   - To check if A crosses over B, use: `crossover(A, B)`.\n"
        "   - ALWAYS use `self.buy(size=0.10, sl=..., tp=...)` for entries.\n"
        "   - Use `self.data.Close` (Capitalized).\n\n"
        
        "3. INDICATOR HELPERS (Define these OUTSIDE the class):\n"
        "   def get_sma(series, length):\n"
        "       return ta.sma(pd.Series(series), length=length).to_numpy()\n"
        "   def get_ema(series, length):\n"
        "       return ta.ema(pd.Series(series), length=length).to_numpy()\n"
        "   def get_rsi(close, length):\n"
        "       return ta.rsi(pd.Series(close), length=length).to_numpy()\n\n"

        "4. CLASS STRUCTURE:\n"
        "   class MomentumStrategy(Strategy):\n"
        "       def init(self):\n"
        "           # Example: self.ema10 = self.I(get_ema, self.data.Close, 10)\n"
        "           pass\n"
        "       def next(self):\n"
        "           pass\n\n"
        
        "TASK: Write the full code for the strategy below. Return ONLY the code."
    )

    model = genai.GenerativeModel(MODEL_NAME, system_instruction=system)
    try:
        response = model.generate_content(
            f"Strategy to implement:\n{strategy_text}",
            generation_config=genai.types.GenerationConfig(temperature=0.0)
        )
        return response.text.replace("```python", "").replace("```", "").strip()
    except Exception as e:
        return f"# Error generating code: {e}"