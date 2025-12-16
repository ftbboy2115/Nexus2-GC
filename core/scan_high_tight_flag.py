"""
Project: High Tight Flag Scanner (Safe Mode)
Filename: core/scan_high_tight_flag.py
Version: 1.2.5
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-15

Changelog:
- v1.2.5: EMOJI REMOVAL. Replaced Unicode icons with text tags to prevent UnicodeEncodeError on Windows.
- v1.2.4: PATH FIX.
"""

import matplotlib
matplotlib.use("Agg") # Force non-GUI backend

import pandas as pd
import requests
import time
import os
import sys
import threading
import concurrent.futures
import shutil
import mplfinance as mpf
from datetime import datetime

# --- PATH SETUP (CRITICAL FIX) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- MODULE IMPORTS ---
import config
import utils

# Suppress Pandas FutureWarnings
pd.set_option('future.no_silent_downcasting', True)

# --- CONFIGURATION ---
SCRIPT_NAME = os.path.basename(__file__)
SCRIPT_VERSION = "1.2.5"

# FILES & PATHS
CHART_DIR = os.path.join(config.BASE_DIR, "charts_htf")
RESULTS_FILE = os.path.join(config.DATA_DIR, "htf_results.csv")

# BLACKLIST
BLACKLIST_SECTORS = ["Aerospace & Defense", "Tobacco"]
BLACKLIST_TICKERS = ["PLBY"]

# HTF PARAMETERS
MIN_MOVE_PCT = 0.90      # +90% Move (The "Pole")
MAX_PULLBACK = 0.25      # -25% Depth (The "Flag")
MIN_PRICE = 4.00
MIN_DOLLAR_VOL = 5_000_000
MIN_SHARE_VOL = 500000

# ENGINE SETTINGS
MAX_WORKERS = 5
API_DELAY = 1.0

# TELEMETRY
API_LOCK = threading.Lock()
PLOT_LOCK = threading.Lock()
API_CALL_COUNT = 0

# ==============================================================================
# 0. UTILS
# ==============================================================================
def check_blacklist(candidate):
    symbol = candidate.get('symbol', '').upper()
    sector = candidate.get('sector', 'Unknown')
    industry = candidate.get('industry', 'Unknown')

    if symbol in BLACKLIST_TICKERS: return True
    for banned in BLACKLIST_SECTORS:
        if banned in sector or banned in industry: return True
    return False

# ==============================================================================
# 1. DATA SOURCE (Two-Step Filter)
# ==============================================================================
def get_liquid_universe():
    if not config.FMP_KEY:
        print("[ERROR] FMP_API_KEY missing.")
        return []

    print(f"[TIME] {datetime.now().strftime('%H:%M:%S')} - Step 1: Broad Screen (Price > ${MIN_PRICE}, Vol > {MIN_SHARE_VOL/100}K)...")
    url = (
        f"https://financialmodelingprep.com/api/v3/stock-screener"
        f"?priceMoreThan={MIN_PRICE}&volumeMoreThan={MIN_SHARE_VOL}"
        f"&isEtf=false&exchange=NASDAQ,NYSE,AMEX&limit=10000&apikey={config.FMP_KEY}"
    )
    try:
        res = requests.get(url, timeout=15).json()
        candidates = []
        for item in res:
            candidates.append({
                'symbol': item.get('symbol', '').replace('.', '-'),
                'sector': item.get('sector', 'Unknown'),
                'industry': item.get('industry', 'Unknown')
            })
        print(f"   [INFO] Found {len(candidates)} raw candidates.")
        return candidates
    except Exception as e:
        print(f"[WARN] FMP Screener failed: {e}")
        return []

def filter_by_volatility(candidates):
    if not candidates: return []

    print(f"[TIME] {datetime.now().strftime('%H:%M:%S')} - Step 2: Batch Volatility Check (> 90% Range)...")

    valid_candidates = []
    chunk_size = 100

    cand_map = {c['symbol']: c for c in candidates}
    all_symbols = list(cand_map.keys())

    for i in range(0, len(all_symbols), chunk_size):
        chunk = all_symbols[i:i + chunk_size]
        tickers_str = ",".join(chunk)

        url = f"https://financialmodelingprep.com/api/v3/quote/{tickers_str}?apikey={config.FMP_KEY}"

        try:
            res = requests.get(url, timeout=5).json()
            for quote in res:
                sym = quote.get('symbol')
                year_high = quote.get('yearHigh')
                year_low = quote.get('yearLow')
                price = quote.get('price')

                if year_high is None or year_low is None or price is None: continue
                if year_low <= 0: continue

                range_pct = (year_high - year_low) / year_low

                if range_pct >= MIN_MOVE_PCT:
                    if year_high > 0:
                        pullback_from_high = (year_high - price) / year_high
                        if pullback_from_high < 0.60:
                            if sym in cand_map:
                                valid_candidates.append(cand_map[sym])

        except Exception as e:
            print(f"   [WARN] Batch {i} failed: {e}")

        time.sleep(0.1)
        print(f"\r   Processed {min(i+chunk_size, len(all_symbols))}/{len(all_symbols)} tickers...", end="")

    # --- REPLACED EMOJI WITH SAFE TEXT ---
    print(f"\n   [FILTER] Reduced {len(candidates)} -> {len(valid_candidates)} Potential Winners.")
    return valid_candidates

