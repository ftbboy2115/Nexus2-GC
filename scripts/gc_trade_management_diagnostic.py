"""
GC Trade Management Diagnostic
Compares WB's trade management against Ross Cameron's known behavior per test case.

Phase 1: Uses existing data only (no backend code changes).
  - Batch test results from POST /warrior/sim/run_batch_concurrent
  - Ross data from warrior_setups.yaml (including regex-extracted notes)

Usage:
  python scripts/gc_trade_management_diagnostic.py                 # Top 10 by P&L gap
  python scripts/gc_trade_management_diagnostic.py --top 5         # Top 5
  python scripts/gc_trade_management_diagnostic.py --case ross_npt_20260203
  python scripts/gc_trade_management_diagnostic.py --all           # All cases
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

# ── Paths ────────────────────────────────────────────────────────────────────
NEXUS_PATH = os.environ.get(
    "NEXUS_PATH",
    r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus",
)
SETUPS_YAML = os.path.join(NEXUS_PATH, "nexus2", "tests", "test_cases", "warrior_setups.yaml")
DIAG_DIR = os.path.join(NEXUS_PATH, "nexus2", "reports", "gc_diagnostics")
BASE_URL = "http://127.0.0.1:8000/warrior"


# ── Helpers ──────────────────────────────────────────────────────────────────
def safe_num(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def safe_str(val, default=""):
    return str(val) if val is not None else default


def fetch_json(url: str, method: str = "GET", body: dict | None = None, timeout: int = 600) -> dict:
    """Fetch JSON from Nexus API."""
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def load_setups_yaml() -> dict:
    """Load warrior_setups.yaml, return dict keyed by case_id."""
    import yaml
    with open(SETUPS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    setups = {}
    cases = data.get("test_cases", [])
    for item in cases:
        if isinstance(item, dict) and "id" in item:
            setups[item["id"]] = item
    return setups


def extract_hhmm(time_str: str) -> str:
    """Extract HH:MM from ISO datetime or HH:MM string."""
    if not time_str:
        return ""
    time_str = str(time_str).strip().lstrip("~").strip()
    if "T" in time_str:
        time_str = time_str.split("T")[1][:5]
    elif len(time_str) > 5 and time_str[4] == "-":
        # Looks like a date, not a time
        return time_str[:10]
    # Strip timezone suffix
    if "+" in time_str:
        time_str = time_str.split("+")[0][:5]
    return time_str[:5]


def parse_time_to_minutes(time_str: str) -> float | None:
    """Parse HH:MM, ~HH:MM, or ISO datetime to minutes since midnight."""
    hhmm = extract_hhmm(time_str)
    if not hhmm:
        return None
    try:
        parts = hhmm.split(":")
        h, m = int(parts[0]), int(parts[1])
        return h * 60 + m
    except (ValueError, IndexError):
        return None


# ── Ross Notes Extraction ────────────────────────────────────────────────────
def extract_ross_notes(notes: str) -> dict:
    """Extract structured data from Ross's freeform notes via regex."""
    if not notes:
        return {"confidence": "NONE", "ross_exit_type": None, "ross_partial": False,
                "ross_added": False, "ross_stop_price": None, "ross_exit_price": None}

    result = {
        "confidence": "HIGH",
        "ross_exit_type": None,
        "ross_partial": False,
        "ross_added": False,
        "ross_stop_price": None,
        "ross_exit_price": None,
        "raw_notes": notes[:200],
    }

    # Exit type detection
    exit_patterns = [
        (r"(?i)stopped out", "stopped_out"),
        (r"(?i)took .{0,20}profit", "took_profit"),
        (r"(?i)sold .{0,30}on pullback", "sold_pullback"),
        (r"(?i)sold .{0,30}on red candle", "sold_red_candle"),
        (r"(?i)bailed", "bailed"),
        (r"(?i)cut", "cut_loss"),
        (r"(?i)quick out", "quick_exit"),
        (r"(?i)got right back out", "quick_exit"),
        (r"(?i)exited", "exited"),
        (r"(?i)sold", "sold"),
    ]
    for pattern, exit_type in exit_patterns:
        if re.search(pattern, notes):
            result["ross_exit_type"] = exit_type
            break

    # Partial detection
    if re.search(r"(?i)took partial|took .{0,10}profit on partial|sold half", notes):
        result["ross_partial"] = True

    # Add detection
    if re.search(r"(?i)added|add", notes):
        result["ross_added"] = True

    # Stop price extraction
    stop_match = re.search(r"(?i)stopped out[^$]*[\$~]?([\d]+\.?\d*)", notes)
    if stop_match:
        try:
            result["ross_stop_price"] = float(stop_match.group(1))
        except ValueError:
            pass

    # Exit price extraction
    exit_match = re.search(r"(?i)(?:sold|exited|exit)[^$]*[\$~]?([\d]+\.?\d*)", notes)
    if exit_match:
        try:
            result["ross_exit_price"] = float(exit_match.group(1))
        except ValueError:
            pass

    # Confidence scoring
    extracted_count = sum([
        result["ross_exit_type"] is not None,
        result["ross_partial"],
        result["ross_added"],
        result["ross_stop_price"] is not None,
        result["ross_exit_price"] is not None,
    ])
    if extracted_count == 0:
        result["confidence"] = "LOW"
    elif extracted_count <= 2:
        result["confidence"] = "MEDIUM"

    return result


