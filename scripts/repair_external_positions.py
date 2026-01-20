#!/usr/bin/env python3
"""
Repair script to fix NAC positions that were incorrectly marked as 'external'.

BUG CONTEXT:
CMG, IAG, COMP, HOUS were opened by NAC but their DB records weren't created
due to silent DB failures. They were later detected by broker sync and 
marked as setup_type='external' with missing metadata.

This script:
1. Identifies positions with setup_type='external' 
2. Updates them with correct NAC metadata from Alpaca order history
3. Sets source='nac' to indicate they were NAC-managed

Run from VPS: python scripts/repair_external_positions.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from decimal import Decimal
from nexus2.db import SessionLocal, PositionModel

# Position repairs based on Alpaca order history
REPAIRS = {
    "CMG": {
        "setup_type": "ep",  # Was likely an EP signal
        "entry_price": "39.97",
        "shares": 12,
        "initial_stop": "39.19",  # From Alpaca stop order
        "opened_at": datetime(2026, 1, 20, 10, 30, 25),  # From Alpaca fill time
        "source": "nac",
    },
    "IAG": {
        "setup_type": "ep",  # Was likely an EP signal
        "entry_price": "19.93",
        "shares": 25,
        "initial_stop": "18.84",  # From Alpaca stop order
        "opened_at": datetime(2026, 1, 20, 11, 55, 52),
        "source": "nac",
    },
    "COMP": {
        "setup_type": "ep",
        "entry_price": "12.07",
        "shares": 41,  # Original shares (20 remaining after sells)
        "remaining_shares": 20,
        "initial_stop": "10.60",  # From Alpaca stop order
        "opened_at": datetime(2026, 1, 7, 11, 31, 13),
        "source": "nac",
    },
    "HOUS": {
        "setup_type": "ep",
        "entry_price": "17.05",
        "shares": 29,
        "initial_stop": "16.23",  # From Alpaca stop order
        "opened_at": datetime(2026, 1, 7, 15, 51, 30),
        "source": "nac",
    },
}


def repair_positions():
    """Update external positions with correct NAC metadata."""
    db = SessionLocal()
    
    try:
        repaired = 0
        for symbol, data in REPAIRS.items():
            # Find the external position
            position = db.query(PositionModel).filter(
                PositionModel.symbol == symbol,
                PositionModel.setup_type == "external"
            ).first()
            
            if not position:
                print(f"⚠️ {symbol}: No 'external' position found - may already be fixed")
                continue
            
            # Update with correct data
            position.setup_type = data["setup_type"]
            position.entry_price = data["entry_price"]
            position.shares = data["shares"]
            position.remaining_shares = data.get("remaining_shares", data["shares"])
            position.initial_stop = data["initial_stop"]
            position.current_stop = data["initial_stop"]
            position.opened_at = data["opened_at"]
            position.source = data["source"]
            
            print(f"✅ {symbol}: Repaired - setup_type={data['setup_type']}, entry=${data['entry_price']}, stop=${data['initial_stop']}")
            repaired += 1
        
        db.commit()
        print(f"\n✅ Repaired {repaired} positions")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


def show_current_state():
    """Show current state of external positions."""
    db = SessionLocal()
    
    try:
        external = db.query(PositionModel).filter(
            PositionModel.setup_type == "external"
        ).all()
        
        if not external:
            print("✅ No 'external' positions found")
            return
        
        print(f"\n📋 Found {len(external)} 'external' positions:")
        for p in external:
            print(f"   - {p.symbol}: entry=${p.entry_price}, shares={p.shares}, opened={p.opened_at}")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Repair NAC external positions")
    parser.add_argument("--dry-run", action="store_true", help="Show current state without making changes")
    args = parser.parse_args()
    
    if args.dry_run:
        show_current_state()
    else:
        print("🔧 Repairing external positions with NAC metadata from Alpaca...\n")
        repair_positions()
