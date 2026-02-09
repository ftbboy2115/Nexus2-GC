#!/usr/bin/env python3
"""Diagnose VERO batch vs GUI discrepancy."""
import json
import sqlite3
import os
import glob

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
BARS_DIR = os.path.join(DATA_DIR, "historical_bars")

print("=" * 60)
print("VERO BATCH DISCREPANCY DIAGNOSTIC")
print("=" * 60)

# 1. Check for PENDING_EXIT in warrior_trades DB
print("\n--- CHECK 1: PENDING_EXIT records in warrior_trades.db ---")
db_path = os.path.join(DATA_DIR, "warrior_trades.db")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    # First discover tables
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]
    print(f"  Tables found: {table_names}")
    
    for tbl in table_names:
        # Check columns
        cols = conn.execute(f"PRAGMA table_info({tbl})").fetchall()
        col_names = [c[1] for c in cols]
        
        if 'status' in col_names and 'symbol' in col_names:
            print(f"  Checking table '{tbl}' for PENDING_EXIT...")
            cursor = conn.execute(
                f"SELECT * FROM {tbl} WHERE status LIKE '%PENDING%' OR status LIKE '%pending%'"
            )
            rows = cursor.fetchall()
            if rows:
                for r in rows:
                    print(f"    FOUND: {r}")
            else:
                print(f"    No PENDING_EXIT records (theory 1 DISPROVEN for {tbl})")
            
            # Also check VERO records
            cursor2 = conn.execute(f"SELECT * FROM {tbl} WHERE symbol='VERO'")
            vero_rows = cursor2.fetchall()
            print(f"    VERO records: {len(vero_rows)}")
            for r in vero_rows:
                print(f"      {r}")
    conn.close()
else:
    print(f"  DB not found at {db_path}")

# 2. Check for 10s bars
print("\n--- CHECK 2: Does VERO have 10s bars? ---")
if os.path.exists(BARS_DIR):
    vero_files = glob.glob(os.path.join(BARS_DIR, "*VERO*"))
    if vero_files:
        for f in vero_files:
            basename = os.path.basename(f)
            size = os.path.getsize(f)
            print(f"  {basename} ({size:,} bytes)")
            if "10s" in basename:
                print("    ^^^ 10S BARS FOUND - theory 2 CONFIRMED")
    else:
        print("  No VERO bar files found")
    
    # Also check test_cases dir
    test_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "test_cases", "intraday")
    if os.path.exists(test_dir):
        vero_test = glob.glob(os.path.join(test_dir, "*VERO*"))
        for f in vero_test:
            basename = os.path.basename(f)
            size = os.path.getsize(f)
            print(f"  (test_cases) {basename} ({size:,} bytes)")
            if "10s" in basename:
                print("    ^^^ 10S BARS FOUND - theory 2 CONFIRMED")
    if not any("10s" in os.path.basename(f) for f in glob.glob(os.path.join(BARS_DIR, "*VERO*")) + glob.glob(os.path.join(test_dir, "*VERO*") if os.path.exists(test_dir) else "")):
        print("  No 10s bars for VERO (theory 2 DISPROVEN)")
else:
    print(f"  Historical bars dir not found at {BARS_DIR}")

# 3. Analyze the last batch run's broker orders
print("\n--- CHECK 3: Broker sell orders in last VERO batch run ---")
debug_file = "/tmp/vero_debug.json"
if os.path.exists(debug_file):
    data = json.load(open(debug_file))
    result = data["results"][0]
    trades = result["trades"]
    
    sells_matched = [t for t in trades if t.get("exit_price") is not None]
    still_open = [t for t in trades if t.get("note") == "position_still_open"]
    
    print(f"  Total trade entries: {len(trades)}")
    print(f"  Matched (has exit): {len(sells_matched)}")
    print(f"  Still open: {len(still_open)}")
    print(f"  Realized P&L: ${result['realized_pnl']:.2f}")
    print(f"  Unrealized P&L: ${result['unrealized_pnl']:.2f}")
    print(f"  Total P&L: ${result['total_pnl']:.2f}")
    
    print("\n  Matched trades:")
    for t in sells_matched:
        print(f"    {t['entry_time']} BUY {t['shares']}x @ ${t['entry_price']:.2f} → "
              f"{t['exit_time']} SELL @ ${t['exit_price']:.2f} = ${t['pnl']:.2f} "
              f"({t.get('entry_trigger', '?')}/{t.get('exit_mode', '?')})")
    
    print("\n  Still open:")
    for t in still_open:
        print(f"    {t['entry_time']} BUY {t['shares']}x @ ${t['entry_price']:.2f} "
              f"({t.get('entry_trigger', '?')}/{t.get('exit_mode', '?')})")
    
    # Count total bought vs total sold
    total_bought = sum(t["shares"] for t in trades)
    total_sold_matched = sum(t["shares"] for t in sells_matched)
    total_still_open = sum(t["shares"] for t in still_open)
    print(f"\n  Total shares bought: {total_bought}")
    print(f"  Total shares sold (matched): {total_sold_matched}")
    print(f"  Total shares still open: {total_still_open}")
    print(f"  Unaccounted: {total_bought - total_sold_matched - total_still_open}")
else:
    print(f"  Debug file not found at {debug_file}")

# 4. Check the actual number of sell orders the broker created
print("\n--- CHECK 4: What the GUI should show (expected sells) ---")
print("  GUI consistently shows 6 sells:")
print("  1. 05:34 SELL 657x @ $3.70")
print("  2. 10:07 SELL 336x @ $7.51")
print("  3. 10:36 SELL 441x @ $7.73")
print("  4. 11:00 SELL 132x @ $10.14")
print("  5. 16:29 SELL 126x @ $6.86  ← MISSING IN BATCH")
print("  6. 19:57 SELL 846x @ $5.91")
print("  Total GUI sells: 2538 shares (all bought = all sold)")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
