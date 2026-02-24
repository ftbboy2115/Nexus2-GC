"""
GC Batch Diagnosis Script
Runs all test cases, categorizes issues, and produces a priority report.
Called by Gravity Claw via shell_exec — outputs only the summary.
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
from datetime import datetime
from collections import defaultdict

BASE_URL = "http://localhost:8000"
NEXUS_PATH = os.environ.get("NEXUS_PATH", r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus")
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
            try:
                bot_entry = safe_str(trades[0].get("entry_time") if isinstance(trades[0], dict) else "")
                if bot_entry and ":" in bot_entry and ":" in ross_entry:
                    ross_parts = ross_entry.replace("~", "").strip().split(":")
                    ross_minutes = int(ross_parts[0]) * 60 + int(ross_parts[1])

                    bot_time_str = bot_entry
                    if "T" in bot_time_str:
                        bot_time_str = bot_time_str.split("T")[1]
                    bot_parts = bot_time_str.split(":")
                    bot_minutes = int(bot_parts[0]) * 60 + int(bot_parts[1])

                    diff = bot_minutes - ross_minutes
                    if diff > 30:
                        hours = diff // 60
                        mins = diff % 60
                        diagnoses.append(f"LATE_ENTRY: Bot entered {hours}h{mins}m after Ross")
            except (ValueError, IndexError, AttributeError):
                pass

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


# ── Main ─────────────────────────────────────────────────────────────
def main():
    # Check server health
    try:
        fetch_json(f"{BASE_URL}/health", timeout=5)
    except Exception:
        print("ERROR: Nexus server not running on port 8000. Start it first.")
        sys.exit(1)

    print("Running batch test (this takes 2-5 minutes)...")

    # Fetch batch results with trades
    try:
        batch = fetch_json(
            f"{BASE_URL}/warrior/sim/run_batch_concurrent",
            method="POST",
            body={"include_trades": True},
            timeout=600,
        )
    except Exception as e:
        print(f"ERROR: Batch test failed: {e}")
        sys.exit(1)

    if not isinstance(batch, dict):
        print("ERROR: Unexpected response format from batch endpoint")
        sys.exit(1)

    # Fetch test case metadata
    try:
        tc_data = fetch_json(f"{BASE_URL}/warrior/sim/test_cases", timeout=30)
        test_cases = {}
        for tc in safe_list(tc_data.get("test_cases") if isinstance(tc_data, dict) else []):
            if isinstance(tc, dict) and "id" in tc:
                test_cases[tc["id"]] = tc
    except Exception:
        test_cases = {}

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
        print(f"\nReport saved to: {report_path}")
    except Exception as e:
        print(f"WARNING: Could not save report file: {e}")


if __name__ == "__main__":
    main()