# ── Diagnosis Category ───────────────────────────────────────────────────────
def diagnose_trade(wb: dict, ross: dict, ross_notes: dict) -> list[str]:
    """Classify the WB vs Ross divergence for a single case."""
    diagnoses = []
    wb_pnl = safe_num(wb.get("total_pnl"))
    ross_pnl = safe_num(ross.get("ross_pnl"))
    trades = wb.get("trades", [])

    # NO_ENTRY
    if not trades and ross_pnl > 0:
        # Check guard blocks
        if wb.get("guard_block_count", 0) > 0:
            diagnoses.append("GUARD_BLOCKED")
        else:
            diagnoses.append("NO_ENTRY")
        return diagnoses

    if not trades:
        diagnoses.append("NO_ENTRY")
        return diagnoses

    trade = trades[0]
    wb_exit = safe_str(trade.get("exit_reason", ""))

    # BETTER_MANAGEMENT
    if wb_pnl > ross_pnl and ross_pnl > 0:
        diagnoses.append("BETTER_MANAGEMENT")

    # WORSE_MANAGEMENT
    if wb_pnl < ross_pnl:
        diagnoses.append("WORSE_MANAGEMENT")

    # WRONG_STOP — WB stopped out but Ross didn't
    if "stop" in wb_exit.lower() and ross_notes.get("ross_exit_type") not in ("stopped_out",):
        ross_ep = ross_notes.get("ross_exit_type")
        if ross_ep and ross_ep != "stopped_out":
            diagnoses.append("WRONG_STOP")

    # EARLY_EXIT — WB exited but left significant MFE on table
    # (Approximate: if WB P&L < 30% of Ross P&L on a winner)
    if ross_pnl > 0 and wb_pnl > 0 and wb_pnl < ross_pnl * 0.3:
        diagnoses.append("EARLY_EXIT")

    # MISSED_PARTIAL — Ross took partial, WB didn't (or vice versa)
    wb_partial = trade.get("partial_taken", False)
    ross_partial = ross_notes.get("ross_partial", False)
    if ross_partial and not wb_partial:
        diagnoses.append("MISSED_PARTIAL")
    elif wb_partial and not ross_partial and wb_pnl < ross_pnl:
        diagnoses.append("UNNECESSARY_PARTIAL")

    # STOP_TOO_WIDE — WB loss is deeper than Ross loss
    if ross_pnl < 0 and wb_pnl < ross_pnl:
        diagnoses.append("STOP_TOO_WIDE")

    # STOP_TOO_TIGHT — WB stopped out, Ross survived to profit
    if wb_pnl < 0 and ross_pnl > 0 and "stop" in wb_exit.lower():
        diagnoses.append("STOP_TOO_TIGHT")

    if not diagnoses:
        if abs(wb_pnl - ross_pnl) < 500:
            diagnoses.append("MATCHED")
        else:
            diagnoses.append("REVIEW")

    return diagnoses


