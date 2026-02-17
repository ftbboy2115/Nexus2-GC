"""
Bot vs Ross Ground Truth Comparison

Extracts Ross's actual P&L per case from warrior_setups.yaml,
pulls bot P&L from the latest batch results JSON, and builds
a side-by-side comparison to identify WHERE the gap lives.
"""
import yaml
import json
from pathlib import Path

# Load test cases
with open("nexus2/tests/test_cases/warrior_setups.yaml", encoding="utf-8") as f:
    data = yaml.safe_load(f)

# Load latest batch results
batch_file = Path("nexus2/scripts/_gate_on_results.json")
bot_results = {}
if batch_file.exists():
    with open(batch_file) as f:
        results = json.load(f)
    for r in results:
        bot_results[r["case_id"]] = r

# Build comparison
cases = data["test_cases"]
rows = []
for case in cases:
    case_id = case["id"]
    ross_pnl = case.get("ross_pnl") or case.get("target_pnl") or 0
    ross_traded = case.get("ross_traded", False)
    status = case.get("status", "")
    symbol = case["symbol"]
    notes = case.get("notes", "")
    entry_near = case.get("expected", {}).get("entry_near")
    
    bot = bot_results.get(case_id, {})
    bot_pnl = bot.get("total_pnl", 0)
    
    gap = bot_pnl - ross_pnl if ross_pnl else None
    
    rows.append({
        "case_id": case_id,
        "symbol": symbol,
        "ross_pnl": ross_pnl,
        "bot_pnl": bot_pnl,
        "gap": gap,
        "ross_traded": ross_traded,
        "status": status,
        "ross_entry": entry_near,
        "notes": notes[:80],
    })

# Sort by gap (worst first)
rows.sort(key=lambda r: r["gap"] if r["gap"] is not None else 0)

print("=" * 110)
print("  BOT vs ROSS — Per-Case P&L Comparison")
print("=" * 110)
print(f"  {'Case':<28} {'Symbol':<7} {'Ross P&L':>12} {'Bot P&L':>12} {'Gap':>12}  {'Notes'}")
print(f"  {'-'*28} {'-'*7} {'-'*12} {'-'*12} {'-'*12}  {'-'*40}")

total_ross = 0
total_bot = 0
total_gap = 0
matched_count = 0
ross_traded_cases = []

for r in rows:
    if r["gap"] is None:
        continue
    if r["status"] in ("BAD_DATA", "ESTIMATED", "NO_FMP_DATA", "SYNTHETIC"):
        continue
    
    matched_count += 1
    total_ross += r["ross_pnl"]
    total_bot += r["bot_pnl"]
    total_gap += r["gap"]
    
    flag = ""
    if r["ross_traded"]:
        ross_traded_cases.append(r)
    if not r["ross_traded"]:
        flag = " [Ross didn't trade]"
    
    gap_str = f"${r['gap']:>+11,.2f}" if r["gap"] is not None else f"{'n/a':>12}"
    print(f"  {r['case_id']:<28} {r['symbol']:<7} ${r['ross_pnl']:>+11,.2f} ${r['bot_pnl']:>+11,.2f} {gap_str}{flag}")

print(f"  {'-'*28} {'-'*7} {'-'*12} {'-'*12} {'-'*12}")
print(f"  {'TOTAL':<28} {'':7} ${total_ross:>+11,.2f} ${total_bot:>+11,.2f} ${total_gap:>+11,.2f}")
print(f"\n  Cases matched: {matched_count}")

# Breakdown
print(f"\n  {'='*80}")
print(f"  GAP BREAKDOWN (Ross-traded cases only)")
print(f"  {'='*80}")

ross_only = [r for r in rows if r["ross_traded"] and r["gap"] is not None 
             and r["status"] not in ("BAD_DATA", "ESTIMATED", "NO_FMP_DATA", "SYNTHETIC")]

# Where bot lost more than Ross
worse_cases = [r for r in ross_only if r["gap"] < -500]
better_cases = [r for r in ross_only if r["gap"] > 500]
similar_cases = [r for r in ross_only if abs(r["gap"] or 0) <= 500]

print(f"\n  BOT WORSE than Ross ({len(worse_cases)} cases, ${sum(r['gap'] for r in worse_cases):+,.2f}):")
for r in sorted(worse_cases, key=lambda x: x["gap"]):
    print(f"    {r['symbol']:6} gap=${r['gap']:>+11,.2f} | Ross=${r['ross_pnl']:>+10,.2f} Bot=${r['bot_pnl']:>+10,.2f}")

print(f"\n  BOT BETTER than Ross ({len(better_cases)} cases, ${sum(r['gap'] for r in better_cases):+,.2f}):")
for r in sorted(better_cases, key=lambda x: -x["gap"]):
    print(f"    {r['symbol']:6} gap=${r['gap']:>+11,.2f} | Ross=${r['ross_pnl']:>+10,.2f} Bot=${r['bot_pnl']:>+10,.2f}")

print(f"\n  SIMILAR (~${'-500 to +500'}) ({len(similar_cases)} cases):")
for r in similar_cases:
    print(f"    {r['symbol']:6} gap=${r['gap']:>+11,.2f} | Ross=${r['ross_pnl']:>+10,.2f} Bot=${r['bot_pnl']:>+10,.2f}")

# Top 5 biggest gaps
print(f"\n  {'='*80}")
print(f"  TOP 5 BIGGEST GAPS (where the money is)")
print(f"  {'='*80}")
for r in sorted(ross_only, key=lambda x: x["gap"])[:5]:
    print(f"    {r['symbol']:6} Ross=${r['ross_pnl']:>+10,.2f}  Bot=${r['bot_pnl']:>+10,.2f}  Gap=${r['gap']:>+11,.2f}")
    print(f"           Ross entry: ${r['ross_entry']}")
    print(f"           {r['notes']}")
    print()
