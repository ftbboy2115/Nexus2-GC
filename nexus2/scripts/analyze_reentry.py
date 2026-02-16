"""
Re-Entry Quality Gate Analysis Script

Analyzes all 14 test cases to determine conditions at re-entry time.
For each case, runs a sim step-by-step and captures:
- Trade 1 exit time and P&L
- Trade 2 entry time and conditions (VWAP, MACD, volume, % off HOD, time)
- Whether the re-entry was good or bad

Outputs a structured analysis for quality gate design.
"""

import json
import os
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, time as dt_time

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# ============================================================================
# CONFIGURATION
# ============================================================================

TEST_CASES_DIR = project_root / "nexus2" / "tests" / "test_cases" / "intraday"

# Cases and their classification
GOOD_REENTRY_CASES = {
    "batl_20260127": {"with": 2485, "without": -434, "delta": -2919},
    "vero_20260116": {"with": 966, "without": 121, "delta": -845},
    "rolr_20260114": {"with": 1539, "without": 820, "delta": -719},
    "tnmg_20260116": {"with": 215, "without": -12, "delta": -228},
    "evmn_20260210": {"with": 386, "without": 170, "delta": -216},
    "dcx_20260129": {"with": 327, "without": 118, "delta": -209},
    "bnai_20260205": {"with": 257, "without": 67, "delta": -190},
    "bnkk_20260115": {"with": 177, "without": 37, "delta": -140},
}

BAD_REENTRY_CASES = {
    "gwav_20260116": {"with": 216, "without": 631, "delta": 415},
    "mnts_20260209": {"with": -704, "without": -317, "delta": 388},
    "lrhc_20260130": {"with": -98, "without": 178, "delta": 276},
    "pavm_20260121": {"with": -146, "without": 27, "delta": 174},
    "mlec_20260213": {"with": -100, "without": 65, "delta": 166},
    "batl_20260126": {"with": -176, "without": 67, "delta": 243},
}


def compute_vwap(bars):
    """Compute VWAP from bars up to current point."""
    cum_vol = 0
    cum_tp_vol = 0
    for b in bars:
        tp = (b["h"] + b["l"] + b["c"]) / 3
        vol = b["v"]
        cum_vol += vol
        cum_tp_vol += tp * vol
    if cum_vol == 0:
        return 0
    return cum_tp_vol / cum_vol


def compute_ema(closes, period):
    """Compute EMA of closes."""
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def compute_macd(closes):
    """Compute MACD line and signal line."""
    if len(closes) < 26:
        return None, None, None
    
    # EMA 12
    k12 = 2 / 13
    ema12 = sum(closes[:12]) / 12
    for c in closes[12:]:
        ema12 = c * k12 + ema12 * (1 - k12)
    
    # EMA 26
    k26 = 2 / 27
    ema26 = sum(closes[:26]) / 26
    for c in closes[26:]:
        ema26 = c * k26 + ema26 * (1 - k26)
    
    # Actually compute full MACD series for signal
    ema12_series = []
    ema12_val = sum(closes[:12]) / 12
    for i, c in enumerate(closes):
        if i < 12:
            continue
        ema12_val = c * k12 + ema12_val * (1 - k12)
        ema12_series.append(ema12_val)
    
    ema26_series = []
    ema26_val = sum(closes[:26]) / 26
    for i, c in enumerate(closes):
        if i < 26:
            continue
        ema26_val = c * k26 + ema26_val * (1 - k26)
        ema26_series.append(ema26_val)
    
    # MACD line = EMA12 - EMA26 (aligned from bar 26 onward)
    macd_offset = 26 - 12  # 14 bars offset between ema12 and ema26 start
    macd_series = []
    for i, e26 in enumerate(ema26_series):
        e12 = ema12_series[i + macd_offset]
        macd_series.append(e12 - e26)
    
    if len(macd_series) < 9:
        return macd_series[-1] if macd_series else None, None, None
    
    # Signal = EMA 9 of MACD
    k9 = 2 / 10
    signal = sum(macd_series[:9]) / 9
    for m in macd_series[9:]:
        signal = m * k9 + signal * (1 - k9)
    
    macd_line = macd_series[-1]
    histogram = macd_line - signal
    
    return macd_line, signal, histogram


def get_hod_at_bar(bars, idx):
    """Get high of day up to (but not including) bar at idx."""
    hod = 0
    for b in bars[:idx]:
        if b["h"] > hod:
            hod = b["h"]
    return hod


