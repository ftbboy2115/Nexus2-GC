"""
Research: What was the HOD at Ross's entry time for the top 5 gap cases?

Determines whether Ross was buying HOD breaks (bot SHOULD catch)
or entering below the current HOD (bot CAN'T catch with current triggers).
"""
import json
from pathlib import Path

cases = [
    {"symbol": "NPT", "file": "intraday/ross_npt_20260203.json", "ross_entry_time": "07:50", "ross_entry_price": 10.00, "ross_pnl": 81000, "gap": -63461},
    {"symbol": "HIND", "file": "intraday/ross_hind_20260127.json", "ross_entry_time": "08:00", "ross_entry_price": 5.00, "ross_pnl": 55252, "gap": -55252},
    {"symbol": "PAVM", "file": "intraday/ross_pavm_20260121.json", "ross_entry_time": "unknown", "ross_entry_price": 12.31, "ross_pnl": 43950, "gap": -43844},
    {"symbol": "MLEC", "file": "intraday/ross_mlec_20260213.json", "ross_entry_time": "08:11", "ross_entry_price": 7.90, "ross_pnl": 43000, "gap": -42710},
    {"symbol": "LRHC", "file": "intraday/ross_lrhc_20260130.json", "ross_entry_time": "09:30", "ross_entry_price": 5.30, "ross_pnl": 31076, "gap": -30207},
]

base = Path("nexus2/tests/test_cases")

def time_to_minutes(t_str):
    """Convert HH:MM to minutes since midnight for comparison."""
    parts = t_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])

for case in cases:
    filepath = base / case["file"]
    if not filepath.exists():
        print(f"\n  {case['symbol']}: FILE NOT FOUND — {filepath}")
        continue
    
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    
    # Get the trade date
    trade_date = data.get("date", "?")
    pmh = data.get("premarket", {}).get("pmh", 0)
    
    # Get bars — separate prev_day continuity bars from trade-day bars
    all_bars = []
    for key in ["continuity_bars", "bars"]:
        if key in data and isinstance(data[key], list):
            for bar in data[key]:
                if isinstance(bar, dict):
                    bar["_source"] = key
                    all_bars.append(bar)
    
    # Filter to trade-day bars only (not prev_day)
    trade_day_bars = [b for b in all_bars if not b.get("prev_day", False) and b.get("d", "") == trade_date]
    prev_day_bars = [b for b in all_bars if b.get("prev_day", False) or b.get("d", "") != trade_date]
    
    print(f"\n{'='*90}")
    print(f"  {case['symbol']} — Ross entry ~{case['ross_entry_time']} ET at ${case['ross_entry_price']}")
    print(f"  Ross P&L: ${case['ross_pnl']:+,} | Gap vs Bot: ${case['gap']:+,}")
    print(f"  Trade date: {trade_date} | PMH from data: ${pmh}")
    print(f"  Total bars: {len(all_bars)} (trade day: {len(trade_day_bars)}, prev day: {len(prev_day_bars)})")
    print(f"{'='*90}")
    
    if not trade_day_bars:
        print(f"  NO TRADE-DAY BARS FOUND! Checking all bars...")
        trade_day_bars = all_bars  # Fall back to all bars
    
    # Track running HOD through trade-day bars
    running_high = 0.0
    entry_price = case["ross_entry_price"]
    entry_bar_found = False
    
    # Print first 10 bars of trade day
    print(f"\n  First 10 trade-day bars:")
    for i, bar in enumerate(trade_day_bars[:10]):
        t = bar.get("t", "?")
        o, h, l, c = bar.get("o", 0), bar.get("h", 0), bar.get("l", 0), bar.get("c", 0)
        v = bar.get("v", 0)
        
        if h > running_high:
            running_high = h
        
        marker = ""
        if not entry_bar_found and h >= entry_price:
            entry_bar_found = True
            marker = f"  <<< ENTRY HIT! HOD={running_high:.2f}"
        
        print(f"    {t:>5} | O={o:>7.2f} H={h:>7.2f} L={l:>7.2f} C={c:>7.2f} V={v:>8,} | HOD={running_high:.2f}{marker}")
    
    # If entry wasn't in first 10, continue scanning
    if not entry_bar_found:
        for i, bar in enumerate(trade_day_bars[10:], 10):
            h = bar.get("h", 0)
            if h > running_high:
                running_high = h
            if h >= entry_price:
                t = bar.get("t", "?")
                o, l, c = bar.get("o", 0), bar.get("l", 0), bar.get("c", 0)
                v = bar.get("v", 0)
                entry_bar_found = True
                print(f"\n    ... (skipped bars {10}-{i-1}) ...")
                print(f"    {t:>5} | O={o:>7.2f} H={h:>7.2f} L={l:>7.2f} C={c:>7.2f} V={v:>8,} | HOD={running_high:.2f}  <<< ENTRY HIT!")
                break
    
    # Continue to find overall HOD
    overall_high = max(b.get("h", 0) for b in trade_day_bars) if trade_day_bars else 0
    overall_low = min(b.get("l", 999) for b in trade_day_bars) if trade_day_bars else 0
    
    # Verdict
    print(f"\n  ANALYSIS:")
    print(f"    PMH (from data):       ${pmh:.2f}")
    print(f"    Ross entry price:      ${entry_price:.2f}")
    print(f"    HOD at entry time:     ${running_high:.2f}")
    print(f"    Full-day high:         ${overall_high:.2f}")
    print(f"    Full-day low:          ${overall_low:.2f}")
    
    if entry_bar_found:
        if entry_price >= running_high * 0.99:
            print(f"    >>> VERDICT: HOD BREAK — Ross bought AT/NEAR the HOD (${entry_price:.2f} vs HOD ${running_high:.2f})")
        else:
            pct_below = (running_high - entry_price) / running_high * 100
            print(f"    >>> VERDICT: BELOW HOD by {pct_below:.1f}% — entry ${entry_price:.2f} vs HOD ${running_high:.2f}")
        
        if entry_price < pmh:
            pct_below_pmh = (pmh - entry_price) / pmh * 100
            print(f"    >>> ALSO: {pct_below_pmh:.1f}% below final PMH (${pmh:.2f})")
        else:
            print(f"    >>> ALSO: AT or ABOVE PMH (${pmh:.2f})")
    else:
        print(f"    >>> Entry price ${entry_price:.2f} NEVER reached in data (range ${overall_low:.2f}-${overall_high:.2f})")

print(f"\n{'='*90}")
print(f"  RESEARCH COMPLETE")
print(f"{'='*90}")