# ── Per-Case Report ──────────────────────────────────────────────────────────
def format_case_report(wb: dict, ross_case: dict, ross_notes: dict) -> str:
    """Format a per-case diagnostic report in markdown."""
    case_id = wb.get("case_id", "unknown")
    symbol = wb.get("symbol", "???")
    date = wb.get("date", "")
    wb_pnl = safe_num(wb.get("total_pnl"))
    ross_pnl = safe_num(ross_case.get("ross_pnl"))
    delta = round(wb_pnl - ross_pnl, 2)
    trades = wb.get("trades", [])
    diagnoses = diagnose_trade(wb, ross_case, ross_notes)

    lines = []
    lines.append(f"\n{'='*72}")
    lines.append(f"## {case_id}  ({symbol} {date})")
    lines.append(f"{'='*72}")

    # P&L Summary
    lines.append(f"  WB P&L: ${wb_pnl:>+10,.2f}   Ross P&L: ${ross_pnl:>+10,.2f}   Δ: ${delta:>+10,.2f}")
    lines.append(f"  Diagnosis: {', '.join(diagnoses)}")
    lines.append("")

    # Section B: Entry Comparison
    expected = ross_case.get("expected", {}) or {}
    ross_entry = safe_num(expected.get("entry_near")) if expected.get("entry_near") else None
    ross_entry_time = ross_case.get("ross_entry_time")
    trade = trades[0] if trades else {}
    wb_entry = safe_num(trade.get("entry_price")) if trade else None
    wb_entry_time = safe_str(trade.get("entry_time"))

    lines.append("  ### Entry Comparison")
    lines.append(f"  {'Metric':<20} {'Ross':>12} {'WB':>12} {'Delta':>12}")
    lines.append(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*12}")

    ross_entry_str = f"${ross_entry:.2f}" if ross_entry else "N/A"
    wb_entry_str = f"${wb_entry:.2f}" if wb_entry else "no entry"
    if ross_entry and wb_entry:
        entry_delta = f"${wb_entry - ross_entry:+.2f}"
    else:
        entry_delta = "N/A"
    lines.append(f"  {'Entry Price':<20} {ross_entry_str:>12} {wb_entry_str:>12} {entry_delta:>12}")

    ross_time_str = ross_entry_time or "N/A"
    wb_time_display = ""
    time_delta_str = "N/A"
    if wb_entry_time:
        wb_time_parsed = parse_time_to_minutes(wb_entry_time)
        ross_time_parsed = parse_time_to_minutes(ross_time_str)
        wb_time_display = extract_hhmm(wb_entry_time)
        if wb_time_parsed and ross_time_parsed:
            diff_min = wb_time_parsed - ross_time_parsed
            if abs(diff_min) < 5:
                time_delta_str = f"{diff_min:+.0f}m ✓"
            else:
                time_delta_str = f"{diff_min:+.0f}m"
    else:
        wb_time_display = "no entry"
    lines.append(f"  {'Entry Time':<20} {ross_time_str:>12} {wb_time_display:>12} {time_delta_str:>12}")

    trigger = safe_str(trade.get("entry_trigger")) if trade else "none"
    lines.append(f"  {'Entry Trigger':<20} {'manual':>12} {trigger:>12}")
    lines.append("")

    # Section C: Trade Management Comparison
    if trades:
        ross_stop = safe_num(expected.get("stop_near")) if expected.get("stop_near") else None
        wb_stop = None
        stop_str = safe_str(trade.get("stop_price"))
        if stop_str and stop_str != "None":
            try:
                wb_stop = float(stop_str)
            except (ValueError, TypeError):
                pass

        lines.append("  ### Trade Management Comparison")
        lines.append(f"  {'Metric':<20} {'Ross (notes)':>15} {'WB':>15} {'Diagnosis':>15}")
        lines.append(f"  {'-'*20} {'-'*15} {'-'*15} {'-'*15}")

        # Initial stop
        ross_stop_str = f"${ross_stop:.2f}" if ross_stop else "unknown"
        wb_stop_str = f"${wb_stop:.2f}" if wb_stop else "unknown"
        stop_diag = ""
        if ross_stop and wb_stop:
            if wb_stop < ross_stop * 0.95:
                stop_diag = "wider"
            elif wb_stop > ross_stop * 1.05:
                stop_diag = "tighter"
            else:
                stop_diag = "matched ✓"
        lines.append(f"  {'Initial Stop':<20} {ross_stop_str:>15} {wb_stop_str:>15} {stop_diag:>15}")

        # Stop method
        wb_stop_method = safe_str(trade.get("stop_method", ""))
        lines.append(f"  {'Stop Method':<20} {'unknown':>15} {wb_stop_method:>15}")

        # Exit mode
        wb_exit_mode = safe_str(trade.get("exit_mode", ""))
        lines.append(f"  {'Exit Mode':<20} {'unknown':>15} {wb_exit_mode:>15}")

        # Partial taken
        ross_partial_str = "YES" if ross_notes.get("ross_partial") else "no"
        wb_partial_str = "YES" if trade.get("partial_taken") else "no"
        partial_diag = "matched ✓" if ross_notes.get("ross_partial") == trade.get("partial_taken") else "MISMATCH"
        lines.append(f"  {'Partial Taken':<20} {ross_partial_str:>15} {wb_partial_str:>15} {partial_diag:>15}")

        # Exit reason
        wb_exit_reason = safe_str(trade.get("exit_reason", ""))
        ross_exit_type = safe_str(ross_notes.get("ross_exit_type", "unknown"))
        lines.append(f"  {'Exit Reason':<20} {ross_exit_type:>15} {wb_exit_reason:>15}")

        # Exit price
        wb_exit_price = safe_num(trade.get("exit_price"))
        wb_avg_exit = safe_num(trade.get("avg_exit_price"))
        exit_price_display = f"${wb_avg_exit:.2f}" if wb_avg_exit else f"${wb_exit_price:.2f}"
        ross_exit_price = ross_notes.get("ross_exit_price")
        ross_exit_str = f"${ross_exit_price:.2f}" if ross_exit_price else "unknown"
        lines.append(f"  {'Exit Price':<20} {ross_exit_str:>15} {exit_price_display:>15}")

        # Exit time
        wb_exit_time = safe_str(trade.get("exit_time", ""))
        wb_exit_display = extract_hhmm(wb_exit_time)
        lines.append(f"  {'Exit Time':<20} {'unknown':>15} {wb_exit_display:>15}")

        # P&L
        trade_pnl = safe_num(trade.get("pnl"))
        lines.append(f"  {'Trade P&L':<20} {'${:>+,.2f}'.format(ross_pnl):>15} {'${:>+,.2f}'.format(trade_pnl):>15} {'${:>+,.2f}'.format(trade_pnl - ross_pnl):>15}")
        lines.append("")

        # Additional trades
        if len(trades) > 1:
            lines.append(f"  ### Additional WB Trades ({len(trades) - 1} more)")
            for i, t in enumerate(trades[1:], 2):
                t_pnl = safe_num(t.get("pnl"))
                t_entry = safe_num(t.get("entry_price"))
                t_exit = safe_num(t.get("exit_price"))
                t_reason = safe_str(t.get("exit_reason", ""))
                lines.append(f"    Trade {i}: entry=${t_entry:.2f} exit=${t_exit:.2f} P&L=${t_pnl:+,.2f} ({t_reason})")
            lines.append("")

    # Ross added?
    if ross_notes.get("ross_added"):
        lines.append(f"  **Ross Added**: Yes (bot {'did' if len(trades) > 1 else 'did NOT'} scale in)")

    # Guard blocks (deduplicated)
    guard_count = wb.get("guard_block_count", 0)
    if guard_count > 0:
        lines.append(f"  **Guard Blocks**: {guard_count}")
        # Deduplicate: group by guard type + truncated reason
        from collections import Counter
        block_counter = Counter()
        for gb in wb.get("guard_blocks", []):
            key = f"{gb.get('guard', '?')}: {gb.get('reason', '')[:60]}"
            block_counter[key] += 1
        # Show unique blocks with counts, capped at 15
        for block_msg, count in block_counter.most_common(15):
            suffix = f" (×{count})" if count > 1 else ""
            lines.append(f"    - {block_msg}{suffix}")
        remaining_types = len(block_counter) - 15
        if remaining_types > 0:
            lines.append(f"    ... and {remaining_types} more unique block types")

    # Notes confidence
    conf = ross_notes.get("confidence", "LOW")
    if conf != "HIGH":
        lines.append(f"  ⚠ Ross notes extraction confidence: {conf}")

    lines.append("")
    return "\n".join(lines)


