#!/usr/bin/env python3
"""Query NAC trade performance from database."""

from nexus2.db.database import get_session
from nexus2.db.models import Position, TradeEvent
from sqlalchemy import desc

with get_session() as session:
    # NAC positions
    positions = session.query(Position).filter(Position.source == 'nac').order_by(desc(Position.created_at)).limit(30).all()
    
    print(f"\n=== NAC POSITIONS ({len(positions)}) ===")
    print("-" * 80)
    
    total_pnl = 0
    open_count = 0
    closed_count = 0
    winners = 0
    losers = 0
    
    for p in positions:
        pnl = float(p.unrealized_pnl or 0)
        total_pnl += pnl
        
        if p.status == 'open':
            open_count += 1
            status = 'OPEN'
        else:
            closed_count += 1
            status = 'CLOSED'
            if pnl > 0:
                winners += 1
            elif pnl < 0:
                losers += 1
        
        print(f"{p.symbol:6} | {p.quantity:4} @ ${float(p.entry_price):7.2f} | PnL: ${pnl:8.2f} | {status:6} | {p.created_at}")
    
    print("-" * 80)
    print(f"\nSUMMARY:")
    print(f"  Open: {open_count} | Closed: {closed_count}")
    print(f"  Winners: {winners} | Losers: {losers}")
    print(f"  Win Rate: {winners/(winners+losers)*100:.1f}%" if winners+losers > 0 else "  Win Rate: N/A")
    print(f"  Total PnL: ${total_pnl:.2f}")
