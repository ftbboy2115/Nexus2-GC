"""
Position Metadata Enrichment Script

PURPOSE:
--------
Repairs orphaned positions in the local database that are missing proper metadata.
This can happen when:
1. NAC places trades but DB records are lost (historical bug)
2. Positions are synced from Alpaca but marked as "external" 
3. Server restarts cause DB/Alpaca state desync

HOW IT WORKS:
-------------
1. Queries Alpaca order history to find bracket orders (buy + stop-loss pairs)
2. Matches orphaned "external" positions with their Alpaca order metadata
3. Updates local DB with correct: source, setup_type, initial_stop, current_stop

USAGE:
------
    # Dry run (preview changes)
    python -m nexus2.scripts.enrich_positions
    
    # Apply changes
    python -m nexus2.scripts.enrich_positions --apply
    
    # Specify date range for order history lookup
    python -m nexus2.scripts.enrich_positions --apply --days 30

REQUIREMENTS:
-------------
- Alpaca API credentials in .env (ALPACA_API_KEY, ALPACA_SECRET_KEY)
- Database must be accessible
"""

import argparse
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

from nexus2.db import SessionLocal, PositionRepository


def get_alpaca_order_history(days: int = 30) -> Dict[str, dict]:
    """
    Fetch bracket order history from Alpaca.
    
    Returns:
        Dict mapping symbol -> {stop_price, entry_price, qty, filled_at}
    """
    from nexus2.adapters.broker.alpaca_broker import AlpacaBroker
    
    broker = AlpacaBroker()
    
    # Get orders from the last N days
    after_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    try:
        # Get all filled orders
        orders = broker._api.list_orders(
            status="all",
            after=after_date,
            direction="desc",
            limit=500,
        )
    except Exception as e:
        print(f"❌ Failed to fetch Alpaca orders: {e}")
        return {}
    
    # Group orders by symbol to find bracket pairs (buy + stop-loss)
    order_data = {}
    for order in orders:
        symbol = order.symbol
        
        # Process filled buy orders
        if order.side == "buy" and order.status == "filled":
            if symbol not in order_data:
                order_data[symbol] = {
                    "entry_price": float(order.filled_avg_price or order.limit_price or 0),
                    "qty": int(float(order.filled_qty or order.qty)),
                    "filled_at": str(order.filled_at.date()) if order.filled_at else None,
                    "stop_price": None,
                }
        
        # Process stop-loss orders (expired or cancelled - we want the stop price)
        if order.side == "sell" and order.type in ("stop", "stop_limit"):
            if symbol in order_data and order_data[symbol]["stop_price"] is None:
                order_data[symbol]["stop_price"] = float(order.stop_price or 0)
    
    # Filter to only include entries with valid stop prices
    return {
        symbol: data 
        for symbol, data in order_data.items() 
        if data.get("stop_price") and data.get("entry_price")
    }


def enrich_positions(dry_run: bool = True, days: int = 30):
    """Enrich external positions with correct metadata from Alpaca."""
    
    print(f"🔍 Fetching Alpaca order history (last {days} days)...")
    alpaca_data = get_alpaca_order_history(days)
    
    if not alpaca_data:
        print("⚠️  No matching bracket orders found in Alpaca history")
        return
    
    print(f"📦 Found {len(alpaca_data)} symbols with bracket order data")
    
    db = SessionLocal()
    repo = PositionRepository(db)
    
    try:
        # Get all open positions
        positions = repo.get_all(status="open")
        
        updated = []
        skipped = []
        
        for pos in positions:
            if pos.symbol not in alpaca_data:
                continue
                
            order_info = alpaca_data[pos.symbol]
            
            # Check if this position needs enrichment
            needs_update = (
                pos.source in ("manual", "external") or
                pos.setup_type == "external" or
                pos.initial_stop is None or
                str(pos.initial_stop) == "0" or
                str(pos.initial_stop) == "None"
            )
            
            if not needs_update:
                skipped.append(f"{pos.symbol}: already has correct metadata")
                continue
            
            print(f"\n📝 {pos.symbol}:")
            print(f"   Before: source={pos.source}, setup={pos.setup_type}, stop={pos.initial_stop}")
            
            updates = {
                "source": "nac",
                "setup_type": "breakout",  # Default - could be refined with more analysis
                "initial_stop": str(order_info["stop_price"]),
                "current_stop": str(order_info["stop_price"]),
                "entry_price": str(order_info["entry_price"]),
            }
            
            print(f"   After:  source=nac, setup=breakout, stop={order_info['stop_price']}")
            
            if not dry_run:
                repo.update(str(pos.id), updates)
                updated.append(pos.symbol)
            else:
                updated.append(f"{pos.symbol} (dry-run)")
        
        if not dry_run and updated:
            db.commit()
        
        print(f"\n{'='*50}")
        print(f"Updated: {len(updated)} positions")
        print(f"Skipped: {len(skipped)} positions")
        
        if dry_run:
            print("\n⚠️  DRY RUN - no changes made. Run with --apply to apply.")
        else:
            print("\n✅ Changes applied to database.")
            
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Enrich orphaned position metadata from Alpaca order history"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to database (default: dry run)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days of order history to search (default: 30)"
    )
    
    args = parser.parse_args()
    enrich_positions(dry_run=not args.apply, days=args.days)


if __name__ == "__main__":
    main()