# ── Summary Statistics ───────────────────────────────────────────────────────
def compute_summary(diagnostics: list[dict]) -> dict:
    """Compute aggregate statistics across all analyzed cases."""
    total = len(diagnostics)
    if total == 0:
        return {}

    both_entered = [d for d in diagnostics if d.get("wb_trades")]
    no_entry = [d for d in diagnostics if not d.get("wb_trades")]

    better = [d for d in both_entered if d["wb_pnl"] > d["ross_pnl"]]
    worse = [d for d in both_entered if d["wb_pnl"] < d["ross_pnl"]]
    matched = [d for d in both_entered if d["wb_pnl"] == d["ross_pnl"]]

    better_sum = sum(d["wb_pnl"] - d["ross_pnl"] for d in better)
    worse_sum = sum(d["wb_pnl"] - d["ross_pnl"] for d in worse)

    # Stop analysis
    stop_too_tight = [d for d in diagnostics if "STOP_TOO_TIGHT" in d.get("diagnoses", [])]
    stop_too_wide = [d for d in diagnostics if "STOP_TOO_WIDE" in d.get("diagnoses", [])]
    wrong_stop = [d for d in diagnostics if "WRONG_STOP" in d.get("diagnoses", [])]
    guard_blocked = [d for d in diagnostics if "GUARD_BLOCKED" in d.get("diagnoses", [])]
    early_exit = [d for d in diagnostics if "EARLY_EXIT" in d.get("diagnoses", [])]
    missed_partial = [d for d in diagnostics if "MISSED_PARTIAL" in d.get("diagnoses", [])]

    return {
        "cases_analyzed": total,
        "both_entered": len(both_entered),
        "no_entry": len(no_entry),
        "better_than_ross": {"count": len(better), "delta": round(better_sum, 2)},
        "worse_than_ross": {"count": len(worse), "delta": round(worse_sum, 2)},
        "matched": len(matched),
        "stop_too_tight": len(stop_too_tight),
        "stop_too_wide": len(stop_too_wide),
        "wrong_stop": len(wrong_stop),
        "guard_blocked": len(guard_blocked),
        "early_exit": len(early_exit),
        "missed_partial": len(missed_partial),
        "total_wb_pnl": round(sum(d["wb_pnl"] for d in diagnostics), 2),
        "total_ross_pnl": round(sum(d["ross_pnl"] for d in diagnostics), 2),
    }