def get_volume_trend(bars, idx, lookback=5):
    """Get average volume of recent bars vs overall average."""
    if idx < lookback:
        return 0, 0
    recent = [bars[i]["v"] for i in range(max(0, idx - lookback), idx)]
    overall = [b["v"] for b in bars[:idx]] if idx > 0 else [0]
    return sum(recent) / len(recent) if recent else 0, sum(overall) / len(overall) if overall else 0


def parse_time(t_str):
    """Parse time string like '07:10' or '09:30' to dt_time."""
    parts = t_str.split(":")
    return dt_time(int(parts[0]), int(parts[1]))


def is_market_hours(t):
    """Check if time is during regular market hours (9:30-16:00)."""
    return dt_time(9, 30) <= t <= dt_time(16, 0)


def analyze_case(case_id, json_path, classification):
    """
    Analyze a single test case for re-entry conditions.
    
    Since we can't easily run the full simulation in standalone mode,
    we analyze the raw bar data to find where trade events likely occur
    based on the PMH breakout and price action patterns.
    """
    with open(json_path) as f:
        data = json.load(f)
    
    symbol = data["symbol"]
    pmh = data["premarket"]["pmh"]
    gap_pct = data["premarket"]["gap_percent"]
    prev_close = data["premarket"]["previous_close"]
    
    # Get only trading day bars (not prev_day continuity)
    bars = data.get("bars", [])
    if not bars:
        return None
    
    # Find trading-day bars only
    market_bars = []
    all_day_bars = []
    for b in bars:
        if b.get("prev_day"):
            continue
        all_day_bars.append(b)
        t = parse_time(b["t"])
        if is_market_hours(t):
            market_bars.append(b)
    
    # Find HOD (high of day)
    overall_hod = max(b["h"] for b in all_day_bars) if all_day_bars else 0
    
    # Identify approximate entry/exit regions by finding large moves
    # We look for the PMH break area and where price action suggests entries
    
    result = {
        "case_id": case_id,
        "symbol": symbol,
        "pmh": pmh,
        "gap_pct": gap_pct,
        "prev_close": prev_close,
        "hod": overall_hod,
        "classification": classification,
        "total_bars": len(all_day_bars),
        "market_bars": len(market_bars),
    }
    
    # Analyze price action around the HOD
    # Key metrics at various time points
    if all_day_bars:
        # Find the HOD bar
        hod_bar_idx = max(range(len(all_day_bars)), key=lambda i: all_day_bars[i]["h"])
        hod_bar = all_day_bars[hod_bar_idx]
        result["hod_time"] = hod_bar["t"]
        result["hod_price"] = hod_bar["h"]
        
        # Volume at HOD
        result["hod_volume"] = hod_bar["v"]
        
        # Price at various stages after HOD
        bars_after_hod = all_day_bars[hod_bar_idx:]
        if len(bars_after_hod) > 5:
            result["price_5_bars_after_hod"] = bars_after_hod[5]["c"]
            result["pct_off_hod_after_5"] = (overall_hod - bars_after_hod[5]["c"]) / overall_hod * 100
        
        if len(bars_after_hod) > 10:
            result["price_10_bars_after_hod"] = bars_after_hod[10]["c"]
            result["pct_off_hod_after_10"] = (overall_hod - bars_after_hod[10]["c"]) / overall_hod * 100
        
        # Compute VWAP progression
        closes = [b["c"] for b in all_day_bars]
        
        # VWAP at midpoint
        mid_idx = len(all_day_bars) // 2
        vwap_mid = compute_vwap(all_day_bars[:mid_idx])
        result["vwap_at_midpoint"] = round(vwap_mid, 4) if vwap_mid else None
        result["price_at_midpoint"] = all_day_bars[mid_idx]["c"] if mid_idx < len(all_day_bars) else None
        
        # VWAP at 3/4 point  
        q3_idx = len(all_day_bars) * 3 // 4
        vwap_q3 = compute_vwap(all_day_bars[:q3_idx])
        result["vwap_at_q3"] = round(vwap_q3, 4) if vwap_q3 else None
        
        # Full VWAP
        vwap_full = compute_vwap(all_day_bars)
        result["vwap_full"] = round(vwap_full, 4) if vwap_full else None
        
        # MACD at various points
        if len(closes) >= 26:
            # MACD at midpoint
            macd_mid, sig_mid, hist_mid = compute_macd(closes[:mid_idx])
            result["macd_at_midpoint"] = round(macd_mid, 4) if macd_mid else None
            result["macd_hist_at_midpoint"] = round(hist_mid, 4) if hist_mid else None
            
            # MACD at 3/4
            macd_q3, sig_q3, hist_q3 = compute_macd(closes[:q3_idx])
            result["macd_at_q3"] = round(macd_q3, 4) if macd_q3 else None
            result["macd_hist_at_q3"] = round(hist_q3, 4) if hist_q3 else None
        
        # Volume trend analysis
        # Compare first 1/3 volume vs last 1/3 volume
        third = len(all_day_bars) // 3
        if third > 0:
            vol_first_third = sum(b["v"] for b in all_day_bars[:third]) / third
            vol_last_third = sum(b["v"] for b in all_day_bars[-third:]) / third
            result["vol_first_third_avg"] = int(vol_first_third)
            result["vol_last_third_avg"] = int(vol_last_third)
            result["vol_ratio_late_vs_early"] = round(vol_last_third / vol_first_third, 2) if vol_first_third > 0 else 0
        
        # Price trend after HOD: does it recover or fade?
        if hod_bar_idx < len(all_day_bars) - 1:
            last_close = all_day_bars[-1]["c"]
            result["final_close"] = last_close
            result["hod_to_close_pct"] = round((overall_hod - last_close) / overall_hod * 100, 2)
            
            # Find the lowest point after HOD
            lod_after_hod = min(b["l"] for b in all_day_bars[hod_bar_idx:])
            result["lod_after_hod"] = lod_after_hod
            result["max_drawdown_from_hod_pct"] = round((overall_hod - lod_after_hod) / overall_hod * 100, 2)
            
            # Does price recover above 50% of HOD-to-LOD range?
            recovery_level = (overall_hod + lod_after_hod) / 2
            recovers = any(b["h"] > recovery_level for b in all_day_bars[hod_bar_idx + 1:])
            result["recovers_above_midpoint"] = recovers
            
            # Count "higher highs" after HOD
            higher_high_count = 0
            prev_high = all_day_bars[hod_bar_idx + 1]["h"] if hod_bar_idx + 1 < len(all_day_bars) else 0
            for b in all_day_bars[hod_bar_idx + 2:]:
                if b["h"] > prev_high:
                    higher_high_count += 1
                prev_high = b["h"]
            result["higher_highs_after_hod"] = higher_high_count
            
            # How quickly does HOD form? (bar # of HOD / total bars)
            result["hod_timing_ratio"] = round(hod_bar_idx / len(all_day_bars), 2)
    
    return result


