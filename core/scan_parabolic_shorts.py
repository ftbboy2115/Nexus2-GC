"""
Project: Parabolic Short Scanner (The "Gravity" Engine)
Version: 1.0.1
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-03

Changelog:
- v1.0.1: Added Metadata Header (Script Name, Version, Timestamp).
- v1.0.0: Initial release. Parabolic Short logic.
"""

import matplotlib

matplotlib.use("Agg")  # Prevent GUI crashes

import yfinance as yf
import pandas as pd
import requests
import time
import os
import sys
import datetime
import contextlib
import mplfinance as mpf
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
SCRIPT_NAME = os.path.basename(__file__)
SCRIPT_VERSION = "1.0.1"
MAX_THREADS = 5
WATCHLIST_FILE = "parabolic_shorts.txt"
CHART_DIR = "charts_shorts"

load_dotenv()
FMP_KEY = os.environ.get("FMP_API_KEY")


# ==============================================================================
# 0. METADATA HEADER
# ==============================================================================
def print_metadata():
    """Prints script identity and time to the console."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 60)
    print(f"📜 SCRIPT:   {SCRIPT_NAME}")
    print(f"🔢 VERSION:  {SCRIPT_VERSION}")
    print(f"⏰ TIME:     {now}")
    print("=" * 60 + "\n")


# ==============================================================================
# 1. DATA SCRAPER (Hunting the High Flyers)
# ==============================================================================
def get_parabolic_candidates():
    if not FMP_KEY:
        print("⚠️ FMP_API_KEY missing. Cannot run fast scan.")
        return []

    print("⚡ CONNECTING TO FMP (Finding Top Gainers)...")

    # We ask FMP for stocks with Beta > 1.5 (Volatile) and Vol > 500k
    url = (
        f"https://financialmodelingprep.com/api/v3/stock-screener"
        f"?marketCapMoreThan=50000000"
        f"&priceMoreThan=2"
        f"&volumeMoreThan=500000"
        f"&betaMoreThan=1.5"
        f"&isEtf=false"
        f"&exchange=NASDAQ,NYSE,AMEX"
        f"&limit=1000"
        f"&apikey={FMP_KEY}"
    )

    try:
        response = requests.get(url)
        data = response.json()
        tickers = [item['symbol'].replace('.', '-') for item in data]
        print(f"✅ Found {len(tickers)} volatile candidates.")
        return tickers
    except Exception as e:
        print(f"❌ FMP Error: {e}")
        return []


def get_data(symbol):
    try:
        # Download 3 months
        with contextlib.redirect_stderr(open(os.devnull, 'w')):  # Silence yfinance
            df = yf.download(symbol, period="3mo", interval="1d", progress=False, auto_adjust=True)

        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if len(df) < 50: return None
        return df
    except:
        return None


# ==============================================================================
# 2. LOGIC ENGINE (The "Gravity" Check)
# ==============================================================================
def evaluate_short(symbol, df):
    today = df.iloc[-1]
    close = float(today['Close'])

    # Moving Averages
    sma_10 = df['Close'].rolling(window=10).mean().iloc[-1]
    sma_20 = df['Close'].rolling(window=20).mean().iloc[-1]

    # RSI (Momentum)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs)).iloc[-1]

    # --- PARABOLIC CRITERIA ---

    # A. The Massive Run (Up > 40% in last month)
    price_20_days_ago = float(df['Close'].iloc[-21])
    monthly_gain = (close - price_20_days_ago) / price_20_days_ago
    if monthly_gain < 0.40: return None

    # B. The Extension (Rubber Band > 15% from 10MA)
    dist_from_10 = (close - sma_10) / sma_10
    if dist_from_10 < 0.15: return None

    # C. The Climax (RSI > 75)
    if rsi < 75: return None

    return {
        "Symbol": symbol,
        "Price": round(close, 2),
        "1M_Gain%": round(monthly_gain * 100, 1),
        "Dist_10MA%": round(dist_from_10 * 100, 1),
        "RSI": round(rsi, 1)
    }


# ==============================================================================
# 3. VISUALIZER
# ==============================================================================
def save_short_chart(symbol, df, match_data):
    if not os.path.exists(CHART_DIR): os.makedirs(CHART_DIR)

    title = (f"{symbol} PARABOLIC SHORT\n"
             f"Gain: +{match_data['1M_Gain%']}% | RSI: {match_data['RSI']}")

    try:
        save_path = os.path.join(CHART_DIR, f"{symbol}_SHORT.png")

        sma_10 = mpf.make_addplot(df['Close'].rolling(window=10).mean(), color='blue', width=1.5)
        sma_20 = mpf.make_addplot(df['Close'].rolling(window=20).mean(), color='red', width=1.5)

        mpf.plot(
            df, type='candle', style='yahoo', title=title,
            addplot=[sma_10, sma_20], volume=True, savefig=save_path
        )
        matplotlib.pyplot.close('all')
    except:
        pass


# ==============================================================================
# 4. MAIN EXECUTION
# ==============================================================================
def scan_worker(symbol):
    data = get_data(symbol)
    if data is None: return None

    try:
        result = evaluate_short(symbol, data)
        if result:
            save_short_chart(symbol, data, result)
            # Live Save
            with open(WATCHLIST_FILE, "a") as f: f.write(f"{symbol},")
            return result
    except:
        pass
    return None


if __name__ == "__main__":
    print_metadata()
    print("### STARTING PARABOLIC SHORT SCAN ###")
    print("Criteria: Up > 40% Month, 15% Extended from 10MA, RSI > 75.")

    if not os.path.exists(CHART_DIR): os.makedirs(CHART_DIR)
    with open(WATCHLIST_FILE, "w") as f:
        f.write("")

    tickers = get_parabolic_candidates()
    matches = []

    print(f"\n🚀 Scanning {len(tickers)} high-beta stocks...")

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_symbol = {executor.submit(scan_worker, sym): sym for sym in tickers}

        completed = 0
        for future in as_completed(future_to_symbol):
            completed += 1
            res = future.result()
            print(f"\rScanning {completed}/{len(tickers)} | Found: {len(matches)}", end="")
            if res: matches.append(res)

    print("\n\n" + "=" * 60)
    print(f"🎉 FOUND {len(matches)} PARABOLIC SHORT CANDIDATES")
    print("=" * 60)

    if matches:
        res_df = pd.DataFrame(matches)
        res_df = res_df.sort_values(by="1M_Gain%", ascending=False)
        print(res_df.to_string(index=False))
        print(f"\nCheck '{CHART_DIR}' for charts.")
    else:
        print("No parabolic setups found.")