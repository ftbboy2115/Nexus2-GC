"""
Investigate 5 cases where Ross profited but the bot loses.
Runs each case through SimContext and extracts detailed trade data.
"""
import asyncio
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

CASES_TO_INVESTIGATE = [
    "ross_mnts_20260209",
    "ross_lcfy_20260116",
    "ross_flye_20260206",
    "ross_mlec_20260213",
    "ross_bnrg_20260211",
]


async def investigate_case(case_id: str, case: dict, yaml_data: dict) -> dict:
    """Run a single case and extract detailed trade data."""
    from nexus2.adapters.simulation.sim_context import (
        SimContext, load_case_into_context, step_clock_ctx
    )
    from nexus2.adapters.simulation.sim_clock import set_simulation_clock_ctx
    from nexus2.domain.automation.trade_event_service import set_sim_mode_ctx
    import time
    
    # Purge warrior_db between cases
    try:
        from nexus2.db.warrior_db import purge_sim_trades
        purge_sim_trades(confirm=True)
    except Exception:
        pass  # Table may not exist yet on first run

    start = time.time()
    symbol = case.get("symbol", "")
    ross_pnl = case.get("ross_pnl", 0) or 0
    
    # Create isolated context
    ctx = SimContext.create(case_id)
    set_simulation_clock_ctx(ctx.clock)
    set_sim_mode_ctx(True)
    
    # Load case
    bar_count = load_case_into_context(ctx, case, yaml_data)
    if bar_count == 0:
        return {"case_id": case_id, "error": "No bars loaded"}
    
    # Step through full day
    await step_clock_ctx(ctx, 960)
    
    # Force close open positions
    eod_positions = ctx.broker.get_positions()
    for pos in eod_positions:
        pos_symbol = pos.get("symbol")
        pos_qty = pos.get("qty", 0)
        if pos_qty > 0:
            ctx.broker.sell_position(pos_symbol, pos_qty)
    
    # Collect all data
    account = ctx.broker.get_account()
    orders = ctx.broker.get_orders()
    positions = ctx.broker.get_positions()
    
    # Separate buy/sell orders
    buy_orders = [o for o in orders if o.get("side") == "buy" and o.get("status") == "filled"]
    sell_orders = [o for o in orders if o.get("side") == "sell" and o.get("status") == "filled"]
    
    # Count entries and re-entries
    entry_count = len(buy_orders)
    
    # Calculate P&L per entry
    total_pnl = round(account.get("realized_pnl", 0) + account.get("unrealized_pnl", 0), 2)
    
    # Get monitor positions for exit details
    monitor_positions = ctx.monitor.get_positions()
    
    # Get event history from monitor if available
    event_log = []
    if hasattr(ctx.monitor, '_event_log'):
        event_log = ctx.monitor._event_log
    
    case_time = round(time.time() - start, 2)
    
    return {
        "case_id": case_id,
        "symbol": symbol,
        "date": case.get("trade_date"),
        "bar_count": bar_count,
        "ross_pnl": ross_pnl,
        "bot_pnl": total_pnl,
        "delta": round(total_pnl - ross_pnl, 2),
        "entry_count": entry_count,
        "sell_count": len(sell_orders),
        "buy_orders": [
            {
                "price": o.get("avg_fill_price"),
                "shares": o.get("filled_qty"),
                "time": o.get("sim_time"),
                "trigger": o.get("entry_trigger"),
                "exit_mode": o.get("exit_mode"),
            }
            for o in buy_orders
        ],
        "sell_orders": [
            {
                "price": o.get("avg_fill_price"),
                "shares": o.get("filled_qty"),
                "time": o.get("sim_time"),
            }
            for o in sell_orders
        ],
        "config": {
            "risk_per_trade": ctx.engine.config.risk_per_trade,
            "max_shares": ctx.engine.config.max_shares_per_trade,
        },
        "expected_entry": case.get("expected", {}).get("entry_near"),
        "expected_stop": case.get("expected", {}).get("stop_near"),
        "pmh": float(ctx.engine._watchlist.get(symbol, {}).pmh) if symbol in ctx.engine._watchlist else None,
        "runtime": case_time,
    }


