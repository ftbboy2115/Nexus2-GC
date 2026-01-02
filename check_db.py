import sqlite3

db = sqlite3.connect('data/nexus.db')

cursor = db.execute('SELECT COUNT(*) FROM positions')
print('Total positions:', cursor.fetchone()[0])

cursor = db.execute("SELECT COUNT(*) FROM positions WHERE status = 'open'")
print('Open:', cursor.fetchone()[0])

cursor = db.execute("SELECT COUNT(*) FROM positions WHERE status = 'closed'")
print('Closed:', cursor.fetchone()[0])

# Show recent positions
cursor = db.execute("SELECT symbol, status, setup_type, opened_at FROM positions ORDER BY opened_at DESC LIMIT 10")
print("\nRecent positions:")
for row in cursor:
    print(f"  {row[0]:6} | {row[1]:8} | {row[2] or 'N/A':10} | {row[3]}")