def get_candles(symbol):
    global API_CALL_COUNT
    if not config.FMP_KEY: return None

    time.sleep(API_DELAY)

    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}?timeseries=120&apikey={config.FMP_KEY}"

    try:
        res = requests.get(url, timeout=5).json()
        with API_LOCK: API_CALL_COUNT += 1

        if 'historical' not in res: return None
        data = res['historical']
        if len(data) < 60: return None

        df = pd.DataFrame(data)
        df = df.iloc[::-1].reset_index(drop=True)
        df = df.rename(columns={'date': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
        return df
    except: return None

# ==============================================================================
# 2. LOGIC ENGINE
# ==============================================================================
def analyze_htf(candidate):
    symbol = candidate['symbol']
    if check_blacklist(candidate): return None

    df = get_candles(symbol)
    if df is None: return None

    try:
        window = df.tail(60)
        current_close = window['Close'].iloc[-1]
        current_vol = window['Volume'].iloc[-1]

        dollar_vol = current_close * current_vol
        if dollar_vol < MIN_DOLLAR_VOL: return None

        highest_high = window['High'].max()
        lowest_low = window['Low'].min()

        if lowest_low == 0: return None
        move_pct = (highest_high - lowest_low) / lowest_low

        if move_pct < MIN_MOVE_PCT: return None

        pullback = (highest_high - current_close) / highest_high
        if pullback > MAX_PULLBACK: return None

        with PLOT_LOCK:
            save_path = os.path.join(CHART_DIR, f"{symbol}_HTF.png")
            title = f"{symbol} HTF\nMove: +{move_pct*100:.0f}% | Depth: -{pullback*100:.1f}% | $Vol: ${dollar_vol/1_000_000:.1f}M"
            plot_data = df.tail(90)
            mpf.plot(plot_data, type='candle', style='yahoo', title=title, volume=True, savefig=save_path)
            matplotlib.pyplot.close('all')

        return {
            "Symbol": symbol,
            "Sector": candidate['sector'],
            "Move%": round(move_pct * 100, 1),
            "Depth%": round(pullback * 100, 1),
            "Close": current_close,
            "$Vol (M)": round(dollar_vol / 1_000_000, 2)
        }

    except Exception: return None

# ==============================================================================
# 3. EXECUTION
# ==============================================================================
if __name__ == "__main__":
    script_start_time = datetime.now()
    utils.print_metadata(SCRIPT_NAME, SCRIPT_VERSION)

    if not os.path.exists(CHART_DIR): os.makedirs(CHART_DIR)
    utils.clean_folder(CHART_DIR)

    raw_list = get_liquid_universe()
    candidates = filter_by_volatility(raw_list)

    matches = []

    if candidates:
        print(f"\n[TIME] {datetime.now().strftime('%H:%M:%S')} - Deep Scanning {len(candidates)} candidates...")
        print(f"[INFO] Launching {MAX_WORKERS} Worker Threads (w/ {API_DELAY}s delay).")

        analysis_start = time.time()
        processed_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_cand = {executor.submit(analyze_htf, c): c for c in candidates}

            for future in concurrent.futures.as_completed(future_to_cand):
                processed_count += 1
                try:
                    res = future.result()
                    if res: matches.append(res)
                except Exception: pass

                if processed_count % 10 == 0:
                    elapsed = time.time() - analysis_start
                    if elapsed > 0:
                        rate = processed_count / elapsed
                        api_rate = (API_CALL_COUNT / elapsed) * 60
                    else:
                        rate = 0; api_rate = 0

                    print(f"\rScan: {processed_count}/{len(candidates)} | Found: {len(matches)} | Rate: {rate:.1f}/s | API: {api_rate:.0f}/min", end="")

    if matches:
        df_res = pd.DataFrame(matches)
        df_res = df_res.sort_values(by="Move%", ascending=False)
        df_res.to_csv(RESULTS_FILE, index=False)
        print(f"\n\n[SUCCESS] Saved {len(matches)} HTF candidates to {RESULTS_FILE}")
    else:
        print("\n\n[DONE] No HTF setups found.")

    print(f"[TIME] Total Duration: {datetime.now() - script_start_time}")