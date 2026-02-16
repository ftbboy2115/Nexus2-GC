"""
Analyze entry times across ALL test cases to evaluate time cutoff impact.
Uses SimContext directly to capture sim_time on each order.
"""
import asyncio
import json
import sys
import os
import time
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Suppress file logging to avoid lock conflict with running uvicorn
import logging
logging.disable(logging.WARNING)  # Only allow ERROR+
for handler in logging.root.handlers[:]:
    if isinstance(handler, logging.FileHandler):
        logging.root.removeHandler(handler)


async def run_case(case_id: str, case: dict, yaml_data: dict) -> dict:
    """Run a single case and return entry/exit timing data."""
    from nexus2.adapters.simulation.sim_context import (
        SimContext, load_case_into_context, step_clock_ctx
    )
    from nexus2.adapters.simulation.sim_clock import set_simulation_clock_ctx
    from nexus2.domain.automation.trade_event_service import set_sim_mode_ctx

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
    
    await step_clock_ctx(ctx, 960)
    
    # Force close open positions
    for pos in ctx.broker.get_positions():
        qty = pos.get("qty", 0)
        if qty > 0:
            ctx.broker.sell_position(pos.get("symbol"), qty)
    
    account = ctx.broker.get_account()
    orders = ctx.broker.get_orders()
    
    buy_orders = [o for o in orders if o.get("side") == "buy" and o.get("status") == "filled"]
    sell_orders = [o for o in orders if o.get("side") == "sell" and o.get("status") == "filled"]
    
    pnl = round(account.get("realized_pnl", 0) + account.get("unrealized_pnl", 0), 2)
    
    return {
        "case_id": case_id,
        "symbol": symbol,
        "pnl": pnl,
        "ross_pnl": case.get("ross_pnl", 0) or 0,
        "entries": [
            {
                "time": o.get("sim_time", ""),
                "price": o.get("avg_fill_price", 0),
                "shares": o.get("filled_qty", 0),
                "trigger": o.get("entry_trigger", ""),
            }
            for o in buy_orders
        ],
        "exits": [
            {
                "time": o.get("sim_time", ""),
                "price": o.get("avg_fill_price", 0),
                "shares": o.get("filled_qty", 0),
            }
            for o in sell_orders
        ],
    }


