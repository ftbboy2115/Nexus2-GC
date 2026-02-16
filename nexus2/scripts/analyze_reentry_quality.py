"""
Analyze what distinguishes GOOD re-entries from BAD re-entries.
For each re-entry, capture the context:
- Is the stock making new HODs? (higher highs)
- Is the entry price above or below the first entry?
- What's the P&L from the first entry at the time of re-entry?
- How much time has elapsed since the first entry?
- Is price above VWAP?
"""
import asyncio
import io
import json
import sys
import os
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import logging

def _strip_file_handlers():
    """Remove ALL file handlers from ALL loggers to avoid Windows lock conflicts."""
    for name in list(logging.Logger.manager.loggerDict.keys()) + ['']:
        logger = logging.getLogger(name)
        for h in logger.handlers[:]:
            if isinstance(h, logging.FileHandler):
                logger.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass

# Suppress most logging and strip any file handlers set up during import
logging.disable(logging.WARNING)
_strip_file_handlers()


async def run_case_detailed(case_id: str, case: dict, yaml_data: dict) -> dict:
    """Run a case and capture detailed context for each entry."""
    from nexus2.adapters.simulation.sim_context import (
        SimContext, load_case_into_context, step_clock_ctx
    )
    from nexus2.adapters.simulation.sim_clock import set_simulation_clock_ctx
    from nexus2.domain.automation.trade_event_service import set_sim_mode_ctx

    _strip_file_handlers()  # Clean up file handlers added by module imports

    try:
        from nexus2.db.warrior_db import purge_sim_trades
        purge_sim_trades(confirm=True)
    except Exception:
        pass

    symbol = case.get("symbol", "")
    
    ctx = SimContext.create(case_id)
    set_simulation_clock_ctx(ctx.clock)
    set_sim_mode_ctx(True)
    
    bar_count = load_case_into_context(ctx, case, yaml_data)
    if bar_count == 0:
        return {"case_id": case_id, "symbol": symbol, "entries": [], "pnl": 0}
    
    # Capture bar data for context analysis
    bars_by_time = {}
    all_bars = ctx.broker._bars if hasattr(ctx.broker, '_bars') else []
    
    await step_clock_ctx(ctx, 960)
    
    # Force close
    for pos in ctx.broker.get_positions():
        qty = pos.get("qty", 0)
        if qty > 0:
            ctx.broker.sell_position(pos.get("symbol"), qty)
    
    account = ctx.broker.get_account()
    orders = ctx.broker.get_orders()
    
    buy_orders = [o for o in orders if o.get("side") == "buy" and o.get("status") == "filled"]
    sell_orders = [o for o in orders if o.get("side") == "sell" and o.get("status") == "filled"]
    
    pnl = round(account.get("realized_pnl", 0) + account.get("unrealized_pnl", 0), 2)
    
    # Build detailed entry info
    entries = []
    first_entry_price = None
    first_entry_time = None
    cumulative_shares = 0
    
    for i, o in enumerate(buy_orders):
        entry_price = o.get("avg_fill_price", 0)
        entry_time = o.get("sim_time", "")
        entry_shares = o.get("filled_qty", 0)
        trigger = o.get("entry_trigger", "")
        
        # Is this a scale (same time as previous) or a re-entry?
        is_scale = (i > 0 and entry_time == buy_orders[i-1].get("sim_time", "") and trigger is None)
        
        if first_entry_price is None and trigger:  # First real entry (not a scale)
            first_entry_price = entry_price
            first_entry_time = entry_time
        
        cumulative_shares += entry_shares
        
        # Time gap from first entry
        time_gap_mins = 0
        if first_entry_time and entry_time and first_entry_time != entry_time:
            try:
                fh, fm = map(int, str(first_entry_time).split(":"))
                eh, em = map(int, str(entry_time).split(":"))
                time_gap_mins = (eh * 60 + em) - (fh * 60 + fm)
            except:
                pass
        
        # Price relative to first entry
        price_vs_first = None
        if first_entry_price and first_entry_price > 0:
            price_vs_first = round((entry_price - first_entry_price) / first_entry_price * 100, 1)
        
        entries.append({
            "num": i + 1,
            "time": entry_time,
            "price": entry_price,
            "shares": entry_shares,
            "trigger": trigger,
            "is_scale": is_scale,
            "cumulative_shares": cumulative_shares,
            "time_gap_mins": time_gap_mins,
            "price_vs_first_pct": price_vs_first,
            "price_vs_first_dir": "ABOVE" if (price_vs_first and price_vs_first > 1) else "BELOW" if (price_vs_first and price_vs_first < -1) else "NEAR",
        })
    
    return {
        "case_id": case_id,
        "symbol": symbol,
        "pnl": pnl,
        "ross_pnl": case.get("ross_pnl", 0) or 0,
        "outcome": case.get("outcome", ""),
        "entry_count": len([e for e in entries if not e["is_scale"]]),
        "scale_count": len([e for e in entries if e["is_scale"]]),
        "entries": entries,
    }


