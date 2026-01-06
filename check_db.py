"""Cleanup: deduplicate positions and sync with Alpaca."""
import sqlite3
import requests

db_path = 'data/nexus.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Step 1: Get Alpaca positions (via API)
print("=== Step 1: Get Alpaca positions ===")
try:
    resp = requests.get("http://localhost:8000/automation/positions", timeout=5)
    alpaca_data = resp.json()
    alpaca_symbols = set(p["symbol"] for p in alpaca_data.get("positions", []))
    print(f"  Alpaca has {len(alpaca_symbols)} positions: {', '.join(sorted(alpaca_symbols))}")
except Exception as e:
    print(f"  ERROR getting Alpaca positions: {e}")
    alpaca_symbols = set()

# Step 2: Find duplicates and keep only newest
print("\n=== Step 2: Deduplicate (keep newest per symbol) ===")
c.execute("""
    SELECT symbol, COUNT(*) as cnt 
    FROM positions WHERE status='open' 
    GROUP BY symbol HAVING cnt > 1
""")
duplicates = c.fetchall()

for symbol, count in duplicates:
    # Get all IDs for this symbol, ordered by opened_at DESC
    c.execute("""
        SELECT id, opened_at FROM positions 
        WHERE symbol=? AND status='open' 
        ORDER BY opened_at DESC
    """, (symbol,))
    entries = c.fetchall()
    
    # Keep the first (newest), close the rest
    keep_id = entries[0][0]
    close_ids = [e[0] for e in entries[1:]]
    
    for close_id in close_ids:
        c.execute("UPDATE positions SET status='closed' WHERE id=?", (close_id,))
    
    print(f"  {symbol}: kept 1, closed {len(close_ids)} duplicates")

# Step 3: Close positions not in Alpaca
print("\n=== Step 3: Close positions not in Alpaca ===")
if alpaca_symbols:
    c.execute("SELECT id, symbol FROM positions WHERE status='open'")
    for pos_id, symbol in c.fetchall():
        if symbol not in alpaca_symbols:
            c.execute("UPDATE positions SET status='closed' WHERE id=?", (pos_id,))
            print(f"  Closed {symbol} (not in Alpaca)")

conn.commit()

# Final count
print("\n=== Final State ===")
c.execute("SELECT COUNT(*) FROM positions WHERE status='open'")
open_count = c.fetchone()[0]
print(f"  Open positions in DB: {open_count}")
print(f"  Alpaca positions: {len(alpaca_symbols)}")
print(f"  Match: {'✅ YES' if open_count == len(alpaca_symbols) else '❌ NO'}")

conn.close()
print("\n⚠️ Restart uvicorn to reload positions")
