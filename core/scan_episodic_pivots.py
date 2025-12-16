"""
Project: Episodic Pivot Scanner (Smart-Batching Edition)
Filename: core/scan_episodic_pivots.py
Version: 2.3.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-15

Changelog:
- v2.3.0: API EFFICIENCY OVERHAUL.
          - Added 'Batch Quote' filter (Step 2) to weed out non-movers.
          - Filters 1,000+ candidates down to ~20-50 *before* fetching charts.
          - Reduced MAX_WORKERS to 5 to prevent rate-limiting on the filtered list.
- v2.2.4: Funnel Architecture Integration.
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

# --- MODULE IMPORTS ---
import config
import utils

# Suppress Pandas FutureWarnings
pd.set_option('future.no_silent_downcasting', True)

# --- CONFIGURATION ---
SCRIPT_NAME = os.path.basename(__file__)
SCRIPT_VERSION = "2.3.0"
DEBUG_MODE = False

# FILES & PATHS
CHART_DIR = config.CHART_DIR_EP
RESULTS_FILE = os.path.join(config.DATA_DIR, "ep_results.csv")

# BLACKLIST CONFIG
BLACKLIST_SECTORS = ["Aerospace & Defense", "Tobacco"]
BLACKLIST_TICKERS = ["PLBY"]

# STRATEGY SETTINGS
# 1. Pre-Filter (Batch Quote)
MIN_CHANGE_PCT_FILTER = 3.0 # Stock must be up 3% to even qualify for a chart check

# 2. Strict Filter (Candle Data)
MIN_GAP_PCT = 0.08          # 8% True Gap (Open vs Prev Close)
MIN_RVOL = 2.0              # 200% Relative Volume
MIN_DOLLAR_VOL = 10_000_000 # $10M Traded Today

# ENGINE SETTINGS
MAX_WORKERS = 5             # REDUCED from 20 (We have fewer targets now, so we go gentle)

# TELEMETRY
API_LOCK = threading.Lock()
PLOT_LOCK = threading.Lock()
DEBUG_LOCK = threading.Lock()
API_CALL_COUNT = 0
DEBUG_PRINT_COUNT = 0

# ==============================================================================
# 0. UTILS
# ==============================================================================
def check_blacklist(candidate):
    """Checks sector blacklist using metadata from FMP Screener."""
    symbol = candidate.get('symbol', '').upper()
    sector = candidate.get('sector', 'Unknown')
    industry = candidate.get('industry', 'Unknown')

    if symbol in BLACKLIST_TICKERS: return True
    for banned in BLACKLIST_SECTORS:
        if banned in sector or banned in industry: return True
    return False

def debug_log(msg):
    global DEBUG_PRINT_COUNT
    if not DEBUG_MODE: return
    with DEBUG_LOCK:
        if DEBUG_PRINT_COUNT < 10:
            print(f"\n[DEBUG] {msg}")
            DEBUG_PRINT_COUNT += 1

# ==============================================================================
# 1. DATA SOURCE (The Two-Step Filter)
# ==============================================================================
def get_initial_candidates():
    """Step 1: Get the broad list of >$4 stocks with volume."""
    if not config.FMP_KEY:
        print("[ERROR] FMP_API_KEY missing.")
        return []

    print(f"[TIME] {datetime.now().strftime('%H:%M:%S')} - Step 1: Broad Screen (Price > $4)...")
    url = (
        f"https://financialmodelingprep.com/api/v3/stock-screener"
        f"?marketCapMoreThan=50000000&priceMoreThan=4&volumeMoreThan=50000"
        f"&isEtf=false&exchange=NASDAQ,NYSE,AMEX&limit=2000&apikey={config.FMP_KEY}"
    )
    try:
        res = requests.get(url, timeout=10).json()
        candidates = []
        for item in res:
            candidates.append({
                'symbol': item.get('symbol', '').replace('.', '-'),
                'sector': item.get('sector', 'Unknown'),
                'industry': item.get('industry', 'Unknown')
            })
        print(f"   found {len(candidates)} raw candidates.")
        return candidates
    except Exception as e:
        print(f"[WARN] FMP Screener failed: {e}")
        return []

def filter_by_batch_quote(candidates):
    """Step 2: Check % Change in batches to discard non-movers."""
    if not candidates: return []

    print(f"[TIME] {datetime.now().strftime('%H:%M:%S')} - Step 2: Batch Filtering (> {MIN_CHANGE_PCT_FILTER}% move)...")

    valid_candidates = []
    chunk_size = 100 # Safe URL length
    total_chunks = (len(candidates) + chunk_size - 1) // chunk_size

    # Create a map for quick lookup of candidate metadata
    cand_map = {c['symbol']: c for c in candidates}
    all_symbols = list(cand_map.keys())

    for i in range(0, len(all_symbols), chunk_size):
        chunk = all_symbols[i:i + chunk_size]
        tickers_str = ",".join(chunk)

        # Batch Quote Call
        url = f"https://financialmodelingprep.com/api/v3/quote/{tickers_str}?apikey={config.FMP_KEY}"

        try:
            res = requests.get(url, timeout=5).json()
            # FMP returns a list of quote objects
            for quote in res:
                sym = quote.get('symbol')
                pct_change = quote.get('changesPercentage', 0)

                # THE FILTER: Must be up at least X% today
                if pct_change >= MIN_CHANGE_PCT_FILTER:
                    if sym in cand_map:
                        valid_candidates.append(cand_map[sym])

        except Exception as e:
            print(f"   [WARN] Batch {i} failed: {e}")

        # Modest sleep to be kind to the API (even though we are saving huge calls)
        time.sleep(0.1)
        print(f"\r   Processed {min(i+chunk_size, len(all_symbols))}/{len(all_symbols)} tickers...", end="")

    print(f"\n   📉 Reduced {len(candidates)} -> {len(valid_candidates)} Active Movers.")
    return valid_candidates

def get_fmp_candles(symbol):
    """Step 3: Fetch full candles only for the survivors."""
    global API_CALL_COUNT
    if not config.FMP_KEY: return None

    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}?timeseries=60&apikey={config.FMP_KEY}"

    try:
        res = requests.get(url, timeout=5).json()
        with API_LOCK: API_CALL_COUNT += 1

        if 'historical' not in res: return None
        data = res['historical']
        if len(data) < 50: return None

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
def process_stock(candidate):
    symbol = candidate['symbol']
    if check_blacklist(candidate): return None

    df = get_fmp_candles(symbol)
    if df is None: return None

    try:
        today = df.iloc[-1]
        yesterday = df.iloc[-2]

        # 3. TECHNICALS (Strict Gap Check)
        gap_pct = (today['Open'] - yesterday['Close']) / yesterday['Close']

        if gap_pct < MIN_GAP_PCT:
            debug_log(f"{symbol}: Gap {gap_pct*100:.1f}% < {MIN_GAP_PCT*100}% -> REJECT")
            return None

        # 4. VOLUME CHECK
        avg_vol = df['Volume'].iloc[-51:-1].mean()
        if avg_vol == 0: return None

        rvol = today['Volume'] / avg_vol
        dollar_vol = today['Close'] * today['Volume']

        if rvol < MIN_RVOL: return None
        if dollar_vol < MIN_DOLLAR_VOL: return None

        # 5. RANGE CHECK
        range_len = today['High'] - today['Low']
        if range_len > 0 and (today['Close'] - today['Low']) / range_len < 0.40:
            return None

        # 6. AI GATEKEEPER
        if not utils.check_catalyst(symbol): return None

        # 7. GENERATE CHART
        with PLOT_LOCK:
            save_path = os.path.join(CHART_DIR, f"{symbol}_EP.png")
            title = f"{symbol} EP\nGap: {gap_pct*100:.1f}% | RVOL: {rvol:.1f}x"
            mpf.plot(df, type='candle', style='yahoo', title=title, volume=True, savefig=save_path)
            matplotlib.pyplot.close('all')

        return {
            "Symbol": symbol,
            "Gap%": round(gap_pct * 100, 2),
            "Reason": "Gap+News+RVOL"
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

    # STEP 1 & 2: Get Efficient List
    raw_list = get_initial_candidates()
    candidates = filter_by_batch_quote(raw_list)

    matches = []

    if candidates:
        print(f"\n[TIME] {datetime.now().strftime('%H:%M:%S')} - Deep Scanning {len(candidates)} movers...")

        analysis_start = time.time()
        processed_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_cand = {executor.submit(process_stock, c): c for c in candidates}

            for future in concurrent.futures.as_completed(future_to_cand):
                processed_count += 1
                try:
                    res = future.result()
                    if res: matches.append(res)
                except Exception: pass

                if processed_count % 5 == 0:
                    elapsed = time.time() - analysis_start
                    rate = processed_count / elapsed if elapsed > 0 else 0
                    print(f"\rScanning {processed_count}/{len(candidates)} | Found: {len(matches)} | Rate: {rate:.1f}/s", end="")

    # SAVE RESULTS
    if matches:
        df_res = pd.DataFrame(matches)
        df_res = df_res.sort_values(by="Gap%", ascending=False)
        df_res.to_csv(RESULTS_FILE, index=False)
        print("\n\n" + "="*50)
        print(f"[SUCCESS] Saved {len(matches)} EP candidates to {RESULTS_FILE}")
    else:
        print("\n\n" + "="*50)
        print(f"[DONE] No EP setups found.")

    print(f"[TIME] Total Duration: {datetime.now() - script_start_time}")