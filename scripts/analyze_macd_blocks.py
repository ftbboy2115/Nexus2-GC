"""
MACD Block Bucket Analysis Script

Runs batch test, classifies each MACD block into buckets (A/B/C),
cross-references with counterfactual P&L, and produces a report.

Usage:
  python scripts/analyze_macd_blocks.py              # Run fresh batch
  python scripts/analyze_macd_blocks.py --from-file  # Re-analyze last saved batch
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime

# Fix Windows encoding — PowerShell default codec can't handle emojis
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except (AttributeError, TypeError):
    pass

import urllib.request

BASE_URL = "http://127.0.0.1:8000"
NEXUS_PATH = os.environ.get(
    "NEXUS_PATH",
    r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus",
)
REPORT_DIR = os.path.join(NEXUS_PATH, "nexus2", "reports", "2026-02-24")
BATCH_CACHE = os.path.join(REPORT_DIR, "_macd_batch_cache.json")


# ── Helpers ──────────────────────────────────────────────────────────


def fetch_json(
    url: str, method: str = "GET", body: dict | None = None, timeout: int = 600
) -> dict:
    """Fetch JSON from Nexus API."""
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def safe_num(val, default=0):
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_list(val):
    return val if isinstance(val, list) else []


def safe_dict(val):
    return val if isinstance(val, dict) else {}


# ── MACD Parsing ─────────────────────────────────────────────────────

# Regex for the reason string format from warrior_entry_guards.py:217-221
# "MACD GATE - blocking entry (histogram=-0.0847 < tolerance=-0.02, crossover=neutral)..."
HISTOGRAM_RE = re.compile(r"histogram=(-?[\d.]+)")
TOLERANCE_RE = re.compile(r"tolerance=(-?[\d.]+)")
CROSSOVER_RE = re.compile(r"crossover=(\w+)")


def parse_macd_from_reason(reason: str) -> tuple[float | None, str]:
    """
    Extract histogram value and crossover state from guard block reason string.

    Returns:
        (histogram_value, crossover_state) or (None, "unknown") if parse fails
    """
    hist_match = HISTOGRAM_RE.search(reason)
    cross_match = CROSSOVER_RE.search(reason)

    histogram = float(hist_match.group(1)) if hist_match else None
    crossover = cross_match.group(1) if cross_match else "unknown"

    return histogram, crossover


# ── MACD Trajectory (for Bucket C) ───────────────────────────────────


def compute_macd_trajectory(
    case_id: str, symbol: str, blocked_time: str
) -> list[float]:
    """
    Compute MACD histogram for the 5 bars preceding blocked_time.

    Uses HistoricalBarLoader to load bar data and pandas-ta for MACD.
    Returns list of histogram values (oldest first), length up to 5.
    """
    try:
        from nexus2.adapters.simulation.historical_bar_loader import (
            HistoricalBarLoader,
        )

        loader = HistoricalBarLoader()
        data = loader.load_test_case(case_id)
        if not data or not data.bars:
            return []

        # Get bars up to the blocked time (including continuity for MACD)
        bars = data.get_bars_up_to(blocked_time, include_continuity=True)
        if not bars or len(bars) < 26:
            # Need at least 26 bars for MACD slow period
            return []

        # Convert to candle dicts for TechnicalService
        candle_dicts = [
            {
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]

        # Compute MACD for last 6 bars (need 6 to get 5 preceding histograms)
        # We compute on the full bar set, then extract the last 6 histogram values
        import pandas as pd
        import pandas_ta as ta

        df = pd.DataFrame(candle_dicts)
        for col in ["high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd_df is None or macd_df.empty:
            return []

        hist_col = "MACDh_12_26_9"
        if hist_col not in macd_df.columns:
            return []

        # Get the last 6 histogram values (last one is the block bar,
        # preceding 5 are what we want)
        hist_values = macd_df[hist_col].dropna().tail(6).tolist()

        # Return the 5 bars BEFORE the block bar
        if len(hist_values) > 1:
            return hist_values[:-1]  # Exclude the block bar itself
        return hist_values

    except Exception as e:
        # Trajectory computation is best-effort
        return []


# ── Block Classification ─────────────────────────────────────────────

# Bucket thresholds from spec
DEEPLY_NEGATIVE_THRESHOLD = -0.10


def classify_block(
    histogram: float | None, trajectory: list[float]
) -> str:
    """
    Classify MACD block into bucket A, B, or C.

    A = Deeply negative (histogram < -0.10) — legitimate block
    B = Near-zero oscillation (-0.10 to -0.02, no recent positive) — tolerance tuning
    C = Recently-crossed-then-dipped (-0.10 to -0.02, recent positive) — over-blocking
    """
    if histogram is None:
        return "UNKNOWN"

    if histogram < DEEPLY_NEGATIVE_THRESHOLD:
        return "A"

    # histogram between -0.10 and tolerance (-0.02)
    if trajectory and any(h > 0 for h in trajectory):
        return "C"
    else:
        return "B"


# ── Histogram Distribution Chart ─────────────────────────────────────

HISTOGRAM_BINS = [
    ("<-0.50", lambda h: h < -0.50),
    ("-0.50 to -0.30", lambda h: -0.50 <= h < -0.30),
    ("-0.30 to -0.10", lambda h: -0.30 <= h < -0.10),
    ("-0.10 to -0.05", lambda h: -0.10 <= h < -0.05),
    ("-0.05 to -0.02", lambda h: -0.05 <= h < -0.02),
]

BAR_CHAR = "█"
MAX_BAR_WIDTH = 40


def make_histogram_chart(histogram_values: list[float]) -> str:
    """Create a text-based histogram distribution chart."""
    counts = {}
    for label, predicate in HISTOGRAM_BINS:
        counts[label] = sum(1 for h in histogram_values if predicate(h))

    max_count = max(counts.values()) if counts else 1
    lines = ["Histogram Distribution:"]
    for label, count in counts.items():
        bar_len = int((count / max_count) * MAX_BAR_WIDTH) if max_count > 0 else 0
        bar = BAR_CHAR * bar_len
        lines.append(f"  {label:>16s}:  {bar}  {count:,} blocks")
    lines.append("  (Note: -0.02 to 0 = tolerance zone, not blocked)")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────


def main():
    from_file = "--from-file" in sys.argv

    # ── Step 0: Check server health (unless reading from cache) ──
    if not from_file:
        try:
            fetch_json(f"{BASE_URL}/health", timeout=5)
        except Exception:
            print("ERROR: Nexus server not running on port 8000. Start it first.")
            sys.exit(1)

    # ── Step 1: Run batch test (or load from cache) ──
    if from_file and os.path.exists(BATCH_CACHE):
        print(f"Loading cached batch from {BATCH_CACHE}...")
        with open(BATCH_CACHE, "r", encoding="utf-8") as f:
            batch = json.load(f)
    else:
        print("Running full batch test (this takes 2-5 minutes)...")
        start_time = time.time()
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
        elapsed = time.time() - start_time
        print(f"Batch completed in {elapsed:.1f}s")

        # Cache results for re-analysis
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(BATCH_CACHE, "w", encoding="utf-8") as f:
            json.dump(batch, f)
        print(f"Cached results to {BATCH_CACHE}")

    if not isinstance(batch, dict):
        print("ERROR: Unexpected response format from batch endpoint")
        sys.exit(1)

    results = safe_list(batch.get("results"))
    print(f"Analyzing {len(results)} case results...")

    # ── Step 2: Extract all MACD blocks ──
    macd_blocks = []
    unparse_count = 0

    for result in results:
        if not isinstance(result, dict):
            continue
        case_id = result.get("case_id", "")
        symbol = result.get("symbol", "")

        for block in safe_list(result.get("guard_blocks")):
            if block.get("guard") != "macd":
                continue

            reason = block.get("reason", "")
            histogram, crossover = parse_macd_from_reason(reason)

            if histogram is None:
                unparse_count += 1
                continue

            macd_blocks.append(
                {
                    "case_id": case_id,
                    "symbol": symbol,
                    "histogram": histogram,
                    "crossover": crossover,
                    "blocked_price": block.get("blocked_price"),
                    "blocked_time": block.get("blocked_time"),
                    "reason": reason,
                }
            )

    print(f"Found {len(macd_blocks)} MACD blocks ({unparse_count} unparseable)")

    if not macd_blocks:
        print("No MACD blocks found. Nothing to analyze.")
        return

    # ── Step 3: Compute trajectories for Bucket B/C candidates ──
    # Only compute trajectory for blocks in the B/C range (not deeply negative)
    bc_candidates = [
        b for b in macd_blocks if b["histogram"] >= DEEPLY_NEGATIVE_THRESHOLD
    ]
    print(
        f"Computing MACD trajectories for {len(bc_candidates)} "
        f"B/C candidates (skipping {len(macd_blocks) - len(bc_candidates)} Bucket A)..."
    )

    # Group by case_id to avoid reloading bars for every block
    case_blocks = defaultdict(list)
    for b in bc_candidates:
        case_blocks[b["case_id"]].append(b)

    trajectory_count = 0
    trajectory_fail = 0
    for case_id, blocks in case_blocks.items():
        symbol = blocks[0]["symbol"]
        for b in blocks:
            blocked_time = b.get("blocked_time")
            if not blocked_time:
                b["trajectory"] = []
                trajectory_fail += 1
                continue

            trajectory = compute_macd_trajectory(case_id, symbol, blocked_time)
            b["trajectory"] = trajectory
            if trajectory:
                trajectory_count += 1
            else:
                trajectory_fail += 1

    print(
        f"Trajectories: {trajectory_count} computed, {trajectory_fail} failed/skipped"
    )

    # ── Step 4: Classify all blocks ──
    for b in macd_blocks:
        trajectory = b.get("trajectory", [])
        b["bucket"] = classify_block(b["histogram"], trajectory)

    # ── Step 5: Cross-reference with counterfactual P&L ──
    # Build lookup: (case_id) -> guard_analysis.details
    counterfactual_lookup = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        case_id = result.get("case_id", "")
        ga = safe_dict(result.get("guard_analysis"))
        details = safe_list(ga.get("details"))
        if details:
            counterfactual_lookup[case_id] = details

    matched = 0
    for b in macd_blocks:
        case_details = counterfactual_lookup.get(b["case_id"], [])
        # Match by blocked_time and guard type
        for detail in case_details:
            if (
                detail.get("guard") == "macd"
                and detail.get("blocked_time") == b.get("blocked_time")
            ):
                b["outcome"] = detail.get("outcome", "NO_DATA")
                b["hypothetical_pnl_15m"] = detail.get("hypothetical_pnl_15m", 0)
                b["mfe"] = detail.get("mfe", 0)
                b["mae"] = detail.get("mae", 0)
                b["price_5m"] = detail.get("price_5m")
                b["price_15m"] = detail.get("price_15m")
                b["price_30m"] = detail.get("price_30m")
                matched += 1
                break

    # Blocks without counterfactual match
    for b in macd_blocks:
        if "outcome" not in b:
            b["outcome"] = "NO_DATA"
            b["hypothetical_pnl_15m"] = 0

    print(f"Counterfactual match: {matched}/{len(macd_blocks)}")

    # ── Step 6: Aggregate and generate report ──
    histogram_values = [b["histogram"] for b in macd_blocks]

    # Per-bucket aggregation
    bucket_stats = {}
    for bucket_label in ["A", "B", "C", "UNKNOWN"]:
        bucket_blocks = [b for b in macd_blocks if b["bucket"] == bucket_label]
        if not bucket_blocks:
            continue

        histograms = [b["histogram"] for b in bucket_blocks]
        saved = sum(1 for b in bucket_blocks if b["outcome"] == "CORRECT_BLOCK")
        cost = sum(1 for b in bucket_blocks if b["outcome"] == "MISSED_OPPORTUNITY")
        neutral = sum(1 for b in bucket_blocks if b["outcome"] == "NO_DATA")
        net_pnl = sum(
            b.get("hypothetical_pnl_15m", 0) for b in bucket_blocks
        )

        bucket_stats[bucket_label] = {
            "count": len(bucket_blocks),
            "pct": round(len(bucket_blocks) / len(macd_blocks) * 100, 1),
            "avg_histogram": round(sum(histograms) / len(histograms), 4),
            "min_histogram": round(min(histograms), 4),
            "max_histogram": round(max(histograms), 4),
            "saved": saved,
            "cost": cost,
            "neutral": neutral,
            "net_pnl": round(net_pnl, 2),
        }

    # ── Build report text ──
    lines = []
    lines.append(
        f"MACD Block Bucket Analysis ({len(results)} cases, "
        f"{len(macd_blocks)} MACD blocks)"
    )
    lines.append("=" * 60)
    lines.append("")

    # Histogram distribution
    lines.append(make_histogram_chart(histogram_values))
    lines.append("")

    # Bucket classification table
    lines.append("Bucket Classification:")
    lines.append(
        f"{'Bucket':<32s} | {'Count':>6s} | {'%':>5s} | {'Avg Hist':>9s} | "
        f"{'SAVED':>5s} | {'COST':>5s} | {'NEUTRAL':>7s} | {'Net P&L/sh':>10s}"
    )
    lines.append("-" * 100)

    bucket_labels = {
        "A": "A (deeply negative)",
        "B": "B (near-zero oscillation)",
        "C": "C (recently-crossed-dipped)",
        "UNKNOWN": "UNKNOWN (parse fail)",
    }

    for bk in ["A", "B", "C", "UNKNOWN"]:
        stats = bucket_stats.get(bk)
        if not stats:
            continue
        label = bucket_labels.get(bk, bk)
        lines.append(
            f"{label:<32s} | {stats['count']:>6,d} | {stats['pct']:>4.1f}% | "
            f"{stats['avg_histogram']:>9.4f} | {stats['saved']:>5d} | "
            f"{stats['cost']:>5d} | {stats['neutral']:>7d} | "
            f"${stats['net_pnl']:>9.2f}"
        )

    lines.append("")

    # Per-bucket detail
    for bk in ["A", "B", "C"]:
        stats = bucket_stats.get(bk)
        if not stats:
            continue
        label = bucket_labels.get(bk, bk)
        total_decided = stats["saved"] + stats["cost"]
        if total_decided > 0:
            accuracy = stats["saved"] / total_decided * 100
        else:
            accuracy = None

        lines.append(f"  {label}:")
        lines.append(
            f"    Histogram range: [{stats['min_histogram']:.4f}, "
            f"{stats['max_histogram']:.4f}]"
        )
        if accuracy is not None:
            acc_str = f"{accuracy:.1f}% ({stats['saved']}/{total_decided})"
        else:
            acc_str = "N/A (no counterfactual data)"
        lines.append(f"    Block accuracy: {acc_str}")
        if stats["net_pnl"] < 0:
            lines.append(
                f"    Net impact: ${stats['net_pnl']:.2f}/share "
                f"(negative = guards SAVED money)"
            )
        else:
            lines.append(
                f"    Net impact: ${stats['net_pnl']:.2f}/share "
                f"(positive = guards COST money)"
            )
        lines.append("")

    # Recommendation
    lines.append("=" * 60)
    lines.append("RECOMMENDATION:")
    lines.append("")

    c_stats = bucket_stats.get("C")
    b_stats = bucket_stats.get("B")
    a_stats = bucket_stats.get("A")

    if c_stats and c_stats["cost"] > c_stats["saved"]:
        lines.append(
            "  >>> ADD RECENTLY-CROSSED BUFFER <<<\n"
            f"  Bucket C has {c_stats['cost']} COST vs {c_stats['saved']} SAVED blocks.\n"
            f"  Net P&L impact: ${c_stats['net_pnl']:.2f}/share — gate is over-blocking.\n"
            "  Proposed fix: If MACD histogram was > 0 within last 5 bars,\n"
            "  treat as 'recently bullish' and allow entry despite current\n"
            "  slightly negative histogram."
        )
    elif c_stats and c_stats["cost"] <= c_stats["saved"]:
        lines.append(
            "  >>> KEEP CURRENT GATE (Bucket C is net-positive) <<<\n"
            f"  Bucket C has {c_stats['saved']} SAVED vs {c_stats['cost']} COST blocks.\n"
            f"  Net P&L impact: ${c_stats['net_pnl']:.2f}/share — gate is correctly blocking.\n"
            "  No change recommended for the recently-crossed scenario."
        )
    else:
        lines.append(
            "  >>> INSUFFICIENT DATA for Bucket C <<<\n"
            "  Could not compute enough trajectories to classify B vs C.\n"
            "  Review tolerance threshold separately."
        )

    if b_stats:
        b_decided = b_stats["saved"] + b_stats["cost"]
        if b_decided > 0:
            b_accuracy = b_stats["saved"] / b_decided * 100
            if b_accuracy < 60:
                lines.append(
                    f"\n  Bucket B accuracy is {b_accuracy:.1f}% — "
                    f"consider widening tolerance from -0.02."
                )
            else:
                lines.append(
                    f"\n  Bucket B accuracy is {b_accuracy:.1f}% — "
                    f"current tolerance -0.02 is reasonable."
                )

    if a_stats:
        a_decided = a_stats["saved"] + a_stats["cost"]
        if a_decided > 0:
            a_accuracy = a_stats["saved"] / a_decided * 100
            lines.append(
                f"\n  Bucket A accuracy: {a_accuracy:.1f}% — "
                f"deeply negative blocks are {'correctly' if a_accuracy > 70 else 'questionably'} blocked."
            )

    lines.append("")

    # Top symbols with most MACD blocks
    symbol_counts = defaultdict(int)
    for b in macd_blocks:
        symbol_counts[b["symbol"]] += 1
    top_symbols = sorted(symbol_counts.items(), key=lambda x: -x[1])[:10]

    lines.append("Top 10 Symbols by MACD Block Count:")
    for sym, count in top_symbols:
        lines.append(f"  {sym}: {count} blocks")
    lines.append("")

    report = "\n".join(lines)

    # ── Output ──
    print()
    print(report)

    # Write markdown report
    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, "analysis_macd_blocks.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# MACD Block Bucket Analysis\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("```\n")
        f.write(report)
        f.write("\n```\n")

        # Append raw data summary for further analysis
        f.write("\n## Raw Data Summary\n\n")
        f.write(f"- Total MACD blocks: {len(macd_blocks)}\n")
        f.write(f"- Unparseable blocks: {unparse_count}\n")
        f.write(f"- Trajectories computed: {trajectory_count}\n")
        f.write(f"- Trajectories failed: {trajectory_fail}\n")
        f.write(f"- Counterfactual matched: {matched}/{len(macd_blocks)}\n")
        f.write("\n### Per-Bucket Breakdown\n\n")
        for bk in ["A", "B", "C", "UNKNOWN"]:
            stats = bucket_stats.get(bk)
            if stats:
                f.write(
                    f"**Bucket {bk}:** {stats['count']} blocks, "
                    f"avg hist={stats['avg_histogram']:.4f}, "
                    f"saved={stats['saved']}, cost={stats['cost']}, "
                    f"neutral={stats['neutral']}, "
                    f"net_pnl=${stats['net_pnl']:.2f}/sh\n\n"
                )

    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
