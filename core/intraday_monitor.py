"""
Project: Intraday Sniper (The "Trend Guard" Update)
Filename: core/intraday_monitor.py
Version: 2.0.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-14

Changelog:
- v2.0.0: Added "Trust but Verify" Safety Layer.
          - Calculates 20SMA & Prev Close before accepting a ticker.
          - Rejects stocks trading below 20SMA (Downtrend) or below Prev Close (Red).
          - Prevents "Buying the Dip" on broken charts.
- v1.8.0: Parallel Initialization.
"""

import requests
import pandas as pd
import time
import os
import sys
import datetime
import pytz
import json
import threading
import concurrent.futures
from dotenv import load_dotenv

# IMPORT EXECUTION ENGINE
# (Path patching in Launcher allows this import to work)
import paper_trader

# --- CONFIGURATION ---
SCRIPT_NAME = os.path.basename(__file__)
SCRIPT_VERSION = "2.0.0"
WATCHLIST_FILE = os.path.join("data", "watchlist.txt")  # UPDATED PATH
ALERTS_FILE = os.path.join("data", "daily_alerts.csv")  # UPDATED PATH
KILL_SWITCH_FILE = "STOP_SNIPER" # Stays in root for easy access
CONFIG_FILE = "trading_config.json"
CHECK_INTERVAL = 10
ORB_WINDOW = 5

# WORKER SETTINGS
MAX_WORKERS = 10

# --- TESTING MODE ---
TESTING_MODE = False

load_dotenv()
FMP_KEY = os.environ.get("FMP_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK")

# THREAD LOCK
safe_lock = threading.Lock()

# ==============================================================================
# 0. METADATA HEADER
# ==============================================================================
def print_metadata():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 60)
    print(f"📜 SCRIPT:   {SCRIPT_NAME}")
    print(f"🔢 VERSION:  {SCRIPT_VERSION}")
    print(f"⏰ TIME:     {now}")
    print(f"🛡️ SAFETY:   Trend Filter (20SMA) + Gap Filter (Green)")
    if TESTING_MODE:
        print(f"🧪 TESTING:  ENABLED (Time Travel to 10:00 AM)")
    print("=" * 60 + "\n")

# ==============================================================================
# 1. UTILITIES
# ==============================================================================
def check_kill_switch():
    if os.path.exists(KILL_SWITCH_FILE):
        with safe_lock:
            print(f"\n[TIME] {datetime.datetime.now().strftime('%H:%M:%S')} - 🛑 KILL SWITCH DETECTED. SHUTTING DOWN SNIPER.")
        sys.exit(0)

def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        print(f"⚠️ Watchlist not found: {WATCHLIST_FILE}")
        return ["NVDA", "TSLA", "PLTR"]

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        content = f.read()
        raw = [t.strip() for t in content.replace('\n', ',').split(',') if t.strip()]
        clean_tickers = []
        for r in raw:
            ticker = r.split('(')[0].strip()
            if ticker: clean_tickers.append(ticker)
        return list(set(clean_tickers))

def get_realtime_quote(symbol):
    url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={FMP_KEY}"
    try:
        res = requests.get(url, timeout=5).json()
        if res: return res[0]
    except: pass
    return None

# --- NEW SAFETY HELPER ---
def get_daily_technicals(symbol):
    """Fetches daily candles to calculate 20SMA and get Prev Close."""
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}?timeseries=50&apikey={FMP_KEY}"
    try:
        res = requests.get(url, timeout=5).json()
        if 'historical' not in res: return None

        df = pd.DataFrame(res['historical'])
        # FMP is Newest First. We need Oldest First for rolling calc.
        df = df.iloc[::-1].reset_index(drop=True)

        df['SMA20'] = df['close'].rolling(20).mean()

        last_close = df['close'].iloc[-1]
        sma20 = df['SMA20'].iloc[-1]

        return {"PrevClose": last_close, "SMA20": sma20}
    except: return None

def get_intraday_chart(symbol):
    url = f"https://financialmodelingprep.com/api/v3/historical-chart/1min/{symbol}?apikey={FMP_KEY}"
    try:
        res = requests.get(url, timeout=5).json()
        df = pd.DataFrame(res)
        df['date'] = pd.to_datetime(df['date'])
        today = datetime.datetime.now().date()
        df = df[df['date'].dt.date == today]
        if df.empty: return None
        df = df.sort_values('date')
        return df
    except: return None

def save_alert(data):
    with safe_lock:
        try:
            file_exists = os.path.exists(ALERTS_FILE)
            df = pd.DataFrame([data])
            df.to_csv(ALERTS_FILE, mode='a', header=not file_exists, index=False)
        except Exception as e:
            print(f"   ❌ Error saving alert: {e}")

# ==============================================================================
# 2. NOTIFICATION LOGIC
# ==============================================================================
def send_discord_alert(symbol, price, stop):
    if not DISCORD_URL: return

    notifications_on = True
    if os.path.exists(CONFIG_FILE):
        try:
            cfg = json.load(open(CONFIG_FILE))
            notifications_on = cfg.get("notifications", True)
        except: pass

    if not notifications_on: return

    payload = {
        "content": f"🚨 **SNIPER ALERT: {symbol}**\n🚀 Breakout Price: ${price:.2f}\n🛑 Stop Loss: ${stop:.2f}"
    }
    try:
        requests.post(DISCORD_URL, json=payload, timeout=3)
    except: pass

