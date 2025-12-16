"""
Project: KK Strategy Audit (The "Smart Risk" Update)
Version: 1.1.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-09

Changelog:
- v1.1.0: Refined Risk Pillar.
          Now identifies specific technical stops (SMA10, SMA20, LOD) vs. Arbitrary stops.
          Consolidated logic for cleaner execution.
- v1.0.0: Initial Audit Logic.
"""
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import requests
import os
import sys
import datetime
import time
import numpy as np
from dotenv import load_dotenv

# CONFIG
TRADE_LOG_FILE = "trade_log.csv"
OUTPUT_FILE = "strategy_audit_report.csv"

load_dotenv()
ALPACA_KEY = os.environ.get("APCA_API_KEY_ID")
ALPACA_SECRET = os.environ.get("APCA_API_SECRET_KEY")
ALPACA_URL = "https://paper-api.alpaca.markets"

# ==============================================================================
# 1. DATA UTILITIES
# ==============================================================================
def get_alpaca_order_details(order_id):
    """Fetches the original order to find the Stop Loss price."""
    if not ALPACA_KEY or not order_id: return None
    headers = {"APCA-API-KEY-ID": ALPACA_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET}

    try:
        r = requests.get(f"{ALPACA_URL}/v2/orders/{order_id}", headers=headers)
        if r.status_code != 200: return None
        data = r.json()

        stop_price = None
        # Check OTO legs (Standard for automated entry)
        if 'legs' in data and data['legs']:
            for leg in data['legs']:
                if leg['type'] == 'stop' or leg['type'] == 'stop_limit':
                    stop_price = float(leg.get('stop_price') or leg.get('stop_limit_price'))
                    break

        # Fallback (Manual entries)
        if not stop_price:
            stop_price = float(data.get('stop_price')) if data.get('stop_price') else None

        return {"fill_price": float(data.get('filled_avg_price', 0) or 0), "stop_price": stop_price}
    except: return None