async def main():
    # In-memory DB setup
    from sqlalchemy import create_engine as _ce
    from sqlalchemy.orm import sessionmaker as _sm
    import nexus2.db.warrior_db as wdb
    
    mem = _ce("sqlite://", connect_args={"check_same_thread": False})
    wdb.warrior_engine = mem
    wdb.WarriorSessionLocal = _sm(autocommit=False, autoflush=False, bind=mem)
    wdb.WarriorBase.metadata.create_all(bind=mem)
    
    # Load YAML
    yaml_path = os.path.join(
        os.path.dirname(__file__), "..", "tests", "test_cases", "warrior_setups.yaml"
    )
    with open(yaml_path, "r", encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f)
    
    all_cases = yaml_data.get("test_cases", [])
    ross_cases = [c for c in all_cases if c.get("id", "").startswith("ross_")]
    
    print(f"Running {len(ross_cases)} Ross test cases...\n")
    
    results = []
    for case in ross_cases:
        case_id = case["id"]
        try:
            r = await run_case(case_id, case, yaml_data)
            results.append(r)
            entry_ct = len(r["entries"])
            pnl = r["pnl"]
            times = [e["time"] for e in r["entries"]]
            time_str = ", ".join(times) if times else "NO ENTRY"
            sign = "+" if pnl >= 0 else ""
            print(f"  {case_id:<30} {sign}${pnl:>10,.2f}  entries={entry_ct}  times=[{time_str}]")
        except Exception as e:
            print(f"  {case_id:<30} ERROR: {e}")
    
    # === CUTOFF ANALYSIS ===
    print(f"\n{'='*100}")
    print("ENTRY TIME CUTOFF ANALYSIS")
    print(f"{'='*100}\n")
    
    # Collect all entries
    all_entries = []
    for r in results:
        for i, e in enumerate(r["entries"]):
            all_entries.append({
                "case": r["case_id"],
                "symbol": r["symbol"],
                "entry_num": i + 1,
                "total_entries": len(r["entries"]),
                "time": e["time"],
                "price": e["price"],
                "shares": e["shares"],
                "trigger": e["trigger"],
                "case_pnl": r["pnl"],
                "ross_pnl": r["ross_pnl"],
            })
    
    # Sort by time and print ALL entries
    print(f"{'Case':<30} {'#':>2}/{'':<2} {'Time':<8} {'Trigger':<30} {'Shares':>7} {'Price':>8} {'Case P&L':>10}")
    print("-" * 100)
    for e in sorted(all_entries, key=lambda x: x["time"]):
        sign = "+" if e["case_pnl"] >= 0 else ""
        print(f"{e['case']:<30} {e['entry_num']:>2}/{e['total_entries']:<2} {e['time']:<8} {str(e['trigger']):<30} {e['shares']:>7} ${e['price']:>7.2f} {sign}${e['case_pnl']:>9,.2f}")
    
    # Parse time helper
    def parse_minutes(time_str):
        """Convert HH:MM to minutes since midnight."""
        try:
            parts = str(time_str).split(":")
            return int(parts[0]) * 60 + int(parts[1])
        except:
            return 0
    
    # Analyze cutoffs
    cutoffs = [
        ("08:00", 480),
        ("08:30", 510),
        ("09:00", 540),
        ("09:30", 570),
        ("10:00", 600),
        ("10:30", 630),
        ("11:00", 660),
        ("12:00", 720),
        ("13:00", 780),
        ("14:00", 840),
        ("No cutoff", 9999),
    ]
    
    # Current total P&L
    current_total = sum(r["pnl"] for r in results)
    
    print(f"\n{'='*100}")
    print(f"CURRENT TOTAL P&L: ${current_total:+,.2f}")
    print(f"{'='*100}\n")
    
    print(f"{'Cutoff':<12} {'Entries Blocked':>15} {'Cases Fully Blocked':>20} {'Saved (losses)':>15} {'Lost (profits)':>16} {'Net Impact':>12}")
    print("-" * 95)
    
    for label, cutoff_min in cutoffs:
        blocked_entries = [e for e in all_entries if parse_minutes(e["time"]) >= cutoff_min]
        allowed_entries = [e for e in all_entries if parse_minutes(e["time"]) < cutoff_min]
        
        # Cases where ALL entries are blocked
        blocked_case_ids = set(e["case"] for e in blocked_entries)
        allowed_case_ids = set(e["case"] for e in allowed_entries)
        fully_blocked = blocked_case_ids - allowed_case_ids
        partially_blocked = blocked_case_ids & allowed_case_ids
        
        # For fully blocked cases: we save losses, lose profits
        saved = 0
        lost = 0
        for case_id in fully_blocked:
            pnl = next((r["pnl"] for r in results if r["case_id"] == case_id), 0)
            if pnl < 0:
                saved += abs(pnl)
            else:
                lost += pnl
        
        net = saved - lost
        
        print(f"{label:<12} {len(blocked_entries):>15} {len(fully_blocked):>20} {f'${saved:,.2f}':>15} {f'-${lost:,.2f}':>16} {f'${net:+,.2f}':>12}")
    
    # Detail for key cutoffs
    for label, cutoff_min in [("10:00", 600), ("11:00", 660), ("12:00", 720)]:
        blocked_entries = [e for e in all_entries if parse_minutes(e["time"]) >= cutoff_min]
        allowed_entries = [e for e in all_entries if parse_minutes(e["time"]) < cutoff_min]
        
        blocked_case_ids = set(e["case"] for e in blocked_entries)
        allowed_case_ids = set(e["case"] for e in allowed_entries)
        fully_blocked = blocked_case_ids - allowed_case_ids
        partially_blocked = blocked_case_ids & allowed_case_ids
        
        print(f"\n--- Detail: {label} cutoff ---")
        
        if fully_blocked:
            print(f"  Fully blocked (no entry at all):")
            for cid in sorted(fully_blocked):
                pnl = next((r["pnl"] for r in results if r["case_id"] == cid), 0)
                impact = "SAVES" if pnl < 0 else "LOSES"
                print(f"    {cid:<30} ${pnl:+,.2f}  ({impact})")
        
        if partially_blocked:
            print(f"  Partially blocked (some re-entries blocked):")
            for cid in sorted(partially_blocked):
                pnl = next((r["pnl"] for r in results if r["case_id"] == cid), 0)
                num_blocked = sum(1 for e in blocked_entries if e["case"] == cid)
                num_total = sum(1 for e in all_entries if e["case"] == cid)
                blocked_times = [e["time"] for e in blocked_entries if e["case"] == cid]
                print(f"    {cid:<30} ${pnl:+,.2f}  ({num_blocked}/{num_total} entries blocked: {blocked_times})")


if __name__ == "__main__":
    asyncio.run(main())
