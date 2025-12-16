"""
Project: Real-Time Momentum Scanner (The "Governor" Update)
Filename: core/real_time_scanner.py
Version: 3.9.6
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-15

Changelog:
- v3.9.6: PATH FIX. Added dynamic path setup to find config.py.
- v3.9.5: API RATE LIMITER.
"""
import matplotlib
matplotlib.use("Agg")

import pandas as pd
import requests
import time
import os
import sys
import mplfinance as mpf
import shutil
import threading
import concurrent.futures
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

# ==============================================================================
# CONFIGURATION
# ==============================================================================
BLACKLIST_SECTORS = ["Aerospace & Defense", "Tobacco"]
BLACKLIST_TICKERS = ["PLBY"]

MIN_MARKET_CAP = 200_000_000
MIN_FLOAT      = 20_000_000
MIN_DOLLAR_VOL = 25_000_000
MIN_PRICE      = 5.00

# THREADING SETTINGS
MAX_WORKERS = 6
MAX_WORKERS = MAX_WORKERS * 9.5 ########### Night-time rate - System seems to move much slower at night
API_DELAY = .9

PLOT_LOCK = threading.Lock()
API_LOCK = threading.Lock()
API_CALL_COUNT = 0

# ==============================================================================
# 0. UTILS
# ==============================================================================
def safe_save_csv(df, filepath):
    temp_file = filepath + ".tmp"
    try:
        df.to_csv(temp_file, index=False)
        shutil.move(temp_file, filepath)
    except: pass

def check_blacklist(candidate):
    symbol = candidate.get('symbol', '').upper()
    sector = candidate.get('sector', 'Unknown')
    industry = candidate.get('industry', 'Unknown')

    if symbol in BLACKLIST_TICKERS: return True
    for banned in BLACKLIST_SECTORS:
        if banned in sector or banned in industry: return True
    return False

# ==============================================================================
# 1. DATA SOURCE (FMP EXCLUSIVE)
# ==============================================================================
def get_candidates():
    if config.FMP_KEY:
        print(f"[TIME] {datetime.now().strftime('%H:%M:%S')} - Connecting to FMP Screener...")
        url = (f"https://financialmodelingprep.com/api/v3/stock-screener"
               f"?marketCapMoreThan={MIN_MARKET_CAP}&priceMoreThan={MIN_PRICE}"
               f"&volumeMoreThan=500000&isEtf=false&exchange=NASDAQ,NYSE,AMEX"
               f"&limit=3000&apikey={config.FMP_KEY}")
        try:
            res = requests.get(url, timeout=10).json()
            candidates = []
            for item in res:
                candidates.append({
                    'symbol': item.get('symbol', '').replace('.', '-'),
                    'sector': item.get('sector', 'Unknown'),
                    'industry': item.get('industry', 'Unknown')
                })
            print(f"[OK] FMP Identified {len(candidates)} candidates.")
            return candidates
        except Exception as e:
            print(f"[WARN] FMP Connection failed: {e}")
            pass

    return [{'symbol': s, 'sector': 'Unknown', 'industry': 'Unknown'} for s in ["NVDA", "TSLA"]]