def format_summary(summary: dict) -> str:
    """Format summary statistics as text."""
    lines = []
    lines.append("\n" + "=" * 72)
    lines.append("## TRADE MANAGEMENT DIAGNOSTIC SUMMARY")
    lines.append("=" * 72)

    total_wb = summary.get("total_wb_pnl", 0)
    total_ross = summary.get("total_ross_pnl", 0)
    delta = round(total_wb - total_ross, 2)

    lines.append(f"  Cases analyzed:          {summary.get('cases_analyzed', 0)}")
    lines.append(f"  Both entered:            {summary.get('both_entered', 0)}")
    lines.append(f"  WB no entry:             {summary.get('no_entry', 0)}")
    lines.append("")
    lines.append(f"  TOTAL P&L:")
    lines.append(f"    WB:    ${total_wb:>+12,.2f}")
    lines.append(f"    Ross:  ${total_ross:>+12,.2f}")
    lines.append(f"    Delta: ${delta:>+12,.2f}")
    lines.append("")
    lines.append(f"  MANAGEMENT QUALITY:")
    better = summary.get("better_than_ross", {})
    worse = summary.get("worse_than_ross", {})
    lines.append(f"    Better than Ross:  {better.get('count', 0)} cases  (${better.get('delta', 0):>+,.2f})")
    lines.append(f"    Worse than Ross:   {worse.get('count', 0)} cases  (${worse.get('delta', 0):>+,.2f})")
    lines.append(f"    Matched:           {summary.get('matched', 0)} cases")
    lines.append("")
    lines.append(f"  DIAGNOSIS BREAKDOWN:")
    lines.append(f"    Stop too tight:    {summary.get('stop_too_tight', 0)} (WB stopped, Ross survived)")
    lines.append(f"    Stop too wide:     {summary.get('stop_too_wide', 0)} (WB loss > Ross loss)")
    lines.append(f"    Wrong stop:        {summary.get('wrong_stop', 0)} (WB stopped, Ross exited differently)")
    lines.append(f"    Guard blocked:     {summary.get('guard_blocked', 0)} (entry blocked by guard)")
    lines.append(f"    Early exit:        {summary.get('early_exit', 0)} (WB captured <30% of Ross P&L)")
    lines.append(f"    Missed partial:    {summary.get('missed_partial', 0)} (Ross took partial, WB didn't)")
    lines.append("")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Trade Management Diagnostic: WB vs Ross")
    parser.add_argument("--case", type=str, help="Analyze a single case ID")
    parser.add_argument("--all", action="store_true", help="Analyze all cases")
    parser.add_argument("--top", type=int, default=10, help="Analyze top N cases by P&L gap (default: 10)")
    parser.add_argument("--no-run", action="store_true", help="Skip batch test, load from saved JSON")
    args = parser.parse_args()

    # Load Ross data
    print("[Diagnostic] Loading warrior_setups.yaml...")
    setups = load_setups_yaml()
    print(f"[Diagnostic] Loaded {len(setups)} test cases from YAML")

    # Filter to POLYGON_DATA cases with ross_pnl
    polygon_cases = {k: v for k, v in setups.items()
                     if v.get("status") == "POLYGON_DATA" and v.get("ross_pnl") is not None}
    print(f"[Diagnostic] {len(polygon_cases)} POLYGON_DATA cases with ross_pnl")

    # Determine which cases to run
    if args.case:
        case_ids = [args.case]
    elif args.all:
        case_ids = list(polygon_cases.keys())
    else:
        case_ids = None  # Will run all, then sort

    # Run batch test or load from saved JSON
    saved_json = os.path.join(DIAG_DIR, "trade_management_diagnostic.json")

    if args.no_run and os.path.exists(saved_json):
        print(f"[Diagnostic] Loading saved results from {saved_json}...")
        with open(saved_json, "r") as f:
            saved = json.load(f)
        batch_results = saved.get("batch_results", [])
    else:
        print("[Diagnostic] Running batch test (include_trades=True)...")
        t0 = time.time()
        body = {"include_trades": True}
        if case_ids:
            body["case_ids"] = case_ids
        try:
            response = fetch_json(f"{BASE_URL}/sim/run_batch_concurrent", method="POST", body=body)
        except Exception as e:
            print(f"[Diagnostic] ERROR: Batch test failed: {e}")
            print("[Diagnostic] Is the server running? (uvicorn on port 8000)")
            sys.exit(1)

        batch_results = response.get("results", [])
        elapsed = round(time.time() - t0, 1)
        total_pnl = response.get("summary", {}).get("total_pnl", 0)
        print(f"[Diagnostic] Batch complete: {len(batch_results)} cases in {elapsed}s, total P&L=${total_pnl:+,.2f}")

    # Build case lookup
    batch_by_id = {r.get("case_id"): r for r in batch_results}

    # Build diagnostics
    diagnostics = []
    for case_id, ross_case in polygon_cases.items():
        wb = batch_by_id.get(case_id)
        if not wb:
            continue

        ross_notes = extract_ross_notes(safe_str(ross_case.get("notes")))
        diagnoses_list = diagnose_trade(wb, ross_case, ross_notes)

        wb_pnl = safe_num(wb.get("total_pnl"))
        ross_pnl = safe_num(ross_case.get("ross_pnl"))

        diagnostics.append({
            "case_id": case_id,
            "symbol": wb.get("symbol"),
            "date": wb.get("date"),
            "wb_pnl": wb_pnl,
            "ross_pnl": ross_pnl,
            "delta": round(wb_pnl - ross_pnl, 2),
            "abs_delta": round(abs(wb_pnl - ross_pnl), 2),
            "wb_trades": wb.get("trades", []),
            "diagnoses": diagnoses_list,
            "ross_notes": ross_notes,
            "guard_block_count": wb.get("guard_block_count", 0),
        })

    # Sort by absolute P&L gap
    diagnostics.sort(key=lambda d: d["abs_delta"], reverse=True)

    # Determine slice
    if not args.all and not args.case:
        diagnostics = diagnostics[:args.top]

    if not diagnostics:
        print("[Diagnostic] No cases to analyze.")
        sys.exit(0)

    # Print per-case reports
    for diag in diagnostics:
        case_id = diag["case_id"]
        wb = batch_by_id.get(case_id, {})
        ross_case = polygon_cases.get(case_id, {})
        ross_notes = diag["ross_notes"]
        report = format_case_report(wb, ross_case, ross_notes)
        print(report)

    # Print summary
    # Use ALL diagnostics for summary if not --case mode
    if not args.case:
        all_diag = []
        for case_id, ross_case in polygon_cases.items():
            wb = batch_by_id.get(case_id)
            if not wb:
                continue
            ross_notes = extract_ross_notes(safe_str(ross_case.get("notes")))
            diagnoses_list = diagnose_trade(wb, ross_case, ross_notes)
            wb_pnl = safe_num(wb.get("total_pnl"))
            ross_pnl_val = safe_num(ross_case.get("ross_pnl"))
            all_diag.append({
                "wb_pnl": wb_pnl,
                "ross_pnl": ross_pnl_val,
                "wb_trades": wb.get("trades", []),
                "diagnoses": diagnoses_list,
            })
        summary = compute_summary(all_diag)
        print(format_summary(summary))

    # Save detailed JSON
    os.makedirs(DIAG_DIR, exist_ok=True)
    output = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cases_analyzed": len(diagnostics),
        "diagnostics": diagnostics,
        "summary": compute_summary(diagnostics) if not args.case else None,
        "batch_results": batch_results,
    }

    with open(saved_json, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[Diagnostic] Detailed JSON saved to: {saved_json}")


if __name__ == "__main__":
    main()
