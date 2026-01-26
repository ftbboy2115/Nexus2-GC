#!/usr/bin/env python3
"""
NAC PSM Database Migration Script

1. Fix CRNX position (reopen with remaining_shares=4)
2. Migrate open NAC positions from nexus.db to nac.db
"""
import sqlite3
from datetime import datetime

NEXUS_DB = "/root/Nexus2/data/nexus.db"
NAC_DB = "/root/Nexus2/data/nac.db"

def fix_crnx():
    """Reopen CRNX position that was incorrectly marked as closed."""
    print("=== Fixing CRNX Position ===")
    
    conn = sqlite3.connect(NEXUS_DB)
    cursor = conn.cursor()
    
    # Find CRNX position
    cursor.execute("SELECT id, symbol, status, remaining_shares, closed_at FROM positions WHERE symbol='CRNX' AND id='6b2c6d49-8e07-465b-8791-f4f829ffeadb'")
    row = cursor.fetchone()
    
    if row:
        print(f"Current state: id={row[0][:8]}..., status={row[2]}, remaining_shares={row[3]}, closed_at={row[4]}")
        
        # Fix: reopen with 4 remaining shares (per Alpaca)
        cursor.execute("""
            UPDATE positions 
            SET status = 'open', 
                remaining_shares = 4, 
                closed_at = NULL
            WHERE id = '6b2c6d49-8e07-465b-8791-f4f829ffeadb'
        """)
        conn.commit()
        print("✅ CRNX reopened with remaining_shares=4")
    else:
        print("⚠️ CRNX position not found")
    
    conn.close()

def migrate_to_nac_db():
    """Migrate open NAC positions from nexus.db to nac.db."""
    print("\n=== Migrating Open Positions to nac.db ===")
    
    # Read open NAC positions from nexus.db
    nexus_conn = sqlite3.connect(NEXUS_DB)
    nexus_conn.row_factory = sqlite3.Row
    cursor = nexus_conn.cursor()
    
    cursor.execute("""
        SELECT id, symbol, status, entry_price, shares, remaining_shares, 
               initial_stop, setup_type, opened_at, realized_pnl, partial_taken
        FROM positions 
        WHERE status IN ('open', 'partial') 
        AND source = 'nac'
    """)
    positions = cursor.fetchall()
    nexus_conn.close()
    
    if not positions:
        print("No open NAC positions to migrate")
        return
    
    print(f"Found {len(positions)} open NAC positions")
    
    # Insert into nac.db
    nac_conn = sqlite3.connect(NAC_DB)
    cursor = nac_conn.cursor()
    
    # Create table if not exists (should be created by init_nac_db but just in case)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nac_trades (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            status TEXT NOT NULL,
            entry_price TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            entry_time DATETIME NOT NULL,
            setup_type TEXT,
            stop_price TEXT NOT NULL,
            target_price TEXT,
            exit_price TEXT,
            exit_time DATETIME,
            exit_reason TEXT,
            realized_pnl TEXT DEFAULT '0',
            partial_taken INTEGER DEFAULT 0,
            remaining_quantity INTEGER,
            entry_order_id TEXT,
            exit_order_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    migrated = 0
    for p in positions:
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO nac_trades 
                (id, symbol, status, entry_price, quantity, entry_time, setup_type, 
                 stop_price, realized_pnl, partial_taken, remaining_quantity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p['id'],
                p['symbol'],
                p['status'],
                p['entry_price'],
                p['shares'],
                p['opened_at'],
                p['setup_type'],
                p['initial_stop'] or '0',
                p['realized_pnl'] or '0',
                1 if p['partial_taken'] else 0,
                p['remaining_shares'],
            ))
            migrated += 1
            print(f"  ✅ {p['symbol']}: {p['remaining_shares']} shares")
        except Exception as e:
            print(f"  ❌ {p['symbol']}: {e}")
    
    nac_conn.commit()
    nac_conn.close()
    
    print(f"\n✅ Migrated {migrated}/{len(positions)} positions to nac.db")

if __name__ == "__main__":
    fix_crnx()
    migrate_to_nac_db()
    print("\n=== Migration Complete ===")
