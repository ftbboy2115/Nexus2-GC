"""
GC Top Gaps — Show the biggest P&L gaps between bot and Ross.

Reads from the latest baseline (or last_run.json) and displays cases
sorted by gap size, highlighting the biggest improvement opportunities.

Usage:
  python scripts/gc_top_gaps.py              # Top 10 gaps from baseline
  python scripts/gc_top_gaps.py --all        # All 35 cases
  python scripts/gc_top_gaps.py --top 5      # Top 5 gaps
  python scripts/gc_top_gaps.py --json       # JSON output (for GC)
  python scripts/gc_top_gaps.py --last       # Use last_run.json instead of baseline
"""
from __future__ import annotations

import io
import json
import os
import sys
import argparse

# Fix Windows encoding
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except (AttributeError, TypeError):
    pass

try:
    from gc_memory_bridge import write_known_issues_memory
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gc_memory_bridge import write_known_issues_memory

NEXUS_PATH = os.environ.get(
    "NEXUS_PATH",
    r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
)
BASELINE_FILE = os.path.join(NEXUS_PATH, "nexus2", "reports", "gc_diagnostics", "baseline.json")
LAST_RUN_FILE = os.path.join(NEXUS_PATH, "nexus2", "reports", "gc_diagnostics", "last_run.json")


def load_data(use_last: bool = False) -> dict:
    path = LAST_RUN_FILE if use_last else BASELINE_FILE
    if not os.path.exists(path):
        print(f"  ERROR: File not found: {path}")
        sys.exit(1)
    with open(path, "r") as f:
        return json.load(f)


def analyze_gaps(data: dict, top_n: int | None = None) -> list[dict]:
    cases = data.get("results", data.get("cases", []))
    gaps = []
    for c in cases:
        bot = c.get("total_pnl", c.get("bot_pnl", 0)) or 0
        ross = c.get("ross_pnl", 0) or 0
        gap = bot - ross
        guard_count = len(c.get("guard_blocks", []))
        gaps.append({
            "case_id": c["case_id"],
            "symbol": c.get("symbol", c["case_id"].split("_")[1].upper()),
            "bot_pnl": bot,
            "ross_pnl": ross,
            "gap": gap,
            "guard_blocks": guard_count,
        })

    # Sort by gap ascending (worst gaps first)
    gaps.sort(key=lambda x: x["gap"])

    if top_n:
        # Return only the worst gaps (negative = underperforming)
        return gaps[:top_n]
    return gaps


def print_gaps(gaps: list[dict], source_label: str, saved_at: str):
    total_bot = sum(g["bot_pnl"] for g in gaps)
    total_ross = sum(g["ross_pnl"] for g in gaps)
    total_gap = sum(g["gap"] for g in gaps)
    capture = (total_bot / total_ross * 100) if total_ross else 0

    # Count underperforming vs outperforming
    under = sum(1 for g in gaps if g["gap"] < -10)
    over = sum(1 for g in gaps if g["gap"] > 10)
    even = len(gaps) - under - over

    print(f"\n{'='*80}")
    print(f"  TOP P&L GAPS ({len(gaps)} cases) — Source: {source_label}")
    print(f"  Data from: {saved_at}")
    print(f"{'='*80}")
    print(f"  Bot Total:  ${total_bot:>12,.2f}")
    print(f"  Ross Total: ${total_ross:>12,.2f}")
    print(f"  Gap Total:  ${total_gap:>+12,.2f}")
    print(f"  Capture:    {capture:.1f}%")
    print(f"  Under: {under} | Over: {over} | Even: {even}")
    print(f"{'='*80}")
    print(f"  {'Case':<30s} | {'Bot':>10s} | {'Ross':>10s} | {'Gap':>10s} | {'Guards':>6s}")
    print(f"  {'-'*30}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*6}")

    for g in gaps:
        marker = "▼" if g["gap"] < -100 else ("▲" if g["gap"] > 100 else " ")
        guards = str(g["guard_blocks"]) if g["guard_blocks"] > 0 else "-"
        print(f"  {marker} {g['symbol']:<28s} | ${g['bot_pnl']:>9,.0f} | ${g['ross_pnl']:>9,.0f} | ${g['gap']:>+9,.0f} | {guards:>6s}")

    print()


def main():
    parser = argparse.ArgumentParser(description="GC Top Gaps — biggest P&L improvement opportunities")
    parser.add_argument("--top", type=int, default=10, help="Show top N gaps (default: 10)")
    parser.add_argument("--all", action="store_true", help="Show all cases")
    parser.add_argument("--last", action="store_true", help="Use last_run.json instead of baseline")
    parser.add_argument("--json", action="store_true", help="JSON output (for GC)")
    args = parser.parse_args()

    data = load_data(use_last=args.last)
    saved_at = data.get("saved_at", "unknown")
    source = "last_run" if args.last else "baseline"

    top_n = None if args.all else args.top
    gaps = analyze_gaps(data, top_n=top_n)

    if args.json:
        total_bot = sum(g["bot_pnl"] for g in gaps)
        total_ross = sum(g["ross_pnl"] for g in gaps)
        output = {
            "source": source,
            "saved_at": saved_at,
            "total_bot_pnl": total_bot,
            "total_ross_pnl": total_ross,
            "total_gap": total_bot - total_ross,
            "capture_pct": (total_bot / total_ross * 100) if total_ross else 0,
            "gaps": gaps,
        }
        print(json.dumps(output, indent=2))
    else:
        print_gaps(gaps, source, saved_at)

    # Auto-write known issues to GC memory (always, using ALL gaps)
    all_gaps = analyze_gaps(data, top_n=None)
    try:
        write_known_issues_memory(all_gaps)
    except Exception:
        pass  # Non-critical


if __name__ == "__main__":
    main()
