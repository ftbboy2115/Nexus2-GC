"""
GC Bag Holding Deep Analysis — Per-case price action, entry trigger correlation,
time-to-profit, and MFE analysis for all 38 batch test cases.

Outputs a comprehensive JSON and a summary to stdout.

Usage:
  python scripts/gc_bag_holding_analysis.py
  python scripts/gc_bag_holding_analysis.py --json  # JSON output only
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

# Fix Windows encoding
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except (AttributeError, TypeError):
    pass

BASE_URL = "http://127.0.0.1:8000"
NEXUS_PATH = os.environ.get(
    "NEXUS_PATH",
    r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
)
OUTPUT_DIR = os.path.join(NEXUS_PATH, "nexus2", "reports", "2026-03-02")

# Standardized batch settings
BATCH_CONFIG_OVERRIDES = {
    "risk_per_trade": "2500",
    "max_capital": "100000",
    "max_shares_per_trade": 10000,
    "max_positions": 20,
    "entry_bar_timeframe": "1min",
}


def fetch_json(url: str, method: str = "GET", body: dict | None = None, timeout: int = 900) -> dict:
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def time_to_minutes(time_str: str) -> int | None:
    """Convert HH:MM or HH:MM:SS to minutes since midnight."""
    if not time_str:
        return None
    try:
        parts = time_str.replace("T", " ").strip()
        # Handle ISO format like 2026-02-09T08:00:20
        if " " in parts:
            parts = parts.split(" ")[1]
        if ":" in parts:
            components = parts.split(":")
            h, m = int(components[0]), int(components[1])
            return h * 60 + m
    except (ValueError, IndexError):
        pass
    return None


def compute_hold_minutes(entry_time, exit_time) -> int | None:
    """Compute hold time in minutes."""
    entry_min = time_to_minutes(str(entry_time)) if entry_time else None
    exit_min = time_to_minutes(str(exit_time)) if exit_time else None
    if entry_min is not None and exit_min is not None:
        return exit_min - entry_min
    return None


def classify_trade(trade: dict) -> str:
    """Classify trade into a behavior bucket."""
    pnl = trade.get("pnl", 0)
    exit_reason = trade.get("exit_reason", "")
    hold_min = compute_hold_minutes(trade.get("entry_time"), trade.get("exit_time"))

    if exit_reason in ("after_hours_exit", "eod_close"):
        if pnl < -500:
            return "BAG_HOLD_LOSS"
        elif pnl < 0:
            return "BAG_HOLD_SMALL_LOSS"
        else:
            return "BAG_HOLD_FLAT"
    elif exit_reason in ("stop_hit", "mental_stop_hit"):
        return "STOPPED_OUT"
    elif exit_reason in ("base_hit_target", "profit_target"):
        return "TARGET_HIT"
    elif exit_reason in ("candle_trail", "candle_under_candle"):
        return "TRAILED_OUT"
    elif exit_reason == "partial_exit":
        return "PARTIAL"
    elif hold_min and hold_min < 10:
        return "QUICK_EXIT"
    else:
        return f"OTHER ({exit_reason})"


def main():
    json_mode = "--json" in sys.argv
    
    if not json_mode:
        print("\n  Running batch test with trade details (38 cases)...")
        print("  This will take 2-3 minutes...\n")

    t0 = time.time()
    
    # Step 1: Run batch with include_trades=True
    body = {
        "include_trades": True,
        "config_overrides": BATCH_CONFIG_OVERRIDES,
    }
    result = fetch_json(f"{BASE_URL}/warrior/sim/run_batch_concurrent", method="POST", body=body)
    elapsed = time.time() - t0

    results = result.get("results", [])
    summary = result.get("summary", {})

    if not json_mode:
        print(f"  Batch complete in {elapsed:.1f}s — {len(results)} cases\n")

    # ── Step 2: Per-case analysis ──────────────────────────────────────────
    analysis = {
        "metadata": {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "runtime_seconds": round(elapsed, 1),
            "total_cases": len(results),
            "total_bot_pnl": summary.get("total_pnl", 0),
            "total_ross_pnl": summary.get("total_ross_pnl", 0),
        },
        "cases": [],
        "entry_trigger_stats": {},
        "exit_reason_stats": {},
        "behavior_stats": {},
        "bag_holding_cases": [],
        "time_to_profit_analysis": {},
    }

    # Aggregators
    trigger_stats = defaultdict(lambda: {"count": 0, "total_pnl": 0, "wins": 0, "losses": 0, "bag_holds": 0, "trades": []})
    exit_stats = defaultdict(lambda: {"count": 0, "total_pnl": 0})
    behavior_stats = defaultdict(lambda: {"count": 0, "total_pnl": 0, "cases": []})
    
    all_trades_flat = []

    for case in results:
        case_id = case.get("case_id", "unknown")
        symbol = case.get("symbol", "")
        total_pnl = case.get("total_pnl", 0)
        ross_pnl = case.get("ross_pnl", 0)
        trades = case.get("trades", [])

        case_analysis = {
            "case_id": case_id,
            "symbol": symbol,
            "date": case.get("date", ""),
            "total_pnl": total_pnl,
            "ross_pnl": ross_pnl,
            "delta": round(total_pnl - ross_pnl, 2),
            "trade_count": len(trades),
            "trades": [],
        }

        for trade in trades:
            entry_trigger = trade.get("entry_trigger", "unknown")
            exit_reason = trade.get("exit_reason", "unknown")
            pnl = trade.get("pnl", 0) or 0
            entry_price = trade.get("entry_price", 0)
            exit_price = trade.get("exit_price")
            shares = trade.get("shares", 0)
            stop_price = trade.get("stop_price")
            support_level = trade.get("support_level")
            hold_min = compute_hold_minutes(trade.get("entry_time"), trade.get("exit_time"))
            behavior = classify_trade(trade)

            # Compute stop distance
            stop_distance = None
            stop_pct = None
            if entry_price and stop_price:
                stop_distance = round(entry_price - float(stop_price), 4)
                stop_pct = round(stop_distance / entry_price * 100, 2) if entry_price > 0 else None

            trade_detail = {
                "entry_trigger": entry_trigger,
                "exit_reason": exit_reason,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "shares": shares,
                "pnl": pnl,
                "stop_price": stop_price,
                "stop_method": trade.get("stop_method"),
                "support_level": support_level,
                "stop_distance": stop_distance,
                "stop_pct": stop_pct,
                "hold_minutes": hold_min,
                "behavior": behavior,
                "entry_time": trade.get("entry_time"),
                "exit_time": trade.get("exit_time"),
                "exit_mode": trade.get("exit_mode"),
            }
            case_analysis["trades"].append(trade_detail)
            all_trades_flat.append({**trade_detail, "case_id": case_id, "symbol": symbol})

            # Aggregate by trigger
            trigger_stats[entry_trigger]["count"] += 1
            trigger_stats[entry_trigger]["total_pnl"] += pnl
            if pnl > 0:
                trigger_stats[entry_trigger]["wins"] += 1
            elif pnl < 0:
                trigger_stats[entry_trigger]["losses"] += 1
            if "BAG_HOLD" in behavior:
                trigger_stats[entry_trigger]["bag_holds"] += 1
            trigger_stats[entry_trigger]["trades"].append(trade_detail)

            # Aggregate by exit reason
            exit_stats[exit_reason]["count"] += 1
            exit_stats[exit_reason]["total_pnl"] += pnl

            # Aggregate by behavior
            behavior_stats[behavior]["count"] += 1
            behavior_stats[behavior]["total_pnl"] += pnl
            behavior_stats[behavior]["cases"].append(f"{symbol} ${pnl:,.0f}")

        analysis["cases"].append(case_analysis)

        # Track bag-holding cases
        bag_hold_trades = [t for t in case_analysis["trades"] if "BAG_HOLD" in t.get("behavior", "")]
        if bag_hold_trades:
            for bht in bag_hold_trades:
                analysis["bag_holding_cases"].append({
                    "case_id": case_id,
                    "symbol": symbol,
                    "pnl": bht["pnl"],
                    "entry_trigger": bht["entry_trigger"],
                    "entry_price": bht["entry_price"],
                    "exit_price": bht["exit_price"],
                    "stop_price": bht["stop_price"],
                    "stop_distance": bht["stop_distance"],
                    "stop_pct": bht["stop_pct"],
                    "hold_minutes": bht["hold_minutes"],
                    "entry_time": bht.get("entry_time"),
                    "exit_time": bht.get("exit_time"),
                })

    # ── Step 3: Finalize stats ─────────────────────────────────────────────

    # Entry trigger stats
    for trigger, stats in trigger_stats.items():
        avg_pnl = stats["total_pnl"] / stats["count"] if stats["count"] > 0 else 0
        win_rate = stats["wins"] / stats["count"] * 100 if stats["count"] > 0 else 0
        bag_rate = stats["bag_holds"] / stats["count"] * 100 if stats["count"] > 0 else 0
        
        # Compute avg hold time and avg stop distance for this trigger
        hold_times = [t.get("hold_minutes") for t in stats["trades"] if t.get("hold_minutes") is not None]
        stop_dists = [t.get("stop_pct") for t in stats["trades"] if t.get("stop_pct") is not None]
        
        analysis["entry_trigger_stats"][trigger] = {
            "count": stats["count"],
            "total_pnl": round(stats["total_pnl"], 2),
            "avg_pnl": round(avg_pnl, 2),
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": round(win_rate, 1),
            "bag_holds": stats["bag_holds"],
            "bag_hold_rate": round(bag_rate, 1),
            "avg_hold_min": round(sum(hold_times) / len(hold_times), 1) if hold_times else None,
            "avg_stop_pct": round(sum(stop_dists) / len(stop_dists), 2) if stop_dists else None,
        }

    # Exit reason stats
    for reason, stats in exit_stats.items():
        analysis["exit_reason_stats"][reason] = {
            "count": stats["count"],
            "total_pnl": round(stats["total_pnl"], 2),
            "avg_pnl": round(stats["total_pnl"] / stats["count"], 2) if stats["count"] > 0 else 0,
        }

    # Behavior stats
    for behavior, stats in behavior_stats.items():
        analysis["behavior_stats"][behavior] = {
            "count": stats["count"],
            "total_pnl": round(stats["total_pnl"], 2),
            "cases": stats["cases"][:10],  # Top 10 for brevity
        }

    # ── Step 4: Time-to-profit analysis ──────────────────────────────────
    # For winning trades: how quickly did they become profitable?
    winning_trades = [t for t in all_trades_flat if t.get("pnl", 0) > 0 and t.get("hold_minutes") is not None]
    losing_trades = [t for t in all_trades_flat if t.get("pnl", 0) < 0 and t.get("hold_minutes") is not None]
    
    analysis["time_to_profit_analysis"] = {
        "winners": {
            "count": len(winning_trades),
            "avg_hold_min": round(sum(t["hold_minutes"] for t in winning_trades) / len(winning_trades), 1) if winning_trades else 0,
            "median_hold_min": sorted([t["hold_minutes"] for t in winning_trades])[len(winning_trades)//2] if winning_trades else 0,
            "avg_pnl": round(sum(t["pnl"] for t in winning_trades) / len(winning_trades), 2) if winning_trades else 0,
        },
        "losers": {
            "count": len(losing_trades),
            "avg_hold_min": round(sum(t["hold_minutes"] for t in losing_trades) / len(losing_trades), 1) if losing_trades else 0,
            "median_hold_min": sorted([t["hold_minutes"] for t in losing_trades])[len(losing_trades)//2] if losing_trades else 0,
            "avg_pnl": round(sum(t["pnl"] for t in losing_trades) / len(losing_trades), 2) if losing_trades else 0,
        },
        "insight": "",
    }
    
    # Time bucket distribution
    time_buckets = {"0-5min": {"wins": 0, "losses": 0, "pnl": 0}, 
                    "5-15min": {"wins": 0, "losses": 0, "pnl": 0},
                    "15-60min": {"wins": 0, "losses": 0, "pnl": 0},
                    "60-240min": {"wins": 0, "losses": 0, "pnl": 0},
                    "240+min": {"wins": 0, "losses": 0, "pnl": 0}}
    
    for t in all_trades_flat:
        hold = t.get("hold_minutes")
        pnl = t.get("pnl", 0) or 0
        if hold is None:
            continue
        if hold <= 5: bucket = "0-5min"
        elif hold <= 15: bucket = "5-15min"
        elif hold <= 60: bucket = "15-60min"
        elif hold <= 240: bucket = "60-240min"
        else: bucket = "240+min"
        
        time_buckets[bucket]["pnl"] += pnl
        if pnl > 0:
            time_buckets[bucket]["wins"] += 1
        else:
            time_buckets[bucket]["losses"] += 1
    
    analysis["time_to_profit_analysis"]["time_buckets"] = time_buckets

    # Insight generation
    winner_avg_hold = analysis["time_to_profit_analysis"]["winners"]["avg_hold_min"]
    loser_avg_hold = analysis["time_to_profit_analysis"]["losers"]["avg_hold_min"]
    if winner_avg_hold and loser_avg_hold:
        analysis["time_to_profit_analysis"]["insight"] = (
            f"Winners avg hold: {winner_avg_hold:.0f}min, Losers avg hold: {loser_avg_hold:.0f}min. "
            f"Losers hold {loser_avg_hold/winner_avg_hold:.1f}x longer."
            if winner_avg_hold > 0 else "Insufficient data."
        )

    # ── Step 5: Output ─────────────────────────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "analysis_bag_holding_deep.json")
    with open(output_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)

    if json_mode:
        print(json.dumps(analysis, indent=2, default=str))
        return

    # ── Step 6: Human-readable summary ─────────────────────────────────────
    print("=" * 80)
    print("  BAG HOLDING DEEP ANALYSIS — ALL 38 CASES")
    print("=" * 80)
    
    print(f"\n  Total Bot P&L: ${analysis['metadata']['total_bot_pnl']:,.2f}")
    print(f"  Total Ross P&L: ${analysis['metadata']['total_ross_pnl']:,.2f}")
    
    # Entry trigger breakdown
    print(f"\n  ── ENTRY TRIGGER CORRELATION ──")
    print(f"  {'Trigger':<30s} | {'Count':>5s} | {'Avg P&L':>10s} | {'Win%':>5s} | {'Bag%':>5s} | {'Avg Stop%':>8s}")
    print(f"  {'-'*30}-+-{'-'*5}-+-{'-'*10}-+-{'-'*5}-+-{'-'*5}-+-{'-'*8}")
    
    for trigger, stats in sorted(analysis["entry_trigger_stats"].items(), key=lambda x: x[1]["total_pnl"]):
        avg_stop = f"{stats['avg_stop_pct']:.1f}%" if stats['avg_stop_pct'] else "N/A"
        print(f"  {trigger:<30s} | {stats['count']:>5d} | ${stats['avg_pnl']:>8,.0f} | {stats['win_rate']:>4.0f}% | {stats['bag_hold_rate']:>4.0f}% | {avg_stop:>8s}")

    # Behavior distribution
    print(f"\n  ── BEHAVIOR DISTRIBUTION ──")
    print(f"  {'Behavior':<25s} | {'Count':>5s} | {'Total P&L':>12s}")
    print(f"  {'-'*25}-+-{'-'*5}-+-{'-'*12}")
    for behavior, stats in sorted(analysis["behavior_stats"].items(), key=lambda x: x[1]["total_pnl"]):
        print(f"  {behavior:<25s} | {stats['count']:>5d} | ${stats['total_pnl']:>10,.0f}")

    # Bag holding cases
    print(f"\n  ── BAG HOLDING CASES (Held to EOD) ──")
    bag_cases = sorted(analysis["bag_holding_cases"], key=lambda x: x.get("pnl", 0))
    print(f"  {'Symbol':<8s} | {'Entry':>7s} | {'Exit':>7s} | {'Stop':>7s} | {'Stop%':>6s} | {'Hold':>5s} | {'P&L':>10s} | {'Trigger':<25s}")
    print(f"  {'-'*8}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}-+-{'-'*6}-+-{'-'*5}-+-{'-'*10}-+-{'-'*25}")
    for bc in bag_cases:
        stop_pct_str = f"{bc.get('stop_pct', 0):.1f}%" if bc.get('stop_pct') else "N/A"
        hold_str = f"{bc.get('hold_minutes', 0)}m" if bc.get('hold_minutes') else "?"
        entry_p = float(bc.get('entry_price', 0) or 0)
        exit_p = float(bc.get('exit_price', 0) or 0)
        stop_p = float(bc.get('stop_price', 0) or 0)
        print(f"  {bc['symbol']:<8s} | ${entry_p:>5.2f} | ${exit_p:>5.2f} | ${stop_p:>5.2f} | {stop_pct_str:>6s} | {hold_str:>5s} | ${bc.get('pnl', 0):>8,.0f} | {bc.get('entry_trigger', '?'):<25s}")

    # Time analysis
    print(f"\n  ── TIME-TO-PROFIT ANALYSIS ──")
    ttp = analysis["time_to_profit_analysis"]
    print(f"  {ttp['insight']}")
    print(f"\n  Time Bucket Distribution:")
    print(f"  {'Bucket':<12s} | {'Wins':>5s} | {'Losses':>6s} | {'Net P&L':>12s}")
    print(f"  {'-'*12}-+-{'-'*5}-+-{'-'*6}-+-{'-'*12}")
    for bucket, stats in ttp.get("time_buckets", {}).items():
        print(f"  {bucket:<12s} | {stats['wins']:>5d} | {stats['losses']:>6d} | ${stats['pnl']:>10,.0f}")

    print(f"\n  Analysis saved to: {output_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
