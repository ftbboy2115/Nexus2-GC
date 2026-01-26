#!/usr/bin/env python3
"""Query CRNX position data from all NAC databases."""
import sqlite3
import json

databases = [
    "/root/Nexus2/data/nexus.db",
    "/root/Nexus2/data/warrior.db",
    "/root/Nexus2/data/nac.db",
    "/root/Nexus2/nac_positions.db",
]

for db_path in databases:
    print(f"\n{'='*60}")
    print(f"=== Database: {db_path} ===")
    print('='*60)
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # List tables
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor]
        print(f"Tables: {tables}")
        
        # Look for CRNX in any table
        for table in tables:
            try:
                cursor = conn.execute(f"SELECT * FROM {table} WHERE symbol='CRNX' OR (CAST(symbol AS TEXT) LIKE '%CRNX%')")
                rows = cursor.fetchall()
                if rows:
                    print(f"\n>>> Found CRNX in {table}:")
                    for row in rows:
                        print(json.dumps(dict(row), indent=2, default=str))
            except Exception:
                pass  # Column doesn't exist in this table
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
