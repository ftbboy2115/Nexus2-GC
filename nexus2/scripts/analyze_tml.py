"""
TML Analysis: Parse warrior_trade.log to identify P&L leakage patterns.

Goal: Understand WHERE the $312K gap comes from (bot=$100K vs Ross=$412K)
- Is it from losses being too big?
- From wins being too small?
- From not entering enough trades?
"""
import re
from collections import defaultdict
from pathlib import Path

log_path = Path("data/warrior_trade.log")
lines = log_path.read_text().strip().split("\n")

# Only analyze the most recent batch run (last ~60 seconds of entries)
# Find the latest batch window by looking at timestamps
recent_lines = lines[-200:]  # Last 200 lines should cover one batch

# Parse events
entries = []   # (symbol, shares, price, trigger)
exits = []     # (symbol, price, pnl, reason)
partials = []  # (symbol, shares, price, pnl)
scales = []    # (symbol, shares, price)
blocks = []    # (symbol, guard, reason)

for line in recent_lines:
    parts = line.split(" | ")
    if len(parts) < 3:
        continue
    
    event_type = parts[1].strip()
    symbol = parts[2].strip()
    detail = " | ".join(parts[3:])  # Full detail string (all remaining parts)
    
    if event_type == "ENTRY":
        # Parse: "501 @ $21.68 | stop=$16.69 | trigger=dip_for_level"
        m = re.match(r"(\d+) @ \$?([\d.]+)", detail)
        trigger = ""
        m_trigger = re.search(r"trigger=(\S+)", detail)
        if m_trigger:
            trigger = m_trigger.group(1)
        stop_price = None
        m_stop = re.search(r"stop=\$?([\d.]+)", detail)
        if m_stop:
            stop_price = float(m_stop.group(1))
        if m:
            entries.append({"symbol": symbol, "shares": int(m.group(1)), 
                          "price": float(m.group(2)), "trigger": trigger,
                          "stop": stop_price})
    
    elif event_type in ("MENTAL_STOP_EXIT", "TECHNICAL_STOP_EXIT", "AFTER_HOURS_EXIT"):
        # Parse full line: "@ $18.15 | P&L=-$238.6986 | reason=mental_stop"
        m_price = re.search(r"@ \$?([\d.]+)", detail)
        m_pnl = re.search(r"P&L=([+-]?\$?[\d,.]+)", detail)
        reason = event_type.replace("_EXIT", "").lower()
        if m_price and m_pnl:
            pnl_str = m_pnl.group(1).replace("$", "").replace(",", "")
            exits.append({"symbol": symbol, "price": float(m_price.group(1)),
                        "pnl": float(pnl_str), "reason": reason})
    
    elif event_type == "PARTIAL_EXIT":
        m_pnl = re.search(r"P&L=([+-]?\$?[\d,.]+)", detail)
        if m_pnl:
            pnl_str = m_pnl.group(1).replace("$", "").replace(",", "")
            partials.append({"symbol": symbol, "pnl": float(pnl_str)})
    
    elif event_type == "SCALE_IN":
        m = re.search(r"\+(\d+) @ \$?([\d.]+)", detail)
        if m:
            scales.append({"symbol": symbol, "shares": int(m.group(1)), "price": float(m.group(2))})
    
    elif event_type == "GUARD_BLOCK":
        guard = ""
        m_guard = re.search(r"guard=(\w+)", detail)
        if m_guard:
            guard = m_guard.group(1)
        blocks.append({"symbol": symbol, "guard": guard, "detail": detail})


# Build per-symbol P&L
symbol_pnl = defaultdict(float)
for e in exits:
    symbol_pnl[e["symbol"]] += e["pnl"]
for p in partials:
    symbol_pnl[p["symbol"]] += p["pnl"]

# Analysis
print("=" * 80)
print("  TML P&L ANALYSIS — Latest Batch Run")
print("=" * 80)

# 1. Total P&L breakdown
total_pnl = sum(symbol_pnl.values())
winners = {s: p for s, p in symbol_pnl.items() if p > 0}
losers = {s: p for s, p in symbol_pnl.items() if p < 0}
print(f"\n  Total P&L: ${total_pnl:+,.2f}")
print(f"  Winners:   {len(winners)} cases, ${sum(winners.values()):+,.2f}")
print(f"  Losers:    {len(losers)} cases, ${sum(losers.values()):+,.2f}")

# 2. Exit reason breakdown
exit_by_reason = defaultdict(lambda: {"count": 0, "pnl": 0})
for e in exits:
    exit_by_reason[e["reason"]]["count"] += 1
    exit_by_reason[e["reason"]]["pnl"] += e["pnl"]

print(f"\n  Exit Reason Breakdown:")
print(f"  {'Reason':<25} {'Count':>6} {'Total P&L':>12}")
print(f"  {'-'*25} {'-'*6} {'-'*12}")
for reason, data in sorted(exit_by_reason.items(), key=lambda x: x[1]["pnl"]):
    print(f"  {reason:<25} {data['count']:>6} ${data['pnl']:>+11,.2f}")

# 3. Entry trigger breakdown
trigger_counts = defaultdict(int)
for e in entries:
    trigger_counts[e["trigger"]] += 1
print(f"\n  Entry Triggers:")
for trigger, count in sorted(trigger_counts.items(), key=lambda x: -x[1]):
    print(f"    {trigger}: {count}")

# 4. Guard blocks
guard_counts = defaultdict(int)
for b in blocks:
    guard_counts[b["guard"]] += 1
print(f"\n  Guard Blocks:")
for guard, count in sorted(guard_counts.items(), key=lambda x: -x[1]):
    print(f"    {guard}: {count}x")

# 5. Scaling analysis
if scales:
    scaled_symbols = set(s["symbol"] for s in scales)
    print(f"\n  Scaling:")
    for sym in scaled_symbols:
        scale_pnl = symbol_pnl.get(sym, 0)
        print(f"    {sym}: scaled, final P&L = ${scale_pnl:+,.2f}")

# 6. Top losers (entry → exit detail)
print(f"\n  Top 5 Losers (entry → exit):")
sorted_losers = sorted(losers.items(), key=lambda x: x[1])
for sym, pnl in sorted_losers[:5]:
    entry = next((e for e in entries if e["symbol"] == sym), None)
    exit_ = next((e for e in exits if e["symbol"] == sym), None)
    entry_str = f"${entry['price']:.2f} ({entry['trigger']})" if entry else "?"
    exit_str = f"${exit_['price']:.2f} ({exit_['reason']})" if exit_ else "?"
    stop_dist = ""
    if entry and exit_:
        dist_pct = abs(entry["price"] - exit_["price"]) / entry["price"] * 100
        stop_dist = f" [{dist_pct:.1f}% move]"
    print(f"    {sym}: ${pnl:+,.2f} | entry={entry_str} → exit={exit_str}{stop_dist}")

# 7. Top winners
print(f"\n  Top 5 Winners:")
sorted_winners = sorted(winners.items(), key=lambda x: -x[1])
for sym, pnl in sorted_winners[:5]:
    entry = next((e for e in entries if e["symbol"] == sym), None)
    exit_ = next((e for e in exits if e["symbol"] == sym), None)
    entry_str = f"${entry['price']:.2f} ({entry['trigger']})" if entry else "?"
    exit_str = f"${exit_['price']:.2f} ({exit_['reason']})" if exit_ else "?"
    print(f"    {sym}: ${pnl:+,.2f} | entry={entry_str} → exit={exit_str}")

print(f"\n{'='*80}")
