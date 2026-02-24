"""
GC Batch Diagnosis Script
Runs all test cases, categorizes issues, and produces a priority report.
Called by Gravity Claw via shell_exec — outputs only the summary.

Usage:
  python gc_batch_diagnose.py                  # Run all cases (batch mode)
  python gc_batch_diagnose.py ross_npt_20260203 # Deep diagnosis for specific case(s)
  python gc_batch_diagnose.py NPT MLEC PAVM     # Lookup by symbol name
"""
from __future__ import annotations

import io
import json
import os
import sys

# Fix Windows encoding — PowerShell default codec can't handle emojis
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except (AttributeError, TypeError):
    pass  # Already wrapped or no buffer available

import urllib.request
import yaml
from datetime import datetime
from collections import defaultdict

BASE_URL = "http://127.0.0.1:8000"
NEXUS_PATH = os.environ.get("NEXUS_PATH", r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus")
SETUPS_YAML = os.path.join(NEXUS_PATH, "nexus2", "tests", "test_cases", "warrior_setups.yaml")
DIAG_DIR = os.path.join(NEXUS_PATH, "nexus2", "reports", "gc_diagnostics")


# ── Null-safety helpers ──────────────────────────────────────────────
def safe_num(val, default=0):
    """Coerce None / non-numeric to a number."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_int(val, default=0):
    """Coerce None / non-int to int."""
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def safe_str(val, default=""):
    """Coerce None to empty string."""
    return str(val) if val is not None else default


def safe_list(val):
    """Coerce None to empty list."""
    return val if isinstance(val, list) else []


def safe_dict(val):
    """Coerce None to empty dict."""
    return val if isinstance(val, dict) else {}


# ── API helper ───────────────────────────────────────────────────────
def fetch_json(url: str, method: str = "GET", body: dict | None = None, timeout: int = 600) -> dict:
    """Fetch JSON from Nexus API."""
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ── Code path mapping (real files, not invented) ────────────────────
CODE_PATHS = {
    "LATE_ENTRY": {
        "file": "nexus2/domain/automation/warrior_entry_patterns.py",
        "function": "check_active_market()",
        "description": "Premarket active-market gate blocks early entries due to low bar count/volume",
    },
    "GUARD_BLOCKED": {
        "file": "nexus2/domain/automation/warrior_entry_guards.py",
        "function": "check_entry_guards()",
        "description": "Guard functions block re-entry attempts",
    },
    "STOP_HIT": {
        "file": "nexus2/domain/automation/warrior_monitor.py",
        "function": "_check_technical_stop()",
        "description": "Technical stop calculation and trigger logic",
    },
    "OVERSIZED": {
        "file": "nexus2/domain/automation/warrior_engine.py",
        "function": "_calculate_position_size()",
        "description": "Position sizing based on stop distance and risk",
    },
    "NO_RE_ENTRY": {
        "file": "nexus2/domain/automation/warrior_monitor.py",
        "function": "_check_reentry_opportunity()",
        "description": "Re-entry detection after stop-out",
    },
}


# ── Load warrior_setups.yaml ─────────────────────────────────────────
def load_setups_yaml() -> dict:
    """Load warrior_setups.yaml and return dict keyed by case_id."""
    try:
        with open(SETUPS_YAML, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        setups = {}
        for item in (data or []):
            if isinstance(item, dict) and "id" in item:
                setups[item["id"]] = item
        return setups
    except Exception:
        return {}


def parse_time_to_minutes(time_str: str) -> int | None:
    """Parse HH:MM or ~HH:MM or ISO datetime to minutes since midnight."""
    try:
        clean = time_str.replace("~", "").strip()
        if "T" in clean:
            clean = clean.split("T")[1]
        if "." in clean:
            clean = clean.split(".")[0]
        parts = clean.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return None


# ── Diagnosis logic ──────────────────────────────────────────────────
def diagnose_case(result: dict, test_case: dict | None) -> list[str]:
    """Apply auto-diagnosis categories to a single case result."""
    diagnoses = []
    trades = safe_list(result.get("trades"))
    guard_blocks = safe_int(result.get("guard_block_count"))
    guard_details = safe_dict(result.get("guard_block_details"))
    total_pnl = safe_num(result.get("total_pnl"))
    ross_pnl = safe_num(result.get("ross_pnl"))

    # LATE_ENTRY: Bot entry time > 30 min after Ross entry
    if test_case and trades:
        ross_entry = safe_str(test_case.get("ross_entry_time"))
        if ross_entry:
            ross_min = parse_time_to_minutes(ross_entry)
            bot_entry_str = safe_str(trades[0].get("entry_time") if isinstance(trades[0], dict) else "")
            bot_min = parse_time_to_minutes(bot_entry_str) if bot_entry_str else None
            if ross_min is not None and bot_min is not None:
                diff = bot_min - ross_min
                if diff > 30:
                    hours = diff // 60
                    mins = diff % 60
                    diagnoses.append(f"LATE_ENTRY: Bot entered {hours}h{mins}m after Ross")

    # NO_ENTRY: No trades at all
    if len(trades) == 0 and ross_pnl > 0:
        diagnoses.append("NO_ENTRY: Bot never entered — Ross made money")

    # NO_RE_ENTRY: Only 1 trade AND no guard blocks
    if len(trades) <= 1 and guard_blocks == 0 and total_pnl < 0:
        diagnoses.append("NO_RE_ENTRY: Bot never attempted re-entry after stop-out")

    # GUARD_BLOCKED: Guard blocks > 0 AND bot lost money
    if guard_blocks > 0 and total_pnl < ross_pnl:
        types = ", ".join(f"{k}:{v}" for k, v in guard_details.items()) if guard_details else f"{guard_blocks} blocks"
        diagnoses.append(f"GUARD_BLOCKED: Guards blocked {guard_blocks} re-entry attempts ({types})")

    # HELD_TO_CLOSE: exit_reason contains "after_hours"
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        exit_reason = safe_str(trade.get("exit_reason")).lower()
        if "after_hours" in exit_reason and safe_num(trade.get("pnl")) < 0:
            diagnoses.append("HELD_TO_CLOSE: Bot held losing position until close")
            break

    # OVERSIZED: shares * entry_price > 40000
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        shares = safe_num(trade.get("shares"))
        entry_price = safe_num(trade.get("entry_price"))
        if shares * entry_price > 40000:
            diagnoses.append(f"OVERSIZED: Position size ${shares * entry_price:,.0f}")
            break

    # STOP_HIT: exit_reason = "technical_stop"
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        exit_reason = safe_str(trade.get("exit_reason")).lower()
        if "technical_stop" in exit_reason or "stop" in exit_reason:
            diagnoses.append("STOP_HIT: Technical stop triggered")
            break

    if not diagnoses:
        if total_pnl >= ross_pnl * 0.8 and ross_pnl > 0:
            diagnoses.append("OK: Bot captured most of Ross P&L")
        elif total_pnl > 0:
            diagnoses.append("PARTIAL: Bot profitable but below Ross")
        elif ross_pnl <= 0:
            diagnoses.append("ROSS_LOSS: Ross also lost on this trade")
        else:
            diagnoses.append("UNKNOWN: Needs manual review")

    return diagnoses


# ── Deep per-case analysis ───────────────────────────────────────────
def deep_analyze_case(result: dict, test_case: dict | None, setup: dict | None) -> str:
    """Produce detailed analysis for a single case. Returns formatted text."""
    lines = []
    symbol = safe_str(result.get("symbol"), "???")
    case_id = safe_str(result.get("case_id"))
    bot_pnl = safe_num(result.get("total_pnl"))
    ross_pnl = safe_num(result.get("ross_pnl"))
    delta = bot_pnl - ross_pnl
    trades = safe_list(result.get("trades"))
    guard_blocks = safe_int(result.get("guard_block_count"))
    guard_details = safe_dict(result.get("guard_block_details"))
    diags = diagnose_case(result, test_case)
    primary = diags[0].split(":")[0] if diags else "UNKNOWN"

    lines.append(f"{'='*60}")
    lines.append(f"DEEP ANALYSIS: {symbol} ({case_id})")
    lines.append(f"{'='*60}")
    lines.append(f"")
    lines.append(f"P&L Summary:")
    lines.append(f"  Bot P&L:  ${bot_pnl:>12,.2f}")
    lines.append(f"  Ross P&L: ${ross_pnl:>12,.2f}")
    lines.append(f"  Gap:      ${delta:>12,.2f}")
    capture = (bot_pnl / ross_pnl * 100) if ross_pnl > 0 else 0
    lines.append(f"  Capture:  {capture:.1f}%")
    lines.append(f"")

    # ── Entry Timing Comparison ──
    lines.append(f"Entry Timing:")
    ross_entry_time = None
    ross_entry_price = None
    if setup:
        ross_entry_time = safe_str(setup.get("ross_entry_time"))
        ross_entry_price = setup.get("ross_entry_price")
    if test_case and not ross_entry_time:
        ross_entry_time = safe_str(test_case.get("ross_entry_time"))

    if trades:
        first_trade = trades[0] if isinstance(trades[0], dict) else {}
        bot_entry_time = safe_str(first_trade.get("entry_time"))
        bot_entry_price = safe_num(first_trade.get("entry_price"))

        lines.append(f"  Ross entry: {ross_entry_time or 'UNKNOWN'} @ ${ross_entry_price or '?'}")
        lines.append(f"  Bot entry:  {bot_entry_time or 'UNKNOWN'} @ ${bot_entry_price:.2f}")

        ross_min = parse_time_to_minutes(ross_entry_time) if ross_entry_time else None
        bot_min = parse_time_to_minutes(bot_entry_time) if bot_entry_time else None
        if ross_min and bot_min:
            diff = bot_min - ross_min
            if diff > 0:
                lines.append(f"  Delay:      {diff} minutes LATE")
            elif diff < 0:
                lines.append(f"  Delay:      {abs(diff)} minutes EARLY")
            else:
                lines.append(f"  Delay:      ON TIME")
        if ross_entry_price and bot_entry_price:
            price_diff = bot_entry_price - float(ross_entry_price)
            lines.append(f"  Price diff: ${price_diff:+.2f} ({'higher' if price_diff > 0 else 'lower'} than Ross)")
    else:
        lines.append(f"  Ross entry: {ross_entry_time or 'UNKNOWN'} @ ${ross_entry_price or '?'}")
        lines.append(f"  Bot entry:  NO ENTRY")
    lines.append(f"")

    # ── Trade Details ──
    lines.append(f"Trade Details ({len(trades)} trades):")
    total_trade_pnl = 0
    for i, trade in enumerate(trades):
        if not isinstance(trade, dict):
            continue
        t_entry = safe_str(trade.get("entry_time"))
        t_exit = safe_str(trade.get("exit_time"))
        t_entry_price = safe_num(trade.get("entry_price"))
        t_exit_price = safe_num(trade.get("exit_price"))
        t_shares = safe_int(trade.get("shares"))
        t_pnl = safe_num(trade.get("pnl"))
        t_exit_reason = safe_str(trade.get("exit_reason"))
        t_direction = safe_str(trade.get("direction"), "LONG")
        t_position_value = t_shares * t_entry_price
        total_trade_pnl += t_pnl

        win_loss = "WIN" if t_pnl > 0 else "LOSS" if t_pnl < 0 else "FLAT"
        lines.append(f"  Trade #{i+1}: {t_direction} {t_shares} shares @ ${t_entry_price:.2f}")
        lines.append(f"    Entry:    {t_entry}")
        lines.append(f"    Exit:     {t_exit} ({t_exit_reason})")
        lines.append(f"    Exit $:   ${t_exit_price:.2f} (move: ${t_exit_price - t_entry_price:+.2f})")
        lines.append(f"    Position: ${t_position_value:,.0f}")
        lines.append(f"    P&L:      ${t_pnl:,.2f} ({win_loss})")
    lines.append(f"")

    # ── Guard Block Breakdown ──
    lines.append(f"Guard Analysis:")
    lines.append(f"  Total blocks: {guard_blocks}")
    if guard_details:
        lines.append(f"  Breakdown by type:")
        for guard_type, count in sorted(guard_details.items(), key=lambda x: -safe_int(x[1])):
            pct = (safe_int(count) / guard_blocks * 100) if guard_blocks > 0 else 0
            lines.append(f"    {guard_type}: {count} ({pct:.0f}%)")
    else:
        lines.append(f"  No guard type breakdown available")
    lines.append(f"")

    # ── Diagnosis & Root Cause ──
    lines.append(f"Diagnosis:")
    for d in diags:
        lines.append(f"  - {d}")
    lines.append(f"")

    lines.append(f"Root Cause: {primary}")
    if primary in CODE_PATHS:
        cp = CODE_PATHS[primary]
        lines.append(f"  File:     {cp['file']}")
        lines.append(f"  Function: {cp['function']}")
        lines.append(f"  Context:  {cp['description']}")
    lines.append(f"")

    # ── Specific Recommendation ──
    lines.append(f"Recommended Fix:")
    if primary == "LATE_ENTRY":
        lines.append(f"  In {CODE_PATHS['LATE_ENTRY']['file']}:")
        lines.append(f"  Reduce min_bar_count and min_volume thresholds in check_active_market()")
        lines.append(f"  for premarket entries (before 9:30 AM).")
    elif primary == "GUARD_BLOCKED":
        top_guard = max(guard_details.items(), key=lambda x: safe_int(x[1]))[0] if guard_details else "unknown"
        lines.append(f"  Top blocking guard: {top_guard} ({safe_int(guard_details.get(top_guard, 0))} blocks)")
        lines.append(f"  In {CODE_PATHS['GUARD_BLOCKED']['file']}:")
        lines.append(f"  Review {top_guard} guard thresholds — may be too restrictive for strong runners.")
    elif primary == "STOP_HIT":
        lines.append(f"  In {CODE_PATHS['STOP_HIT']['file']}:")
        lines.append(f"  Check mental_stop_cents vs ATR ratio. If stop < 0.5x ATR, it's likely too tight.")
    elif primary == "OVERSIZED":
        lines.append(f"  In {CODE_PATHS['OVERSIZED']['file']}:")
        lines.append(f"  Review position sizing. Max position value should respect risk limits.")
    elif primary == "NO_ENTRY":
        lines.append(f"  Check why no entry was triggered. Look at scanner logs and entry patterns.")
    else:
        lines.append(f"  Manual investigation needed.")
    lines.append(f"")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────
def resolve_case_ids(args: list[str], test_cases: dict) -> list[str] | None:
    """Resolve CLI args to case_ids. Supports full IDs or symbol lookup."""
    if not args:
        return None  # batch mode
    case_ids = []
    for arg in args:
        if arg.startswith("ross_"):
            case_ids.append(arg)
        else:
            # Lookup by symbol name
            symbol_upper = arg.upper()
            matches = [cid for cid, tc in test_cases.items()
                       if safe_str(tc.get("symbol", "")).upper() == symbol_upper]
            if matches:
                case_ids.extend(matches)
            else:
                print(f"WARNING: No test case found for symbol '{arg}'")
    return case_ids if case_ids else None


def main():
    # Check server health
    try:
        fetch_json(f"{BASE_URL}/health", timeout=5)
    except Exception:
        print("ERROR: Nexus server not running on port 8000. Start it first.")
        sys.exit(1)

    # Parse CLI args for specific case IDs
    cli_args = sys.argv[1:]

    # Load YAML for detailed analysis
    yaml_setups = load_setups_yaml()

    # Fetch test case metadata first (needed for symbol lookup)
    try:
        tc_data = fetch_json(f"{BASE_URL}/warrior/sim/test_cases", timeout=30)
        test_cases = {}
        for tc in safe_list(tc_data.get("test_cases") if isinstance(tc_data, dict) else []):
            if isinstance(tc, dict) and "id" in tc:
                test_cases[tc["id"]] = tc
    except Exception:
        test_cases = {}

    # Resolve CLI args to case IDs
    target_case_ids = resolve_case_ids(cli_args, test_cases)
    deep_mode = target_case_ids is not None

    if deep_mode:
        print(f"Deep diagnosis mode: {len(target_case_ids)} case(s)")
    else:
        print("Running full batch test (this takes 2-5 minutes)...")

    # Run batch (with optional case_id filter)
    batch_body = {"include_trades": True}
    if target_case_ids:
        batch_body["case_ids"] = target_case_ids

    try:
        batch = fetch_json(
            f"{BASE_URL}/warrior/sim/run_batch_concurrent",
            method="POST",
            body=batch_body,
            timeout=600,
        )
    except Exception as e:
        print(f"ERROR: Batch test failed: {e}")
        sys.exit(1)

    if not isinstance(batch, dict):
        print("ERROR: Unexpected response format from batch endpoint")
        sys.exit(1)

    results = safe_list(batch.get("results"))
    summary = safe_dict(batch.get("summary"))

    # Diagnose each case
    case_diagnoses = []
    for r in results:
        if not isinstance(r, dict):
            continue
        case_id = safe_str(r.get("case_id"))
        symbol = safe_str(r.get("symbol"), "???")
        tc = test_cases.get(case_id)
        diags = diagnose_case(r, tc)
        bot_pnl = safe_num(r.get("total_pnl"))
        ross_pnl = safe_num(r.get("ross_pnl"))
        delta = bot_pnl - ross_pnl
        case_diagnoses.append({
            "symbol": symbol,
            "case_id": case_id,
            "bot_pnl": bot_pnl,
            "ross_pnl": ross_pnl,
            "delta": delta,
            "guard_blocks": safe_int(r.get("guard_block_count")),
            "guard_details": safe_dict(r.get("guard_block_details")),
            "guard_analysis": r.get("guard_analysis"),
            "trade_count": len(safe_list(r.get("trades"))),
            "diagnoses": diags,
            "primary": diags[0].split(":")[0] if diags else "UNKNOWN",
        })

    if not case_diagnoses:
        print("WARNING: No results to diagnose.")
        return

    # Group by category
    categories = defaultdict(lambda: {"cases": [], "total_gap": 0.0, "count": 0})
    for cd in case_diagnoses:
        cat = cd["primary"]
        categories[cat]["cases"].append(cd["symbol"])
        categories[cat]["total_gap"] += abs(cd["delta"])
        categories[cat]["count"] += 1

    # Sort categories by dollar impact
    sorted_cats = sorted(categories.items(), key=lambda x: x[1]["total_gap"], reverse=True)

    # Sort cases by delta (worst first)
    case_diagnoses.sort(key=lambda x: x["delta"])

    # Aggregate guard blocks
    total_guards = sum(cd["guard_blocks"] for cd in case_diagnoses)
    guard_types = defaultdict(int)
    for cd in case_diagnoses:
        for k, v in safe_dict(cd.get("guard_details")).items():
            guard_types[k] += safe_int(v)

    # Build report
    bot_total = safe_num(summary.get("total_pnl")) or sum(cd["bot_pnl"] for cd in case_diagnoses)
    ross_total = safe_num(summary.get("total_ross_pnl")) or sum(cd["ross_pnl"] for cd in case_diagnoses)
    capture = (bot_total / ross_total * 100) if ross_total > 0 else 0

    lines = []
    lines.append(f"Batch Diagnosis Report ({len(results)} cases)")
    lines.append(f"Bot Total: ${bot_total:,.2f} | Ross Total: ${ross_total:,.2f} | Capture: {capture:.1f}%")
    lines.append("")
    lines.append("Issue Priority Ranking:")

    icons = ["[P1-CRIT]", "[P2-HIGH]", "[P3-MED]", "[P4-LOW]", "[P5]", "[P6]"]
    recommendations = {
        "LATE_ENTRY": "Relax premarket active-market gate thresholds",
        "GUARD_BLOCKED": "Review MACD and reentry guard aggressiveness",
        "NO_RE_ENTRY": "Add re-entry logic after stop-out on strong runners",
        "HELD_TO_CLOSE": "Implement intraday exit rules for losing positions",
        "OVERSIZED": "Review position sizing relative to stop distance",
        "STOP_HIT": "Evaluate stop width -- may be too tight or too wide",
        "PARTIAL": "Fine-tune entry timing and scaling",
        "OK": "No action needed",
        "ROSS_LOSS": "Ross also lost -- not a bot issue",
        "UNKNOWN": "Manual investigation needed",
    }

    for i, (cat, data) in enumerate(sorted_cats):
        icon = icons[min(i, len(icons) - 1)]
        cases_str = ", ".join(data["cases"][:8])
        if len(data["cases"]) > 8:
            cases_str += f" (+{len(data['cases']) - 8} more)"
        rec = recommendations.get(cat, "Investigate further")
        lines.append(f"{icon} {cat}: {data['count']} cases, ~${data['total_gap']:,.0f} P&L gap")
        lines.append(f"   Cases: {cases_str}")
        lines.append(f"   Fix: {rec}")

    lines.append("")
    guard_str = ", ".join(f"{k}: {v}" for k, v in sorted(guard_types.items(), key=lambda x: -x[1]))
    lines.append(f"Guard Blocks: {total_guards} total ({guard_str})")

    # Guard Effectiveness Analysis (Phase 2)
    guard_analyses = [cd.get("guard_analysis") for cd in case_diagnoses if cd.get("guard_analysis")]
    if guard_analyses:
        lines.append("")
        lines.append("Guard Effectiveness Analysis:")
        # Aggregate across all cases
        all_correct = sum(ga.get("correct_blocks", 0) for ga in guard_analyses)
        all_missed = sum(ga.get("missed_opportunities", 0) for ga in guard_analyses)
        all_analyzed = sum(ga.get("analyzed_blocks", 0) for ga in guard_analyses)
        net_impact = sum(ga.get("net_guard_impact", 0) for ga in guard_analyses)
        overall_accuracy = round(all_correct / (all_correct + all_missed), 3) if (all_correct + all_missed) > 0 else None
        lines.append(f"  Analyzed: {all_analyzed} blocks | Correct: {all_correct} | Missed: {all_missed} | Accuracy: {overall_accuracy or 'N/A'}")
        lines.append(f"  Net Guard Impact: ${net_impact:,.2f} (negative = guards saved money)")
        # Per-guard-type breakdown
        merged_guards = defaultdict(lambda: {"blocks": 0, "correct": 0, "missed": 0, "net_impact": 0.0})
        for ga in guard_analyses:
            for gtype, stats in ga.get("by_guard_type", {}).items():
                merged_guards[gtype]["blocks"] += stats.get("blocks", 0)
                merged_guards[gtype]["correct"] += stats.get("correct", 0)
                merged_guards[gtype]["missed"] += stats.get("missed", 0)
                merged_guards[gtype]["net_impact"] += stats.get("net_impact", 0)
        for gtype, stats in sorted(merged_guards.items(), key=lambda x: -abs(x[1]["net_impact"])):
            gt_total = stats["correct"] + stats["missed"]
            acc = f"{stats['correct']}/{gt_total}" if gt_total > 0 else "N/A"
            lines.append(f"    {gtype}: {stats['blocks']} blocks, accuracy={acc}, impact=${stats['net_impact']:,.2f}")

    lines.append("")
    lines.append("Per-Case Summary (sorted by delta, worst first):")
    for cd in case_diagnoses:
        diag_str = " + ".join(cd["diagnoses"])
        lines.append(f"  {cd['symbol']}: Bot ${cd['bot_pnl']:,.2f} vs Ross ${cd['ross_pnl']:,.2f} (delta ${cd['delta']:,.2f}) -- {diag_str}")

    report = "\n".join(lines)
    print(report)

    # If deep mode, also output the deep analysis
    if deep_mode:
        print("\n" + "="*60)
        print("DEEP ANALYSIS (per case)")
        print("="*60)
        for r in results:
            if not isinstance(r, dict):
                continue
            case_id = safe_str(r.get("case_id"))
            tc = test_cases.get(case_id)
            setup = yaml_setups.get(case_id)
            deep_text = deep_analyze_case(r, tc, setup)
            print(deep_text)

    # Write to file
    try:
        os.makedirs(DIAG_DIR, exist_ok=True)
        report_path = os.path.join(DIAG_DIR, "_batch_diagnosis.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Batch Diagnosis Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("```\n")
            f.write(report)
            f.write("\n```\n")
            # Append deep analysis if in deep mode
            if deep_mode:
                f.write("\n## Deep Analysis\n\n```\n")
                for r in results:
                    if not isinstance(r, dict):
                        continue
                    case_id = safe_str(r.get("case_id"))
                    tc = test_cases.get(case_id)
                    setup = yaml_setups.get(case_id)
                    f.write(deep_analyze_case(r, tc, setup))
                    f.write("\n")
                f.write("```\n")
        print(f"\nReport saved to: {report_path}")
    except Exception as e:
        print(f"WARNING: Could not save report file: {e}")


if __name__ == "__main__":
    main()

