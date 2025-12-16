"""
Project: The Execution Engine (The "Conflict Resolution" Update)
Version: 2.9.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-15

Changelog:
- v2.9.0: CONFIG INTEGRATION & ACCOUNT B DEFAULT.
          - Replaced hardcoded Env vars with 'config' module imports.
          - Now defaults to ALPACA_KEY_B (The new Nexus Account).
          - Added sys.path hack to allow importing 'config' from parent dir.
- v2.8.0: Switched TIF to 'day'.
"""
import requests
import os
import math
import json
import sys
import datetime
import pandas as pd

# --- PATH SETUP (CRITICAL) ---
# Add the project root (Nexus/) to sys.path so we can import 'config' and 'utils'
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- MODULE IMPORTS ---
import config

# --- CONFIGURATION ---
# CRITICAL: Default to Account B (Nexus Local) for this instance
API_KEY = config.ALPACA_KEY_B
SECRET_KEY = config.ALPACA_SECRET_B
BASE_URL = config.ALPACA_BASE_URL

# Use paths from config to prevent duplication/errors
KILL_SWITCH_FILE = config.KILL_SWITCH_FILE  # e.g., "STOP_SNIPER"
CONFIG_FILE = config.USER_CONFIG_FILE       # e.g., "data/trading_config.json"
LOG_FILE = config.TRADE_LOG_FILE            # e.g., "data/trade_log.csv"

if not API_KEY:
    print("[ERROR] Alpaca API Keys (Account B) not found in config.")
    exit()

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": SECRET_KEY,
    "Content-Type": "application/json"
}

# ==============================================================================
# 2. LOGGING ENGINE
# ==============================================================================
def log_trade_event(symbol, action, quantity, price, status, details):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_row = {"Time": timestamp, "Symbol": symbol, "Action": action, "Qty": quantity, "Price": price, "Status": status, "Details": str(details)}
    try:
        df = pd.DataFrame([new_row])
        header = not os.path.exists(LOG_FILE)
        df.to_csv(LOG_FILE, mode='a', header=header, index=False)
    except Exception as e: print(f"   [ERROR] Log failed: {e}")

# ==============================================================================
# 3. UTILITIES
# ==============================================================================
def load_config():
    defaults = {"max_position_size": 500, "max_account_risk": 2000, "notifications": True}
    if os.path.exists(CONFIG_FILE):
        try: return json.load(open(CONFIG_FILE))
        except: pass
    return defaults

def get_account():
    try:
        r = requests.get(f"{BASE_URL}/v2/account", headers=HEADERS)
        r.raise_for_status(); return r.json()
    except Exception as e: print(f"[ERROR] Account check failed: {e}"); return None

def get_positions():
    try:
        r = requests.get(f"{BASE_URL}/v2/positions", headers=HEADERS)
        return r.json()
    except: return []

def get_position(symbol):
    try:
        r = requests.get(f"{BASE_URL}/v2/positions/{symbol}", headers=HEADERS)
        if r.status_code == 404: return None
        r.raise_for_status()
        return r.json()
    except: return None

def check_gatekeeper():
    # Kill switch file is in the ROOT (managed by config.KILL_SWITCH_FILE)
    if os.path.exists(KILL_SWITCH_FILE): print("[BLOCKED] STOP_SNIPER active."); return False
    return True

def cancel_open_orders(symbol):
    """Cancels any open orders for a specific symbol to unlock shares."""
    print(f"   [INFO] Checking open orders for {symbol}...")
    try:
        # 1. Get open orders only for this symbol
        r = requests.get(f"{BASE_URL}/v2/orders", headers=HEADERS, params={"status": "open", "symbols": symbol})
        orders = r.json()

        if not orders:
            return

        print(f"   [WARN] Found {len(orders)} open order(s). Canceling to unlock shares...")

        # 2. Cancel them individually
        for o in orders:
            requests.delete(f"{BASE_URL}/v2/orders/{o['id']}", headers=HEADERS)

        print(f"   [OK] Orders canceled. Shares unlocked.")
    except Exception as e:
        print(f"   [WARN] Failed to cancel orders: {e}")

# ==============================================================================
# 4. SELLING LOGIC (CONFLICT FREE)
# ==============================================================================
def close_position(symbol):
    print(f"\n[INFO] CLOSING POSITION: {symbol}...")

    # NEW: Unlock shares first
    cancel_open_orders(symbol)

    pos = get_position(symbol)
    if not pos:
        print(f"   [SKIP] No position found for {symbol}.")
        return

    qty = pos['qty']
    try:
        r = requests.delete(f"{BASE_URL}/v2/positions/{symbol}", headers=HEADERS)
        r.raise_for_status()
        print(f"   [OK] CLOSED: Sold {qty} shares of {symbol}.")
        log_trade_event(symbol, "SELL", qty, "MKT", "FILLED", "Manual Close")
    except Exception as e:
        print(f"   [ERROR] Error closing {symbol}: {e}")
        log_trade_event(symbol, "SELL", qty, "MKT", "FAILED", str(e))