def get_historical_technicals(symbol, entry_date_str):
    """Reconstructs the chart as it looked on Entry Day."""
    try:
        end_date = datetime.datetime.strptime(entry_date_str, "%Y-%m-%d") + datetime.timedelta(days=1)
        start_date = end_date - datetime.timedelta(days=100)

        df = yf.download(symbol, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if len(df) < 50: return None

        # Calculate Indicators for Context
        df['SMA10'] = df.ta.sma(length=10)
        df['SMA20'] = df.ta.sma(length=20)
        df['SMA50'] = df.ta.sma(length=50)

        # ADR Calculation
        df['HighLowPct'] = (df['High'] - df['Low']) / df['Low']
        df['ADR'] = df['HighLowPct'].rolling(20).mean() * 100

        return df.iloc[-1]
    except: return None

def check_management(symbol, entry_date_str, df_log):
    """Checks if a trim occurred 3-5 days later."""
    entry_dt = pd.to_datetime(entry_date_str)

    future_actions = df_log[
        (df_log['Symbol'] == symbol) &
        (pd.to_datetime(df_log['Time']) > entry_dt) &
        (df_log['Status'] == 'FILLED')
    ].copy()

    if future_actions.empty: return "HOLDING", 0, False

    first_sell = future_actions.iloc[0]
    sell_dt = pd.to_datetime(first_sell['Time'])
    days_held = (sell_dt - entry_dt).days

    action_type = first_sell['Action']
    is_kk_window = (3 <= days_held <= 6)

    return action_type, days_held, is_kk_window

# ==============================================================================
# 2. GRADING ENGINE (REFINED)
# ==============================================================================
def grade_trade(row, df_log):
    symbol = row['Symbol']
    entry_time = row['Time']
    entry_date_str = pd.to_datetime(entry_time).strftime("%Y-%m-%d")

    # 1. Find Order ID
    order_id = None
    if "ID: " in str(row['Details']):
        try: order_id = row['Details'].split("ID: ")[1].strip()
        except: pass

    # 2. Fetch Context
    tech = get_historical_technicals(symbol, entry_date_str)
    order_data = get_alpaca_order_details(order_id)

    if tech is None: return None

    # --- PILLAR 1: SETUP (40 pts) ---
    score_setup = 0
    price = tech['Close']
    is_surfing = (price > tech['SMA10']) and (tech['SMA10'] > tech['SMA20'])

    if is_surfing: score_setup += 20
    elif price > tech['SMA20']: score_setup += 10

    adr = tech['ADR']
    if adr >= 4.0: score_setup += 20
    elif adr >= 2.5: score_setup += 10

    # --- PILLAR 2: RISK (30 pts) [UPDATED] ---
    score_risk = 0
    risk_label = "No Stop ❌"

    if order_data and order_data['stop_price']:
        stop = order_data['stop_price']
        fill = order_data['fill_price']
        risk_pct = abs((fill - stop) / fill) * 100

        # Calculate Technical Distances
        dist_lod = abs(stop - tech['Low']) / tech['Low']
        dist_sma10 = abs(stop - tech['SMA10']) / tech['SMA10']
        dist_sma20 = abs(stop - tech['SMA20']) / tech['SMA20']

        # 2.5% Tolerance for "Touching" a level
        tolerance = 0.025

        if dist_lod <= tolerance:
            score_risk = 30
            risk_label = "LOD ✅"
        elif dist_sma20 <= tolerance:
            score_risk = 30
            risk_label = "SMA20 ✅"
        elif dist_sma10 <= tolerance:
            score_risk = 30
            risk_label = "SMA10 ✅"
        else:
            # Fallback: Was it at least tight?
            if risk_pct < 8.0:
                score_risk = 15
                risk_label = "Tight ⚠️" # Arbitrary but safe
            elif risk_pct < 12.0:
                score_risk = 5
                risk_label = "Wide ⚠️"
            else:
                score_risk = 0
                risk_label = "Loose ❌"
    else:
        score_risk = 0

    # --- PILLAR 3: MANAGEMENT (30 pts) ---
    score_mgmt = 0
    action, days, proper_window = check_management(symbol, entry_date_str, df_log)

    if action == "HOLDING":
        days_since = (datetime.datetime.now() - pd.to_datetime(entry_date_str)).days
        if days_since < 3: score_mgmt += 30
        else: score_mgmt += 10
    elif proper_window: score_mgmt += 30
    else: score_mgmt += 10

    # --- FINAL GRADE ---
    total_score = score_setup + score_risk + score_mgmt

    if total_score >= 90: letter = "A+"
    elif total_score >= 80: letter = "A"
    elif total_score >= 70: letter = "B"
    elif total_score >= 60: letter = "C"
    else: letter = "F"

    return {
        "Date": entry_date_str,
        "Symbol": symbol,
        "Grade": letter,
        "Score": total_score,
        "ADR%": round(adr, 1),
        "StopLoc": risk_label,
        "Trim": f"{days} Days" if action != "HOLDING" else "Holding",
        "Reason": "Solid" if total_score > 70 else "Check Rules"
    }

# ==============================================================================
# 3. MAIN EXECUTION
# ==============================================================================
if __name__ == "__main__":
    print("### KK STRATEGY AUDIT (v1.1.0) ###")

    if not os.path.exists(TRADE_LOG_FILE):
        print("No trade log found.")
        sys.exit()

    df = pd.read_csv(TRADE_LOG_FILE)
    buys = df[(df['Action'] == 'BUY') & (df['Status'] == 'FILLED')]

    if buys.empty:
        print("No BUY trades found.")
        sys.exit()

    print(f"Auditing {len(buys)} trades... (This takes time per trade)\n")

    results = []
    for i, row in buys.iterrows():
        # Clean overwriting print to show progress
        print(f"   > Analyzing {row['Symbol']}...", end="\r")
        res = grade_trade(row, df)
        if res: results.append(res)
        time.sleep(0.2)

    if results:
        audit_df = pd.DataFrame(results)
        audit_df = audit_df.sort_values("Date", ascending=False)

        print("\n\n" + "="*70)
        print(audit_df.to_string(index=False))
        print("="*70)

        audit_df.to_csv(OUTPUT_FILE, index=False)
        print(f"\nSaved report to: {OUTPUT_FILE}")