def main():
    results = []
    
    # Process all GOOD re-entry cases
    for case_key, metrics in GOOD_REENTRY_CASES.items():
        json_file = TEST_CASES_DIR / f"ross_{case_key}.json"
        if json_file.exists():
            result = analyze_case(case_key, json_file, "GOOD")
            if result:
                result.update(metrics)
                results.append(result)
        else:
            print(f"WARNING: Missing {json_file}")
    
    # Process all BAD re-entry cases
    for case_key, metrics in BAD_REENTRY_CASES.items():
        json_file = TEST_CASES_DIR / f"ross_{case_key}.json"
        if json_file.exists():
            result = analyze_case(case_key, json_file, "BAD")
            if result:
                result.update(metrics)
                results.append(result)
        else:
            print(f"WARNING: Missing {json_file}")
    
    # Print summary
    print("=" * 120)
    print("RE-ENTRY QUALITY GATE ANALYSIS")
    print("=" * 120)
    
    # Group by classification
    good_results = [r for r in results if r["classification"] == "GOOD"]
    bad_results = [r for r in results if r["classification"] == "BAD"]
    
    # Print detailed per-case analysis
    for label, group in [("GOOD RE-ENTRIES (Keep)", good_results), ("BAD RE-ENTRIES (Block)", bad_results)]:
        print(f"\n{'=' * 80}")
        print(f"  {label}")
        print(f"{'=' * 80}")
        
        for r in group:
            print(f"\n--- {r['symbol']} ({r['case_id']}) ---")
            print(f"  With re-entry: ${r['with']:,}  |  Without: ${r['without']:,}  |  Delta: ${r['delta']:+,}")
            print(f"  Gap: {r['gap_pct']:.1f}%  |  PMH: ${r['pmh']}  |  HOD: ${r.get('hod', 'N/A')}")
            print(f"  HOD time: {r.get('hod_time', 'N/A')}  |  HOD timing: {r.get('hod_timing_ratio', 'N/A')}")
            print(f"  Final close: ${r.get('final_close', 'N/A')}")
            print(f"  HOD-to-close: {r.get('hod_to_close_pct', 'N/A')}%")
            print(f"  Max drawdown from HOD: {r.get('max_drawdown_from_hod_pct', 'N/A')}%")
            print(f"  Recovers above midpoint: {r.get('recovers_above_midpoint', 'N/A')}")
            print(f"  Higher highs after HOD: {r.get('higher_highs_after_hod', 'N/A')}")
            print(f"  VWAP (full): ${r.get('vwap_full', 'N/A')}")
            print(f"  MACD hist @ mid: {r.get('macd_hist_at_midpoint', 'N/A')}")
            print(f"  MACD hist @ Q3: {r.get('macd_hist_at_q3', 'N/A')}")
            print(f"  Vol early/late avg: {r.get('vol_first_third_avg', 'N/A')}/{r.get('vol_last_third_avg', 'N/A')}")
            print(f"  Vol ratio (late/early): {r.get('vol_ratio_late_vs_early', 'N/A')}x")
    
    # Discriminating features analysis
    print(f"\n\n{'=' * 80}")
    print("  DISCRIMINATING FEATURES ANALYSIS")
    print(f"{'=' * 80}")
    
    # Compare averages
    metrics_to_compare = [
        ("hod_to_close_pct", "HOD-to-Close %"),
        ("max_drawdown_from_hod_pct", "Max Drawdown from HOD %"),
        ("hod_timing_ratio", "HOD Timing (0=early, 1=late)"),
        ("vol_ratio_late_vs_early", "Vol Ratio (Late/Early)"),
    ]
    
    print(f"\n{'Metric':<35} {'GOOD Avg':>12} {'BAD Avg':>12} {'SEPARABLE?':>12}")
    print("-" * 75)
    
    for key, label in metrics_to_compare:
        good_vals = [r[key] for r in good_results if key in r and r[key] is not None]
        bad_vals = [r[key] for r in bad_results if key in r and r[key] is not None]
        
        good_avg = sum(good_vals) / len(good_vals) if good_vals else 0
        bad_avg = sum(bad_vals) / len(bad_vals) if bad_vals else 0
        
        separable = "YES" if abs(good_avg - bad_avg) > max(abs(good_avg), abs(bad_avg)) * 0.2 else "MAYBE"
        print(f"{label:<35} {good_avg:>12.2f} {bad_avg:>12.2f} {separable:>12}")
    
    # MACD analysis
    print(f"\n{'Metric':<35} {'GOOD Avg':>12} {'BAD Avg':>12} {'SEPARABLE?':>12}")
    print("-" * 75)
    for key, label in [("macd_hist_at_midpoint", "MACD Hist @ Midpoint"), ("macd_hist_at_q3", "MACD Hist @ Q3")]:
        good_vals = [r[key] for r in good_results if key in r and r[key] is not None]
        bad_vals = [r[key] for r in bad_results if key in r and r[key] is not None]
        good_avg = sum(good_vals) / len(good_vals) if good_vals else 0
        bad_avg = sum(bad_vals) / len(bad_vals) if bad_vals else 0
        separable = "YES" if (good_avg > 0 and bad_avg < 0) or (good_avg > 0 and bad_avg < good_avg * 0.5) else "MAYBE"
        print(f"{label:<35} {good_avg:>12.4f} {bad_avg:>12.4f} {separable:>12}")
    
    # Recovery analysis
    print(f"\n--- Recovery Analysis ---")
    good_recovers = sum(1 for r in good_results if r.get("recovers_above_midpoint"))
    bad_recovers = sum(1 for r in bad_results if r.get("recovers_above_midpoint"))
    print(f"  GOOD cases that recover above midpoint: {good_recovers}/{len(good_results)} ({good_recovers/len(good_results)*100:.0f}%)")
    print(f"  BAD cases that recover above midpoint:  {bad_recovers}/{len(bad_results)} ({bad_recovers/len(bad_results)*100:.0f}%)")
    
    # Higher highs analysis
    print(f"\n--- Higher Highs After HOD ---")
    good_hh = [r.get("higher_highs_after_hod", 0) for r in good_results]
    bad_hh = [r.get("higher_highs_after_hod", 0) for r in bad_results]
    print(f"  GOOD avg: {sum(good_hh)/len(good_hh):.1f}")
    print(f"  BAD avg:  {sum(bad_hh)/len(bad_hh):.1f}")
    
    # Output JSON for downstream use
    output_path = project_root / "nexus2" / "reports" / "2026-02-15" / "reentry_analysis_data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nData saved to: {output_path}")


if __name__ == "__main__":
    main()