def get_fmp_candles(symbol):
    if not config.FMP_KEY: return None
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}?timeseries=100&apikey={config.FMP_KEY}"

    try:
        res = requests.get(url, timeout=5).json()
        if 'historical' not in res: return None

        data = res['historical']
        if not data: return None

        df = pd.DataFrame(data)
        df = df.iloc[::-1].reset_index(drop=True)
        df = df.rename(columns={'date': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
        return df
    except: return None

def get_fmp_quote(symbol):
    if not config.FMP_KEY: return None
    url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={config.FMP_KEY}"
    try:
        res = requests.get(url, timeout=5).json()
        if res and isinstance(res, list):
            return res[0]
    except: pass
    return None

def get_benchmark():
    print(f"\n[TIME] {datetime.now().strftime('%H:%M:%S')} - Downloading Benchmark (SPY) via FMP...")
    df = get_fmp_candles("SPY")
    return df if df is not None else pd.DataFrame()

# ==============================================================================
# 2. LOGIC ENGINE (THREAD SAFE)
# ==============================================================================
def analyze_stock(candidate, spy_data):
    global API_CALL_COUNT
    time.sleep(API_DELAY)

    if not isinstance(candidate, dict): return None
    if check_blacklist(candidate): return None
    symbol = candidate['symbol']

    df = get_fmp_candles(symbol)
    with API_LOCK: API_CALL_COUNT += 1

    if df is None or len(df) < 50: return None

    try:
        close = df['Close']
        ema10 = close.ewm(span=10, adjust=False).mean()
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()

        daily_range_pct = (df['High'] - df['Low']) / df['Low']
        adr = daily_range_pct.rolling(20).mean() * 100
        dollar_vol = close.iloc[-1] * df['Volume'].iloc[-1]

        if not spy_data.empty:
            spy_aligned = spy_data.reindex(df.index).ffill()
            rs_score = close.pct_change(50, fill_method=None) - spy_aligned['Close'].pct_change(50, fill_method=None)
        else: rs_score = pd.Series(0, index=df.index)

        p = close.iloc[-1]

        stack_ok = (p > ema10.iloc[-1] > sma20.iloc[-1] > sma50.iloc[-1])
        adr_ok = adr.iloc[-1] > 4.0
        liq_ok = (dollar_vol > MIN_DOLLAR_VOL)

        if not (stack_ok and adr_ok and liq_ok): return None

        quote = get_fmp_quote(symbol)
        with API_LOCK: API_CALL_COUNT += 1

        if not quote: return None

        shares_out = quote.get('sharesOutstanding', 0)
        if shares_out < MIN_FLOAT: return None

        vol_tight = daily_range_pct.iloc[-5:].mean() * 100 < (adr.iloc[-1] * 0.75)
        surfing = abs(p - ema10.iloc[-1]) / ema10.iloc[-1] < 0.04

        grade, display = "TRENDING", "✅ TRENDING"
        if vol_tight and surfing: grade, display = "PERFECT", "⭐⭐⭐ PERFECT"
        elif vol_tight: grade, display = "COILING", "⭐ COILING"
        elif surfing: grade, display = "SURFING", "🌊 SURFING"

        pivot = df['High'].iloc[-20:].max()
        stop = sma20.iloc[-1]

        with PLOT_LOCK:
            save_path = os.path.join(config.CHART_DIR_KK, f"{symbol}.png")
            title = f"[{grade}] {symbol} ({candidate.get('industry')[:15]})\nShares: {shares_out/1_000_000:.1f}M | ADR: {adr.iloc[-1]:.1f}%"
            ap = [mpf.make_addplot(ema10, color='blue', width=1.5), mpf.make_addplot(sma50, color='red', width=1.5)]
            mpf.plot(df, type='candle', style='yahoo', title=title, addplot=ap, volume=False, savefig=save_path)
            matplotlib.pyplot.close('all')

        return {
            "Symbol": symbol,
            "Display": display,
            "Grade": grade,
            "Price": round(p, 2),
            "ADR%": round(adr.iloc[-1], 2),
            "RS_Score": round(rs_score.iloc[-1] * 100, 2),
            "Vol_M": round(dollar_vol / 1_000_000, 1),
            "Float_M": round(shares_out / 1_000_000, 1),
            "Sector": candidate.get('sector', 'Unknown'),
            "Industry": candidate.get('industry', 'Unknown'),
            "Pivot": round(pivot, 2),
            "Stop_Loss": round(stop, 2),
            "Reason": f"Tight & Surfing" if grade == "PERFECT" else "Uptrend"
        }

    except Exception: return None

# ==============================================================================
# 3. EXECUTION
# ==============================================================================
if __name__ == "__main__":
    script_start_time = datetime.now()
    utils.print_metadata(os.path.basename(__file__), "3.9.6")
    print(f"[TIME] Script Start: {script_start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    utils.clean_folder(config.CHART_DIR_KK)

    candidates = get_candidates()
    spy = get_benchmark()

    matches = []
    print(f"\n[TIME] {datetime.now().strftime('%H:%M:%S')} - Scanning {len(candidates)} candidates (Parallel FMP)...")
    print(f"[INFO] Launching {MAX_WORKERS} Worker Threads (GOVERNED MODE).")

    analysis_start = time.time()

    processed_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_candidate = {
            executor.submit(analyze_stock, cand, spy): cand for cand in candidates
        }

        for future in concurrent.futures.as_completed(future_to_candidate):
            processed_count += 1
            try:
                res = future.result()
                if res: matches.append(res)
            except Exception as e: pass

            if processed_count % 5 == 0:
                elapsed = time.time() - analysis_start
                if elapsed > 0:
                    rate = processed_count / elapsed
                    api_rate = (API_CALL_COUNT / elapsed) * 60
                else: rate = 0; api_rate = 0

                print(f"\rScanning {processed_count}/{len(candidates)} | Found: {len(matches)} | Rate: {rate:.1f} stocks/sec | API: {api_rate:.0f} calls/min", end="")

    print("\n\n" + "="*50)
    print(f"[DONE] SCAN COMPLETE. Found {len(matches)} Candidates.")

    if matches:
        df = pd.DataFrame(matches)
        grade_map = {"PERFECT": 0, "COILING": 1, "SURFING": 2, "TRENDING": 3}
        df['Rank'] = df['Grade'].map(grade_map)
        df = df.sort_values(['Rank', 'RS_Score'], ascending=[True, False])

        safe_save_csv(df, config.CSV_FILE)
        print(f"[OK] Results saved to {config.CSV_FILE} (Ready for Manager)")
    else:
        print("[WARN] No matches found.")

    script_end_time = datetime.now()
    duration = script_end_time - script_start_time
    print(f"\n[TIME] Script Finished: {script_end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[TIME] Total Execution Duration: {duration}")