def trim_position(symbol, pct=0.33):
    print(f"\n[INFO] TRIMMING {symbol} by {pct*100}%...")

    # NEW: Unlock shares first
    cancel_open_orders(symbol)

    pos = get_position(symbol)
    if not pos:
        print(f"   [SKIP] No position found for {symbol}.")
        return

    total_qty = int(pos['qty'])
    trim_qty = math.floor(total_qty * pct)

    if trim_qty < 1:
        print(f"   [SKIP] Position too small to trim ({total_qty} shares).")
        return

    order_data = {
        "symbol": symbol,
        "qty": trim_qty,
        "side": "sell",
        "type": "market",
        "time_in_force": "day" # CHANGED: Day order (was GTC)
    }

    try:
        r = requests.post(f"{BASE_URL}/v2/orders", json=order_data, headers=HEADERS)
        r.raise_for_status()
        print(f"   [OK] TRIMMED: Sold {trim_qty} shares of {symbol}.")
        log_trade_event(symbol, "TRIM", trim_qty, "MKT", "FILLED", f"Trimmed {pct*100}%")
    except Exception as e:
        print(f"   [ERROR] Error trimming {symbol}: {e}")
        log_trade_event(symbol, "TRIM", trim_qty, "MKT", "FAILED", str(e))

def close_all_positions():
    print("\n[ALERT] LIQUIDATING ALL...")
    with open(KILL_SWITCH_FILE, "w") as f: f.write("LOCKED")
    try:
        requests.delete(f"{BASE_URL}/v2/orders", headers=HEADERS)
        r = requests.delete(f"{BASE_URL}/v2/positions", headers=HEADERS, params={"cancel_orders": True})
        print(f"   [OK] Liquidation command sent.")
    except Exception as e: print(f"[ERROR] {e}")

# ==============================================================================
# 5. BUY LOGIC
# ==============================================================================
def calculate_smart_qty(symbol, entry_price, stop_loss, equity, buying_power, config):
    max_pos = float(config.get("max_position_size", 500))
    risk_dollars = equity * config.get("risk_per_trade_pct", 0.01)
    risk_per_share = entry_price - stop_loss

    qty_risk = math.floor(risk_dollars / risk_per_share) if risk_per_share > 0 else 0
    qty_cap = math.floor(max_pos / entry_price)
    final_qty = min(qty_risk, qty_cap)

    if (final_qty * entry_price) > buying_power: final_qty = math.floor(buying_power / entry_price)
    return int(final_qty)

def submit_buy_order(symbol, entry_price, stop_loss):
    if not check_gatekeeper(): return
    print(f"\n[INFO] BUYING: {symbol}...")
    acct = get_account()
    if not acct: return

    for p in get_positions():
        if p['symbol'] == symbol: print(f"   [SKIP] Held."); return

    config = load_config()
    if (float(acct['equity']) - float(acct['cash'])) >= float(config.get("max_account_risk", 2000)):
        print("   [SKIP] Max Risk Reached."); return

    qty = calculate_smart_qty(symbol, entry_price, stop_loss, float(acct['equity']), float(acct['buying_power']), config)
    if qty < 1: return

    order = {
        "symbol": symbol,
        "qty": qty,
        "side": "buy",
        "type": "market",
        "time_in_force": "day", # CHANGED: Day order (was GTC)
        "order_class": "oto",
        "stop_loss": {"stop_price": round(stop_loss, 2)}
    }
    try:
        r = requests.post(f"{BASE_URL}/v2/orders", json=order, headers=HEADERS)
        r.raise_for_status()
        log_trade_event(symbol, "BUY", qty, entry_price, "FILLED", f"ID: {r.json()['id']}")
        print(f"   [OK] BOUGHT {qty} {symbol}")
    except Exception as e:
        print(f"   [ERROR] Failed: {e}")
        log_trade_event(symbol, "BUY", qty, entry_price, "FAILED", str(e))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--close-all": close_all_positions()
        elif cmd == "--unlock":
            if os.path.exists(KILL_SWITCH_FILE): os.remove(KILL_SWITCH_FILE)
        elif cmd == "--sell" and len(sys.argv) > 2:
            close_position(sys.argv[2])
        elif cmd == "--trim" and len(sys.argv) > 2:
            trim_position(sys.argv[2], 0.33)
    else:
        acct = get_account()
        if acct: print(f"[OK] Alpaca Connected. Equity: ${float(acct['equity']):,.2f}")