async def main():
    from sqlalchemy import create_engine as _ce
    from sqlalchemy.orm import sessionmaker as _sm
    import nexus2.db.warrior_db as wdb
    
    mem = _ce("sqlite://", connect_args={"check_same_thread": False})
    wdb.warrior_engine = mem
    wdb.WarriorSessionLocal = _sm(autocommit=False, autoflush=False, bind=mem)
    wdb.WarriorBase.metadata.create_all(bind=mem)
    
    yaml_path = os.path.join(
        os.path.dirname(__file__), "..", "tests", "test_cases", "warrior_setups.yaml"
    )
    with open(yaml_path, "r", encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f)
    
    all_cases = yaml_data.get("test_cases", [])
    ross_cases = [c for c in all_cases if c.get("id", "").startswith("ross_")]
    
    # Only cases with re-entries (>2 buy orders = entry + scale + re-entry)
    results = []
    for case in ross_cases:
        # Suppress print noise from sim engine
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            r = await run_case_detailed(case["id"], case, yaml_data)
            results.append(r)
        except Exception as e:
            pass
        finally:
            sys.stdout = old_stdout
    
    # Filter to cases with actual re-entries (not just scales)
    reentry_cases = [r for r in results if r.get("entry_count", 0) > 1]
    single_entry_cases = [r for r in results if r.get("entry_count", 0) == 1]
    no_entry_cases = [r for r in results if r.get("entry_count", 0) == 0]
    
    print(f"{'='*120}")
    print(f"RE-ENTRY QUALITY ANALYSIS")
    print(f"{'='*120}")
    print(f"\nTotal cases: {len(results)}")
    print(f"  No entry: {len(no_entry_cases)}")
    print(f"  Single entry (+ scales): {len(single_entry_cases)}")
    print(f"  Multiple entries (re-entries): {len(reentry_cases)}")
    
    # === DETAILED RE-ENTRY ANALYSIS ===
    print(f"\n{'='*120}")
    print(f"CASES WITH RE-ENTRIES")
    print(f"{'='*120}")
    
    for r in sorted(reentry_cases, key=lambda x: x["pnl"]):
        pnl_sign = "+" if r["pnl"] >= 0 else ""
        quality = "✅ WINNER" if r["pnl"] > 0 else "❌ LOSER"
        
        print(f"\n{'─'*80}")
        print(f"{r['symbol']} ({r['case_id']}) — {quality} | Bot: {pnl_sign}${r['pnl']:,.2f} | Ross: ${r['ross_pnl']:+,.2f}")
        print(f"{'─'*80}")
        
        real_entries = [e for e in r["entries"] if not e["is_scale"]]
        
        print(f"  {'#':>3} {'Time':<8} {'Price':>8} {'Shares':>7} {'Trigger':<28} {'Gap':>6} {'vs Entry1':>12} {'Dir':<6}")
        print(f"  {'-'*90}")
        
        for e in r["entries"]:
            marker = "  " if not e["is_scale"] else "  ↳"
            trigger_str = str(e["trigger"] or "(scale)") 
            gap_str = f"{e['time_gap_mins']}m" if e["time_gap_mins"] > 0 else ""
            vs_first = f"{e['price_vs_first_pct']:+.1f}%" if e["price_vs_first_pct"] is not None else ""
            
            print(f"{marker}{e['num']:>2} {e['time']:<8} ${e['price']:>7.2f} {e['shares']:>7} {trigger_str:<28} {gap_str:>6} {vs_first:>12} {e['price_vs_first_dir']:<6}")
    
    # === CLASSIFICATION ===
    print(f"\n{'='*120}")
    print(f"RE-ENTRY CLASSIFICATION: GOOD vs BAD")
    print(f"{'='*120}\n")
    
    print(f"{'Case':<30} {'P&L':>10} {'Re-entries':>10} {'Price Dir':>10} {'Time Gap':>10} {'Quality':>10}")
    print(f"{'-'*90}")
    
    for r in sorted(reentry_cases, key=lambda x: x["pnl"]):
        real_reentries = [e for e in r["entries"] if not e["is_scale"] and e["time_gap_mins"] > 0]
        if not real_reentries:
            continue
            
        avg_price_dir = sum(e["price_vs_first_pct"] or 0 for e in real_reentries) / len(real_reentries)
        max_gap = max(e["time_gap_mins"] for e in real_reentries)
        price_dir_str = f"{avg_price_dir:+.1f}%"
        gap_str = f"{max_gap}m"
        quality = "✅ GOOD" if r["pnl"] > 0 else "❌ BAD"
        
        pnl_sign = "+" if r["pnl"] >= 0 else ""
        print(f"{r['case_id']:<30} {pnl_sign}${r['pnl']:>9,.2f} {len(real_reentries):>10} {price_dir_str:>10} {gap_str:>10} {quality:>10}")
    
    # === KEY PATTERNS ===
    print(f"\n{'='*120}")
    print(f"KEY PATTERNS")
    print(f"{'='*120}\n")
    
    good_reentries = []
    bad_reentries = []
    
    for r in reentry_cases:
        real_reentries = [e for e in r["entries"] if not e["is_scale"] and e["time_gap_mins"] > 0]
        for e in real_reentries:
            entry_data = {**e, "case": r["case_id"], "case_pnl": r["pnl"], "symbol": r["symbol"]}
            if r["pnl"] > 0:
                good_reentries.append(entry_data)
            else:
                bad_reentries.append(entry_data)
    
    print(f"GOOD re-entries ({len(good_reentries)}):")
    for e in sorted(good_reentries, key=lambda x: x["time_gap_mins"]):
        print(f"  {e['symbol']:>6} @ {e['time']:<6} | gap={e['time_gap_mins']:>4}m | price {e['price_vs_first_dir']:<6} ({e['price_vs_first_pct']:+.1f}%) | trigger={e['trigger']}")
    
    print(f"\nBAD re-entries ({len(bad_reentries)}):")
    for e in sorted(bad_reentries, key=lambda x: x["time_gap_mins"]):
        print(f"  {e['symbol']:>6} @ {e['time']:<6} | gap={e['time_gap_mins']:>4}m | price {e['price_vs_first_dir']:<6} ({e['price_vs_first_pct']:+.1f}%) | trigger={e['trigger']}")
    
    # === PROPOSED FILTERS ===
    print(f"\n{'='*120}")
    print(f"PROPOSED FILTER ANALYSIS")
    print(f"{'='*120}\n")
    
    filters = [
        ("Re-entry price ABOVE first entry", lambda e: (e["price_vs_first_pct"] or 0) > 0),
        ("Re-entry price BELOW first entry", lambda e: (e["price_vs_first_pct"] or 0) < 0),
        ("Time gap > 120 min", lambda e: e["time_gap_mins"] > 120),
        ("Time gap > 180 min", lambda e: e["time_gap_mins"] > 180),
        ("Time gap > 60 min AND price below", lambda e: e["time_gap_mins"] > 60 and (e["price_vs_first_pct"] or 0) < -5),
        ("Price > 50% above first entry (new trend)", lambda e: (e["price_vs_first_pct"] or 0) > 50),
    ]
    
    for name, fn in filters:
        good_match = [e for e in good_reentries if fn(e)]
        bad_match = [e for e in bad_reentries if fn(e)]
        good_block = [e for e in good_reentries if not fn(e)]
        bad_block = [e for e in bad_reentries if not fn(e)]
        
        print(f"Filter: {name}")
        print(f"  Would BLOCK: {len(good_match)} good + {len(bad_match)} bad")
        if bad_match:
            bad_str = ", ".join(f"{e['symbol']} ({e['time']})" for e in bad_match)
            print(f"  Bad blocked:  {bad_str}")
        if good_match:
            good_str = ", ".join(f"{e['symbol']} ({e['time']})" for e in good_match)
            print(f"  Good blocked: {good_str}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