async def main():
    import yaml
    
    # === IN-MEMORY DB (same as sim_context._run_case_sync) ===
    # Create ephemeral warrior_db so trade_event_service can log entries/exits
    from sqlalchemy import create_engine as _create_engine
    from sqlalchemy.orm import sessionmaker as _sessionmaker
    import nexus2.db.warrior_db as wdb
    
    mem_engine = _create_engine("sqlite://", connect_args={"check_same_thread": False})
    wdb.warrior_engine = mem_engine
    wdb.WarriorSessionLocal = _sessionmaker(autocommit=False, autoflush=False, bind=mem_engine)
    wdb.WarriorBase.metadata.create_all(bind=mem_engine)
    print("[Init] In-memory warrior_db created")
    
    # Load YAML
    yaml_path = os.path.join(
        os.path.dirname(__file__), "..", "tests", "test_cases", "warrior_setups.yaml"
    )
    with open(yaml_path, "r", encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f)
    
    all_cases = yaml_data.get("test_cases", [])
    
    # Filter to our target cases
    target_cases = [c for c in all_cases if c.get("id") in CASES_TO_INVESTIGATE]
    
    print(f"\n{'='*80}")
    print(f"WINNER-TO-LOSER INVESTIGATION: {len(target_cases)} cases")
    print(f"{'='*80}\n")
    
    results = []
    for case in target_cases:
        case_id = case.get("id")
        print(f"\n{'─'*60}")
        print(f"Running: {case_id} ({case.get('symbol')})")
        print(f"{'─'*60}")
        
        try:
            result = await investigate_case(case_id, case, yaml_data)
            results.append(result)
            
            # Print summary
            print(f"  Bot P&L:     ${result['bot_pnl']:+,.2f}")
            print(f"  Ross P&L:    ${result['ross_pnl']:+,.2f}")
            print(f"  Delta:       ${result['delta']:+,.2f}")
            print(f"  Entries:     {result['entry_count']}")
            print(f"  Sells:       {result['sell_count']}")
            print(f"  Expected:    entry=${result.get('expected_entry')}, stop=${result.get('expected_stop')}")
            print(f"  PMH:         ${result.get('pmh')}")
            
            if result.get("buy_orders"):
                print(f"\n  BUY ORDERS:")
                for i, o in enumerate(result["buy_orders"]):
                    print(f"    [{i+1}] ${o['price']:.2f} x{o['shares']} @ {o['time']} | trigger={o['trigger']} | exit_mode={o['exit_mode']}")
            else:
                print(f"\n  NO BUY ORDERS (bot did not enter)")
            
            if result.get("sell_orders"):
                print(f"\n  SELL ORDERS:")
                for i, o in enumerate(result["sell_orders"]):
                    print(f"    [{i+1}] ${o['price']:.2f} x{o['shares']} @ {o['time']}")
            
            print(f"\n  Runtime: {result['runtime']}s")
            
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append({"case_id": case_id, "error": str(e)})
    
    # Summary
    print(f"\n\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    
    total_bot_pnl = sum(r.get("bot_pnl", 0) for r in results)
    total_ross_pnl = sum(r.get("ross_pnl", 0) for r in results)
    total_entries = sum(r.get("entry_count", 0) for r in results)
    
    for r in results:
        if "error" in r and "bot_pnl" not in r:
            print(f"  {r['case_id']}: ERROR - {r['error']}")
            continue
        re_entries = max(0, r.get("entry_count", 0) - 1)
        print(f"  {r.get('symbol', '?'):6s} | Bot: ${r.get('bot_pnl', 0):+9,.2f} | Ross: ${r.get('ross_pnl', 0):+9,.2f} | Δ: ${r.get('delta', 0):+10,.2f} | Entries: {r.get('entry_count', 0)} (re: {re_entries})")
    
    print(f"\n  TOTAL  | Bot: ${total_bot_pnl:+9,.2f} | Ross: ${total_ross_pnl:+9,.2f} | Δ: ${total_bot_pnl - total_ross_pnl:+10,.2f} | Entries: {total_entries}")
    
    # Dump full results to JSON for further analysis
    output_path = os.path.join(
        os.path.dirname(__file__), "..", "reports", "2026-02-16", "data_winner_to_loser.json"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Full data written to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