# ==============================================================================
# 3. ORB LOGIC & SAFETY CHECK
# ==============================================================================
def calculate_orb(symbol):
    df = get_intraday_chart(symbol)
    if df is None or len(df) < ORB_WINDOW: return None
    orb_slice = df.head(ORB_WINDOW)
    return {"ORH": orb_slice['high'].max(), "ORL": orb_slice['low'].min()}

def setup_one_ticker(sym):
    check_kill_switch()

    # 1. SAFETY CHECK (The Trust but Verify Layer)
    techs = get_daily_technicals(sym)
    quote = get_realtime_quote(sym)

    if not techs or not quote:
        return None # Can't verify, so safe skip

    current_price = quote['price']
    sma20 = techs['SMA20']
    prev_close = techs['PrevClose']

    # RULE A: Must be above 20SMA (Trend Alignment)
    if current_price < sma20:
        with safe_lock:
            print(f"   ⛔ {sym:<5}: REJECTED (Below 20SMA: ${sma20:.2f})")
        return None

    # RULE B: Must be Green (Gap Up / Momentum)
    # We allow slight red (-0.5%) if trending hard, but generally prefer green.
    if current_price < (prev_close * 0.995):
        with safe_lock:
            print(f"   ⛔ {sym:<5}: REJECTED (Fading/Gap Down)")
        return None

    # 2. ORB CALCULATION
    levels = calculate_orb(sym)
    if levels:
        return sym, levels

    return None

# ==============================================================================
# 4. THREADED SCANNER WORKER
# ==============================================================================
orb_levels = {}
triggered = []

def scan_one_ticker(sym):
    if sym in triggered: return
    if os.path.exists(KILL_SWITCH_FILE): return

    quote = get_realtime_quote(sym)
    if not quote: return

    price = quote['price']
    if sym not in orb_levels: return

    orh = orb_levels[sym]['ORH']
    stop = orb_levels[sym]['ORL']

    if price > orh:
        if TESTING_MODE:
            now_str = (datetime.datetime.now(pytz.timezone('US/Eastern')) + time_travel_offset).strftime('%H:%M:%S')
        else:
            now_str = datetime.datetime.now().strftime('%H:%M:%S')

        with safe_lock:
            print(f"\n\n[TIME] {now_str} - 🚨 BREAKOUT: {sym} @ ${price:.2f}")
            triggered.append(sym)

        save_alert({
            "Time": now_str,
            "Symbol": sym,
            "Action": "BUY",
            "Price": f"${price:.2f}",
            "Trigger": "ORB Breakout",
            "Stop Loss": f"${stop:.2f}"
        })

        send_discord_alert(sym, price, stop)

        with safe_lock:
            print(f"   🚀 SENDING ORDER TO ALPACA...")

        paper_trader.submit_buy_order(sym, price, stop)

# ==============================================================================
# 5. MAIN SNIPER LOOP
# ==============================================================================
time_travel_offset = datetime.timedelta(0)

if __name__ == "__main__":
    script_start_time = datetime.datetime.now()
    print_metadata()
    print(f"[TIME] Script Start: {script_start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    if not FMP_KEY:
        print("❌ ERROR: FMP_API_KEY missing.")
        sys.exit()

    if TESTING_MODE:
        real_startup_time = datetime.datetime.now(pytz.timezone('US/Eastern'))
        target_sim_start = real_startup_time.replace(hour=10, minute=0, second=0, microsecond=0)
        time_travel_offset = target_sim_start - real_startup_time
        print(f"🔮 TIME TRAVEL ENGAGED: Offset {time_travel_offset}")

    tickers = load_watchlist()
    print(f"🎯 Monitoring {len(tickers)} stocks...")

    try:
        while True:
            check_kill_switch()

            real_now = datetime.datetime.now(pytz.timezone('US/Eastern'))
            now_et = real_now + time_travel_offset

            market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            orb_finish = market_open + datetime.timedelta(minutes=ORB_WINDOW)

            if now_et < market_open:
                print(f"\r⏳ Pre-Market. Waiting... ({now_et.strftime('%H:%M:%S')})", end="")
                time.sleep(30)
                continue

            if now_et > market_close:
                print(f"\n[TIME] {now_et.strftime('%H:%M:%S')} - 🌑 Market Closed. Sniper shutting down.")
                break

            if now_et < orb_finish:
                print(f"\r⏳ Market Open! Forming Range... ({now_et.strftime('%H:%M:%S')})", end="")
                time.sleep(15)
                continue

            # --- PARALLEL INITIALIZATION BLOCK ---
            if len(orb_levels) < len(tickers) and not orb_levels:
                print(f"\n\n[TIME] {now_et.strftime('%H:%M:%S')} - 🛡️ SAFETY CHECK & RANGE CALC (Parallel)...")
                calc_start_time = time.time()

                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    results = executor.map(setup_one_ticker, tickers)

                    for res in results:
                        if res:
                            sym, levels = res
                            orb_levels[sym] = levels
                            print(f"   ✅ {sym:<5}: Buy > ${levels['ORH']:.2f}")

                print(f"   ⏱️ Setup Duration: {time.time() - calc_start_time:.2f}s")
                print(f"   🎯 Active Targets: {len(orb_levels)}/{len(tickers)}")

            # --- HUNTING BLOCK ---
            if orb_levels:
                print(f"\r👀 Scanning Prices... ({now_et.strftime('%H:%M:%S')})", end="")

                # Heartbeat for Dashboard
                with open(os.path.join("data", "sniper.log"), "a") as f: pass

                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    executor.map(scan_one_ticker, list(orb_levels.keys()))

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n🛑 Sniper Deactivated.")