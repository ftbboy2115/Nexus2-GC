"""Quick migration to add min_price column or create table if missing."""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "nexus.db")
print(f"Connecting to: {db_path}")

conn = sqlite3.connect(db_path)

# Check if table exists
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print(f"Existing tables: {tables}")

if "scheduler_settings" not in tables:
    print("Table scheduler_settings doesn't exist - creating it...")
    conn.execute("""
        CREATE TABLE scheduler_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            adopt_quick_actions VARCHAR(5) DEFAULT 'true',
            preset VARCHAR(20) DEFAULT 'strict',
            min_quality INTEGER DEFAULT 7,
            stop_mode VARCHAR(10) DEFAULT 'atr',
            max_stop_atr VARCHAR(10) DEFAULT '1.0',
            max_stop_percent VARCHAR(10) DEFAULT '5.0',
            scan_modes VARCHAR(50) DEFAULT 'ep,breakout,htf',
            htf_frequency VARCHAR(20) DEFAULT 'market_open',
            auto_execute VARCHAR(5) DEFAULT 'false',
            max_position_value VARCHAR(20),
            auto_start_enabled VARCHAR(5) DEFAULT 'false',
            auto_start_time VARCHAR(5),
            nac_broker_type VARCHAR(20) DEFAULT 'alpaca_paper',
            nac_account VARCHAR(10) DEFAULT 'A',
            sim_mode VARCHAR(5) DEFAULT 'false',
            min_price VARCHAR(10),
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Insert default row
    conn.execute("INSERT INTO scheduler_settings (id) VALUES (1)")
    conn.commit()
    print("✅ Created scheduler_settings table with min_price column")
else:
    # Table exists, check for column
    cursor = conn.execute("PRAGMA table_info(scheduler_settings)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns: {columns}")
    
    if "min_price" not in columns:
        conn.execute("ALTER TABLE scheduler_settings ADD COLUMN min_price VARCHAR(10) DEFAULT NULL")
        conn.commit()
        print("✅ Added min_price column")
    else:
        print("ℹ️ min_price column already exists")

conn.close()
print("Done!")
