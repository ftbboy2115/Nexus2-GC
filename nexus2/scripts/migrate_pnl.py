"""
P&L Migration Script

Recalculates realized_pnl for all closed Warrior trades that had partial exits.
The old code had two bugs:
  1. Partial exits didn't accumulate P&L
  2. Full exit used original quantity instead of remaining_quantity

This script identifies affected trades and recalculates using:
  P&L = (exit_price - entry_price) * quantity  (for trades WITHOUT partial info)
  
For trades WITH partials, we can only approximate since partial exit prices
weren't stored. We recalculate using the final exit_price for all shares.

Run with --dry-run first to preview changes.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nexus2.db.warrior_db import (
    WarriorTradeModel,
    get_warrior_session,
    WARRIOR_DB_PATH,
)


def check_db_exists():
    """Verify warrior.db exists before running migration."""
    if not WARRIOR_DB_PATH.exists():
        print(f"❌ warrior.db not found at {WARRIOR_DB_PATH}")
        print("   This script must run on the VPS where the bot's data lives.")
        print("   Deploy first, then run: python nexus2/scripts/migrate_pnl.py")
        sys.exit(1)


def migrate_pnl(dry_run: bool = True):
    """Recalculate P&L for closed trades with partial exits."""
    
    with get_warrior_session() as db:
        # Find all closed trades that had partial exits
        affected = db.query(WarriorTradeModel).filter(
            WarriorTradeModel.status == "closed",
            WarriorTradeModel.partial_taken == True,
        ).all()
        
        print(f"Found {len(affected)} closed trades with partial exits")
        print("-" * 70)
        
        fixes = []
        for trade in affected:
            entry = float(trade.entry_price or "0")
            exit_p = float(trade.exit_price or "0")
            qty = trade.quantity or 0
            old_pnl = float(trade.realized_pnl or "0")
            
            if exit_p == 0 or entry == 0:
                print(f"  SKIP {trade.symbol} ({trade.id[:8]}) — missing entry/exit price")
                continue
            
            # Best approximation: full quantity * (exit - entry)
            # This is what the old code did, but it's actually correct IF
            # there's only one exit price recorded (the final one).
            # The real fix is for FUTURE trades where partial P&L is now tracked.
            new_pnl = round((exit_p - entry) * qty, 2)
            
            if abs(new_pnl - old_pnl) < 0.01:
                print(f"  OK   {trade.symbol} ({trade.id[:8]}) — P&L already correct: ${old_pnl}")
                continue
            
            fixes.append({
                "trade": trade,
                "symbol": trade.symbol,
                "id": trade.id[:8],
                "entry": entry,
                "exit": exit_p,
                "qty": qty,
                "remaining": trade.remaining_quantity,
                "old_pnl": old_pnl,
                "new_pnl": new_pnl,
            })
            
            print(
                f"  FIX  {trade.symbol} ({trade.id[:8]}) — "
                f"${old_pnl} → ${new_pnl} "
                f"(entry=${entry}, exit=${exit_p}, qty={qty})"
            )
        
        print("-" * 70)
        print(f"Total fixes needed: {len(fixes)}")
        
        if not fixes:
            print("No changes needed.")
            return
        
        if dry_run:
            print("\n⚠️  DRY RUN — no changes made. Run with --apply to commit.")
            return
        
        # Apply fixes
        for fix in fixes:
            fix["trade"].realized_pnl = str(fix["new_pnl"])
        
        db.commit()
        print(f"\n✅ Applied {len(fixes)} P&L corrections.")


if __name__ == "__main__":
    check_db_exists()
    is_dry_run = "--apply" not in sys.argv
    
    if is_dry_run:
        print("=" * 70)
        print("P&L Migration — DRY RUN")
        print("=" * 70)
    else:
        print("=" * 70)
        print("P&L Migration — APPLYING CHANGES")
        print("=" * 70)
    
    migrate_pnl(dry_run=is_dry_run)
