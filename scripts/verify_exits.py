"""Quick verification of avg exit price calculation."""
import sqlite3
from decimal import Decimal

conn = sqlite3.connect('data/nexus.db')

# Check if position_exits table exists
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='position_exits'")
if not cursor.fetchone():
    print("❌ position_exits table does not exist yet!")
    print("   Restart the backend to create the table.")
    conn.close()
    exit()

print("✅ position_exits table exists\n")

# Get all exits
print("=== Position Exits ===")
cursor = conn.execute("""
    SELECT position_id, shares, exit_price, reason, exited_at 
    FROM position_exits 
    ORDER BY exited_at DESC 
    LIMIT 20
""")
exits = cursor.fetchall()
if not exits:
    print("No exits recorded yet. Close some positions to see data here.")
else:
    for row in exits:
        print(f"  Position: {row[0][:8]}... | {row[1]} shares @ ${row[2]} | {row[3]} | {row[4]}")

# Get closed positions and calculate avg exit
print("\n=== Closed Positions with Avg Exit ===")
cursor = conn.execute("""
    SELECT id, symbol, entry_price, shares, realized_pnl
    FROM positions 
    WHERE status = 'closed'
    ORDER BY closed_at DESC
    LIMIT 10
""")
positions = cursor.fetchall()

for pos in positions:
    pos_id, symbol, entry, shares, pnl = pos
    
    # Calculate avg exit from exits
    cursor = conn.execute("""
        SELECT SUM(shares * CAST(exit_price AS REAL)), SUM(shares)
        FROM position_exits
        WHERE position_id = ?
    """, (pos_id,))
    result = cursor.fetchone()
    
    if result[0] and result[1]:
        avg_exit = result[0] / result[1]
        print(f"  {symbol}: Entry ${entry} → Avg Exit ${avg_exit:.2f} | P&L: ${pnl}")
    else:
        print(f"  {symbol}: Entry ${entry} → Avg Exit: - (no exits recorded) | P&L: ${pnl}")

conn.close()
