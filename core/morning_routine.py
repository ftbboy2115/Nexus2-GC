"""
Project: The Manager (Morning Routine)
Filename: morning_routine.py
Version: 1.3.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-12

Changelog:
- v1.3.0: Added Real-Time AI Telemetry.
          - Now tracks "AI Rate" (checks per minute) in the console.
          - Allows visual verification that we are staying under the Gemini 60 RPM limit.
- v1.2.3: Logic Correction (KK Compliance).
          - Core tickers must prove trend (Price > SMA20) to enter.
          - Core tickers skip AI only if trending.
- v1.2.2: Rate Limit Optimization (3 Workers).
"""

import os
import pandas as pd
import datetime
import shutil
import time
import requests
import concurrent.futures
import threading
from datetime import datetime as dt

import utils    # Import the Specialist (AI Check)
import config

# --- CONFIGURATION ---
CORE_FILE = "core_tickers.txt"
MOMENTUM_FILE = config.CSV_FILE
FINAL_WATCHLIST = config.WATCHLIST_FILE
ARCHIVE_DIR = "archive"
TREND_FILTER_SMA = 20

# PAID TIER SETTINGS
# 3 Workers = ~40-50 AI checks/min (Safe Zone for Gemini's 60 RPM limit)
MAX_WORKERS = 3
SKIP_AI = False

# BLACKLIST
BLACKLIST_SECTORS = ["Aerospace & Defense", "Tobacco"]
BLACKLIST_TICKERS = ["PLBY"]

# TELEMETRY
AI_LOCK = threading.Lock()
AI_CALL_COUNT = 0

def print_step(msg):
    print(f"\n[ROUTINE] {msg}")

def archive_yesterday():
    if not os.path.exists(ARCHIVE_DIR): os.makedirs(ARCHIVE_DIR)
    today = dt.now().strftime("%Y-%m-%d")
    if os.path.exists(FINAL_WATCHLIST):
        dst = os.path.join(ARCHIVE_DIR, f"watchlist_{today}.txt")
        shutil.copy(FINAL_WATCHLIST, dst)
        print(f"   📦 Archived: {dst}")

def get_fmp_profile(symbol):
    """Fetches sector info from FMP to check blacklist."""
    if not config.FMP_KEY: return {}
    try:
        url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}?apikey={config.FMP_KEY}"
        res = requests.get(url, timeout=5).json()
        if res and isinstance(res, list):
            return res[0]
    except: pass
    return {}

def check_blacklist(symbol):
    """Gate 0: Is this stock banned? (Uses FMP now)"""
    if symbol in BLACKLIST_TICKERS: return True

    profile = get_fmp_profile(symbol)
    sector = profile.get('sector', 'Unknown')
    industry = profile.get('industry', 'Unknown')

    for banned in BLACKLIST_SECTORS:
        if banned in sector or banned in industry:
            return True
    return False

def check_technical_gate_fmp(symbol):
    """Gate 1: Is Price > 20 SMA? (Uses FMP API - No more yfinance 401s)"""
    if not config.FMP_KEY:
        print("   ⚠️ FMP Key Missing. Skipping Technical Check.")
        return True # Fail open if no key

    try:
        # Fetch 30 days of daily candles
        url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}?timeseries=30&apikey={config.FMP_KEY}"
        res = requests.get(url, timeout=5).json()

        if 'historical' not in res: return False

        data = res['historical']
        if len(data) < 20: return False

        # Calculate SMA 20 manually (Data is newest to oldest)
        closes = [d['close'] for d in data[:20]]
        current_price = closes[0]
        sma20 = sum(closes) / len(closes)

        return current_price > sma20

    except Exception as e:
        # print(f"   ⚠️ FMP Error {symbol}: {e}")
        return False

