"""
Guard A/B Analysis — Full pipeline:
1. Run guards-OFF batch (guards-ON already saved)
2. Compare per-case P&L
3. Extract per-guard analysis
"""
import json
import os
import time
import urllib.request

API = "http://127.0.0.1:8000"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "nexus2", "reports", "2026-02-24")
ON_FILE = os.path.join(OUT_DIR, "batch_guards_on.json")
OFF_FILE = os.path.join(OUT_DIR, "batch_guards_off.json")


def run_guards_off():
    """Run batch with guards OFF and save."""
    body = json.dumps({"include_trades": True, "skip_guards": True}).encode()
    req = urllib.request.Request(
        f"{API}/warrior/sim/run_batch_concurrent",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print("Running batch with guards OFF... (timeout 600s)")
    start = time.time()
    resp = urllib.request.urlopen(req, timeout=600)
    data = json.loads(resp.read().decode())
    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s")
    with open(OFF_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Saved: {OFF_FILE}")
    return data


def analyze():
    """Analyze both results."""
    on_data = json.load(open(ON_FILE))
    off_data = json.load(open(OFF_FILE))

    on_results = on_data["results"]
    off_results = off_data["results"]

    # Totals
    on_total = sum(r.get("total_pnl", 0) or 0 for r in on_results)
    off_total = sum(r.get("total_pnl", 0) or 0 for r in off_results)
    ross_total = sum(r.get("ross_pnl", 0) or 0 for r in on_results)

    print("\n" + "=" * 70)
    print("A/B GUARD COMPARISON SUMMARY")
    print("=" * 70)
    print(f"  {'Metric':<20} {'Guards ON':>14} {'Guards OFF':>14} {'Delta':>12}")
    print(f"  {'-'*60}")
    print(f"  {'Bot P&L':<20} {'${:,.0f}'.format(on_total):>14} {'${:,.0f}'.format(off_total):>14} {'${:+,.0f}'.format(off_total - on_total):>12}")
    print(f"  {'Ross P&L':<20} {'${:,.0f}'.format(ross_total):>14} {'${:,.0f}'.format(ross_total):>14} {'(same)':>12}")
    cap_on = on_total / ross_total * 100 if ross_total else 0
    cap_off = off_total / ross_total * 100 if ross_total else 0
    print(f"  {'Capture':<20} {'{:.1f}%'.format(cap_on):>14} {'{:.1f}%'.format(cap_off):>14} {'{:+.1f}%'.format(cap_off - cap_on):>12}")

    # Per-case comparison
    on_map = {r["case_id"]: r for r in on_results}
    off_map = {r["case_id"]: r for r in off_results}
    all_ids = sorted(set(list(on_map.keys()) + list(off_map.keys())))

    deltas = []
    for cid in all_ids:
        on_pnl = on_map.get(cid, {}).get("total_pnl", 0) or 0
        off_pnl = off_map.get(cid, {}).get("total_pnl", 0) or 0
        ross_pnl = on_map.get(cid, {}).get("ross_pnl", 0) or 0
        delta = off_pnl - on_pnl
        guards = on_map.get(cid, {}).get("guard_block_count", 0) or 0
        impact = "HURT" if delta > 50 else ("HELP" if delta < -50 else "~")
        deltas.append((cid, on_pnl, off_pnl, delta, ross_pnl, guards, impact))

    deltas.sort(key=lambda x: -x[3])

    print(f"\n{'=' * 100}")
    print(f"PER-CASE COMPARISON (sorted by guard impact, positive = guards HURT)")
    print(f"{'=' * 100}")
    print(f"  {'Case':<30} {'ON':>10} {'OFF':>10} {'Delta':>10} {'Ross':>10} {'Blocks':>7} {'Impact':>6}")
    print(f"  {'-'*90}")

    for cid, on_pnl, off_pnl, delta, ross_pnl, guards, impact in deltas:
        marker = " <<" if abs(delta) > 1000 else ""
        print(f"  {cid:<30} {on_pnl:>10,.0f} {off_pnl:>10,.0f} {delta:>+10,.0f} {ross_pnl:>10,.0f} {guards:>7} {impact:>6}{marker}")

    net = off_total - on_total
    hurt_count = sum(1 for d in deltas if d[6] == "HURT")
    help_count = sum(1 for d in deltas if d[6] == "HELP")
    neutral = sum(1 for d in deltas if d[6] == "~")
    print(f"  {'-'*90}")
    print(f"  {'TOTAL':<30} {on_total:>10,.0f} {off_total:>10,.0f} {net:>+10,.0f} {ross_total:>10,.0f}")
    print(f"\n  Guards HURT: {hurt_count}  |  Guards HELP: {help_count}  |  Neutral: {neutral}")

    # Guard-type breakdown
    print(f"\n{'=' * 90}")
    print(f"PER-GUARD-TYPE ANALYSIS (counterfactual from guards-ON run)")
    print(f"{'=' * 90}")

    guard_totals = {}
    for r in on_results:
        ga = r.get("guard_analysis")
        if not ga:
            continue
        by_type = ga.get("by_guard_type", {})
        for gtype, info in by_type.items():
            if gtype not in guard_totals:
                guard_totals[gtype] = {"blocks": 0, "correct": 0, "missed": 0, "net_impact": 0.0, "cases": 0}
            blocks = info.get("blocks", 0) or 0
            accuracy = info.get("accuracy", 0) or 0
            correct = int(blocks * accuracy)
            missed = blocks - correct
            net_impact = info.get("net_impact", 0) or 0
            guard_totals[gtype]["blocks"] += blocks
            guard_totals[gtype]["correct"] += correct
            guard_totals[gtype]["missed"] += missed
            guard_totals[gtype]["net_impact"] += net_impact
            if blocks > 0:
                guard_totals[gtype]["cases"] += 1

    if guard_totals:
        print(f"  {'Guard Type':<20} {'Blocks':>8} {'Correct':>8} {'Missed':>8} {'Accuracy':>10} {'Net $':>12} {'Cases':>6}")
        print(f"  {'-'*80}")
        sorted_guards = sorted(guard_totals.items(), key=lambda x: x[1]["net_impact"])
        for gtype, info in sorted_guards:
            total = info["blocks"]
            correct = info["correct"]
            missed = info["missed"]
            acc = (correct / total * 100) if total else 0
            ni = info["net_impact"]
            cases = info["cases"]
            print(f"  {gtype:<20} {total:>8} {correct:>8} {missed:>8} {acc:>9.1f}% {ni:>+11,.0f} {cases:>6}")

        tb = sum(v["blocks"] for v in guard_totals.values())
        tc = sum(v["correct"] for v in guard_totals.values())
        tm = sum(v["missed"] for v in guard_totals.values())
        tni = sum(v["net_impact"] for v in guard_totals.values())
        oa = (tc / tb * 100) if tb else 0
        print(f"  {'-'*80}")
        print(f"  {'TOTAL':<20} {tb:>8} {tc:>8} {tm:>8} {oa:>9.1f}% {tni:>+11,.0f}")
    else:
        print("  (No guard_analysis data found in guards-ON results)")

    # Per-case guard details for top impacted cases
    print(f"\n{'=' * 90}")
    print(f"GUARD DETAIL FOR TOP 5 HURT CASES")
    print(f"{'=' * 90}")
    top_hurt = [d for d in deltas if d[6] == "HURT"][:5]
    for cid, on_pnl, off_pnl, delta, ross_pnl, guards, impact in top_hurt:
        print(f"\n  {cid}: ON={on_pnl:+,.0f}  OFF={off_pnl:+,.0f}  Delta={delta:+,.0f}  Guards={guards}")
        ga = on_map.get(cid, {}).get("guard_analysis")
        if ga:
            by_type = ga.get("by_guard_type", {})
            for gtype, info in sorted(by_type.items(), key=lambda x: x[1].get("blocks", 0), reverse=True):
                blocks = info.get("blocks", 0) or 0
                acc = info.get("accuracy", 0) or 0
                ni = info.get("net_impact", 0) or 0
                print(f"    {gtype:<18} blocks={blocks:>5}  accuracy={acc*100:>5.1f}%  net_impact={ni:>+,.0f}")

    # Save full analysis
    analysis = {
        "summary": {
            "guards_on_pnl": on_total,
            "guards_off_pnl": off_total,
            "delta": off_total - on_total,
            "ross_total": ross_total,
            "capture_on": cap_on,
            "capture_off": cap_off,
        },
        "per_case": [
            {"case_id": d[0], "on_pnl": d[1], "off_pnl": d[2], "delta": d[3], "ross_pnl": d[4], "guard_blocks": d[5], "impact": d[6]}
            for d in deltas
        ],
        "guard_breakdown": guard_totals,
    }
    analysis_file = os.path.join(OUT_DIR, "guard_ab_analysis.json")
    with open(analysis_file, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\nSaved analysis: {analysis_file}")


if __name__ == "__main__":
    # Step 1: Run guards-OFF if not already done
    if not os.path.exists(OFF_FILE):
        run_guards_off()
    else:
        print(f"Guards-OFF results already exist: {OFF_FILE}")
        resp = input("Re-run? (y/N): ").strip().lower()
        if resp == "y":
            run_guards_off()

    # Step 2: Analyze
    analyze()
