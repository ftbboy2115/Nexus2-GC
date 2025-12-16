"""
Project: Portfolio Manager (The "Empty Account" Fix)
Version: 2.0.1
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-15

Changelog:
- v2.0.1: LOGIC FIX.
          - Added 'success' flag to get_alpaca_data().
          - Fixed bug where empty account caused fallback to old file data.
          - Now correctly clears portfolio file if Account B is empty.
- v2.0.0: Config Integration.
"""
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import os
import datetime
import time
import contextlib
import sys
import requests
import pytz
import argparse

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- MODULE IMPORTS ---
import config

# --- CONFIGURATION ---
ALPACA_KEY = config.ALPACA_KEY_B
ALPACA_SECRET = config.ALPACA_SECRET_B
ALPACA_URL = config.ALPACA_BASE_URL

PORTFOLIO_FILE = config.PORTFOLIO_FILE
TRADE_LOG_FILE = config.TRADE_LOG_FILE
RISK_REPORT_FILE = config.RISK_REPORT_CSV

if not ALPACA_KEY:
    print("[ERROR] Alpaca API Keys (Account B) not found in config.")
    sys.exit(1)

# ==============================================================================
# 1. MEMORY & LOGGING
# ==============================================================================
def log_trade(symbol, action, qty, price):
    """Appends execution to trade_log.csv."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_row = pd.DataFrame([{
        "Time": timestamp, "Symbol": symbol, "Action": action,
        "Qty": qty, "Price": price, "Status": "FILLED"
    }])

    header = not os.path.exists(TRADE_LOG_FILE)
    if header:
        new_row.to_csv(TRADE_LOG_FILE, index=False)
    else:
        new_row.to_csv(TRADE_LOG_FILE, mode='a', header=False, index=False)

def check_recent_action(symbol):
    """Checks trade_log.csv for actions taken TODAY."""
    if not os.path.exists(TRADE_LOG_FILE): return None
    try:
        df = pd.read_csv(TRADE_LOG_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
        today = datetime.datetime.now().date()
        actions = df[(df['Time'].dt.date == today) & (df['Symbol'] == symbol) & (df['Status'] == 'FILLED')]
        if not actions.empty: return actions.iloc[-1]['Action']
    except: pass
    return None

def get_entry_date_local(symbol):
    if not os.path.exists(TRADE_LOG_FILE): return None
    try:
        df = pd.read_csv(TRADE_LOG_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
        buys = df[(df['Symbol'] == symbol) & (df['Action'] == 'BUY') & (df['Status'] == 'FILLED')]
        if not buys.empty: return buys.iloc[-1]['Time'].strftime("%Y-%m-%d")
    except: pass
    return None

# ==============================================================================
# 2. ALPACA INTERFACE
# ==============================================================================
def get_headers():
    return {"APCA-API-KEY-ID": ALPACA_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET}

def execute_batch_order(tickers, action):
    """Executes market SELLS for a list of tickers."""
    headers = get_headers()
    print(f"\n🚀 EXECUTING BATCH {action}...")

    try:
        r = requests.get(f"{ALPACA_URL}/v2/positions", headers=headers)
        positions = {p['symbol']: int(p['qty']) for p in r.json()}
    except Exception as e:
        print(f"❌ Error fetching positions: {e}")
        return

    for sym in tickers:
        qty_owned = positions.get(sym, 0)
        if qty_owned == 0:
            print(f"   ⚠️ {sym}: No position found. Skipping.")
            continue

        qty_to_sell = qty_owned
        if action == "TRIM":
            qty_to_sell = max(1, int(qty_owned / 3))

        print(f"   ➤ {action} {sym}: {qty_to_sell} shares...", end="")

        order_data = {
            "symbol": sym, "qty": qty_to_sell, "side": "sell",
            "type": "market", "time_in_force": "gtc"
        }

        try:
            r = requests.post(f"{ALPACA_URL}/v2/orders", json=order_data, headers=headers)
            if r.status_code in [200, 201]:
                print(" ✅ FILLED")
                log_trade(sym, action, qty_to_sell, 0.0)
            else:
                print(f" ❌ FAILED ({r.json()})")
        except Exception as e:
            print(f" ❌ ERROR: {e}")
        time.sleep(0.2)

def get_alpaca_data():
    """
    Returns (Success_Flag, Position_Map, History_Map)
    Success_Flag allows differentiation between 'Empty Account' (True) and 'API Fail' (False).
    """
    if not ALPACA_KEY: return False, {}, {}
    headers = get_headers()
    pos_map, history_map = {}, {}
    sell_accumulator = {}

    try:
        # 1. Active Positions
        r_pos = requests.get(f"{ALPACA_URL}/v2/positions", headers=headers)
        r_pos.raise_for_status()

        # If we get here, connection is GOOD.
        # Even if list is empty, that is a valid state.

        for p in r_pos.json():
            sym = p['symbol']
            pos_map[sym] = {
                'qty': int(p['qty']),
                'avg_entry_price': float(p['avg_entry_price']),
                'unrealized_pl': float(p['unrealized_pl']),
                'unrealized_plpc': float(p['unrealized_plpc']),
                'market_value': float(p['market_value']),
                'cost_basis': float(p['cost_basis'])
            }
            sell_accumulator[sym] = 0

        # 2. Order History
        params = {"status": "closed", "direction": "desc", "limit": 500, "nested": True}
        r_hist = requests.get(f"{ALPACA_URL}/v2/orders", headers=headers, params=params)
        orders = r_hist.json()

        for sym in pos_map:
            last_buy_time = None
            for o in orders:
                if o['symbol'] == sym and o['side'] == 'buy' and o['status'] == 'filled':
                     filled_at = o.get('filled_at')
                     if filled_at:
                         history_map[sym] = filled_at.split('T')[0]
                         last_buy_time = filled_at
                         break

            if last_buy_time:
                for o in orders:
                    if o['symbol'] == sym and o['side'] == 'sell' and o['status'] == 'filled':
                        filled_at = o.get('filled_at')
                        if filled_at and filled_at > last_buy_time:
                            sell_accumulator[sym] += int(o.get('filled_qty', 0))

        for sym, data in pos_map.items():
            data['initial_qty'] = data['qty'] + sell_accumulator.get(sym, 0)

        return True, pos_map, history_map

    except Exception as e:
        print(f"[WARN] Alpaca Sync failed: {e}")
        return False, {}, {}

def sync_portfolio():
    print("Syncing with Alpaca (Account B)...")
    success, pos_map, history_map = get_alpaca_data()

    # CASE 1: CONNECTION SUCCESSFUL (Even if empty)
    if success:
        tickers = list(pos_map.keys())
        # Always update the file to reflect the TRUE state (even if empty)
        with open(PORTFOLIO_FILE, "w") as f: f.write(", ".join(tickers))
        return tickers, pos_map, history_map

    # CASE 2: CONNECTION FAILED -> FALLBACK
    print("[WARN] Using local backup file.")
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r") as f:
            tickers = [t.strip().upper() for t in f.read().replace('\n', ',').split(',') if t.strip()]
            return tickers, {}, {}

    return [], {}, {}

@contextlib.contextmanager
def suppress_stderr():
    with open(os.devnull, "w") as devnull:
        old = sys.stderr; sys.stderr = devnull
        try: yield
        finally: sys.stderr = old

def get_data(symbol):
    for _ in range(3):
        try:
            with suppress_stderr():
                df = yf.download(symbol, period="6mo", interval="1d", progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            if len(df) > 50: return df
        except: time.sleep(1)
    return None

# ==============================================================================
# 3. RISK LOGIC
# ==============================================================================
def calculate_priority_score(row):
    status = row['Status']
    days = row['DaysHeld']
    is_new = (days == 0)

    base_map = {
        "[SELL]": 0, "[TRIM]": 10, "[WARN]": 20,
        "[WATCH]": 50, "[HOLD]": 100, "[TRIMMED]": 110,
        "[CLOSED]": 120, "[ERROR]": 999
    }
    score = base_map.get(status, 999)

    if is_new and status not in ["[SELL]", "[TRIM]", "[WARN]"]:
        score += 500

    return score

def check_position(symbol, financial_data, history_date):
    df = get_data(symbol)

    qty = financial_data.get('qty', 0)
    avg_price = financial_data.get('avg_entry_price', 0.0)
    pl_dol = financial_data.get('unrealized_pl', 0.0)
    pl_pct = financial_data.get('unrealized_plpc', 0.0)
    cost_basis = financial_data.get('cost_basis', 0.0)
    market_val = financial_data.get('market_value', 0.0)
    init_qty = financial_data.get('initial_qty', qty)

    entry_date = get_entry_date_local(symbol)
    if not entry_date and history_date: entry_date = history_date
    if not entry_date: entry_date = "N/A"

    days_held = 0
    if entry_date != "N/A":
        try:
            d_entry = datetime.datetime.strptime(entry_date, "%Y-%m-%d").date()
            d_today = datetime.datetime.now().date()
            days_held = (d_today - d_entry).days
            if days_held < 0: days_held = 0
        except: pass

    if df is None:
        return {
            "Symbol": symbol, "Status": "[ERROR]", "Reason": "No Data",
            "EntryDate": entry_date, "DaysHeld": days_held,
            "AvgPrice": avg_price, "PL_Dol": pl_dol, "PL_Pct": pl_pct,
            "Qty": qty, "InitQty": init_qty, "CostBasis": cost_basis, "MarketVal": market_val,
            "Price": 0.0, "Last_Updated": datetime.datetime.now().strftime("%H:%M:%S")
        }

    today = df.iloc[-1]
    price = float(today['Close'])
    ema_10 = df.ta.ema(length=10).iloc[-1]
    sma_20 = df.ta.sma(length=20).iloc[-1]
    sma_50 = df.ta.sma(length=50).iloc[-1]

    status = "[HOLD]"
    reason = "Trend Intact"
    now_et = datetime.datetime.now(pytz.timezone('US/Eastern'))
    is_decision_time = (now_et.hour >= 15 and now_et.minute >= 45) or now_et.hour >= 16

    if price < sma_20:
        status = "[SELL]" if is_decision_time else "[WATCH]"
        reason = f"Below 20SMA ({sma_20:.2f})"
    elif price < ema_10:
        status = "[WARN]" if is_decision_time else "[WATCH]"
        reason = f"Below 10EMA ({ema_10:.2f})"

    dist_50 = (price - sma_50) / sma_50
    if dist_50 > 0.30:
        status = "[TRIM]"
        reason = f"Extended {dist_50:.1%} > 50SMA"
    elif pl_pct > 0.20 and days_held < 5:
        status = "[TRIM]"
        reason = "Super-Momentum (>20% in <5d)"

    recent_action = check_recent_action(symbol)
    if recent_action == "TRIM":
        status = "[TRIMMED]"
        reason = "Risk reduced today"
    elif recent_action == "SELL":
        status = "[CLOSED]"
        reason = "Position sold today"

    return {
        "Symbol": symbol, "Status": status, "Price": price, "Reason": reason,
        "EntryDate": entry_date, "DaysHeld": days_held,
        "AvgPrice": avg_price, "PL_Dol": pl_dol, "PL_Pct": pl_pct,
        "Qty": qty, "InitQty": init_qty,
        "CostBasis": cost_basis, "MarketVal": market_val,
        "Last_Updated": datetime.datetime.now().strftime("%H:%M:%S")
    }

# ==============================================================================
# 4. MAIN EXECUTION
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sell", nargs="+", help="List of symbols to SELL ALL")
    parser.add_argument("--trim", nargs="+", help="List of symbols to TRIM (1/3)")
    args = parser.parse_args()

    if args.sell:
        execute_batch_order(args.sell, "SELL")
        sys.exit(0)

    if args.trim:
        execute_batch_order(args.trim, "TRIM")
        sys.exit(0)

    print("### PORTFOLIO RISK MANAGER (v2.0.1) ###")
    tickers, pos_map, history_map = sync_portfolio()

    # FIX: Even if empty, we want to save the empty report to clear the dashboard
    if not tickers:
        print("[INFO] Account is empty. Clearing Risk Report.")
        pd.DataFrame(columns=["Symbol", "Status", "Last_Updated"]).to_csv(RISK_REPORT_FILE, index=False)
        sys.exit(0)

    print(f"\n[SCAN] Analyzing {len(tickers)} positions...\n")
    results = []

    for i, ticker in enumerate(tickers):
        print(f"\r   [{i+1}/{len(tickers)}] Checking {ticker:<5}...", end="")
        fin_data = pos_map.get(ticker, {})
        hist_date = history_map.get(ticker, None)
        results.append(check_position(ticker, fin_data, hist_date))
        time.sleep(0.1)

    if results:
        df = pd.DataFrame(results)
        df['Price'] = df['Price'].round(2)
        df['AvgPrice'] = df['AvgPrice'].round(2)
        df['PL_Dol'] = df['PL_Dol'].round(2)
        df['PL_Pct'] = df['PL_Pct'].round(4)
        df['CostBasis'] = df['CostBasis'].round(2)
        df['MarketVal'] = df['MarketVal'].round(2)

        df['Sort'] = df.apply(calculate_priority_score, axis=1)
        df = df.sort_values('Sort').drop('Sort', axis=1)

        print("\n\n" + df.to_string(index=False))

        export = df.copy()
        emoji_map = {
            "[SELL]": "🚨 SELL", "[WATCH]": "👀 WATCH", "[WARN]": "⚠️ WARN",
            "[TRIM]": "💰 TRIM", "[TRIMMED]": "✅ TRIMMED",
            "[CLOSED]": "✅ CLOSED", "[HOLD]": "✅ HOLD", "[ERROR]": "⚠️ ERROR"
        }
        export['Status'] = export['Status'].replace(emoji_map)
        export.to_csv(RISK_REPORT_FILE, index=False)