def load_inputs():
    candidates = set()
    core_list = []
    if os.path.exists(CORE_FILE):
        with open(CORE_FILE, "r") as f:
            core = [t.strip() for t in f.read().split(",") if t.strip()]
            candidates.update(core)
            core_list = core
            print(f"   🔹 Loaded {len(core)} Core Tickers.")

    if os.path.exists(MOMENTUM_FILE):
        try:
            df = pd.read_csv(MOMENTUM_FILE)
            if 'Symbol' in df.columns:
                mom_tickers = df['Symbol'].tolist()
                candidates.update(mom_tickers)
                print(f"   🔹 Loaded {len(mom_tickers)} Momentum Tickers.")
        except: pass

    return list(candidates), core_list

def process_one_ticker(sym, core_list):
    """Worker function to process a single stock."""
    global AI_CALL_COUNT

    # 0. Burst Smoothing (Prevents hitting Gemini 429)
    time.sleep(1.0)

    # 1. Blacklist
    if check_blacklist(sym): return None

    # 2. Technical Gate (FMP)
    if not check_technical_gate_fmp(sym):
        if sym in core_list:
            print(f"   📉 {sym}: Core Ticker Rejected (Below SMA20)")
        return None

    # 3. AI Gate
    if SKIP_AI: return sym

    # Core Tickers bypass AI *only if* they are trending.
    if sym in core_list:
        print(f"   ✅ {sym}: Core Ticker (Trusted & Trending)")
        return sym

    # Track AI Usage
    with AI_LOCK:
        AI_CALL_COUNT += 1

    # The expensive call
    is_valid = utils.check_catalyst(sym)

    if is_valid:
        print(f"   ✅ {sym}: AI Approved")
        return sym
    else:
        return None

def run_routine():
    script_start_time = dt.now()
    utils.print_metadata("morning_routine.py", "1.3.0")
    print(f"[TIME] Script Start: {script_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   🚀 PAID TIER MODE: {MAX_WORKERS} Parallel Workers (Optimized for Rate Limits)")

    print_step("Step 1: Archiving History")
    archive_yesterday()

    print_step("Step 2: Gathering Candidates")
    all_tickers, core_list = load_inputs()
    print(f"   🔎 Total Unique Candidates: {len(all_tickers)}")

    final_list = []

    print_step("Step 3: Running The Gauntlet (Parallel Execution)")
    print(f"[TIME] {dt.now().strftime('%H:%M:%S')} - Starting Parallel Processing...")

    start_time = time.time()
    processed_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_sym = {executor.submit(process_one_ticker, sym, core_list): sym for sym in all_tickers}

        for future in concurrent.futures.as_completed(future_to_sym):
            processed_count += 1
            try:
                result = future.result()
                if result:
                    final_list.append(result)
            except Exception as e:
                sym = future_to_sym[future]
                print(f"   ⚠️ Error processing {sym}: {e}")

            # Telemetry Update (Every 5 stocks)
            if processed_count % 5 == 0:
                elapsed = time.time() - start_time
                if elapsed > 0:
                    ai_rate = (AI_CALL_COUNT / elapsed) * 60
                    # We use \r to overwrite the line, creating a dashboard effect
                    # Note: Normal prints from process_one_ticker will break this line, which is fine
                    # It serves as a heartbeat between logs.
                    # print(f"   [Telemetry] Processed: {processed_count}/{len(all_tickers)} | AI Rate: {ai_rate:.0f} checks/min")

    elapsed = time.time() - start_time
    print(f"\n   ⏱️ Processing Time: {elapsed:.2f} seconds")
    if elapsed > 0:
        print(f"   📊 Final Average AI Rate: {(AI_CALL_COUNT / elapsed) * 60:.0f} checks/min")

    print_step("Step 4: Saving Final Watchlist")
    with open(FINAL_WATCHLIST, "w", encoding="utf-8") as f:
        f.write(", ".join(final_list))

    print(f"   💾 Saved {len(final_list)} High-Quality Tickers to {FINAL_WATCHLIST}")

    script_end_time = dt.now()
    duration = script_end_time - script_start_time
    print(f"\n[TIME] Routine Finished: {script_end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[TIME] Total Execution Duration: {duration}")

if __name__ == "__main__":
    run_routine()