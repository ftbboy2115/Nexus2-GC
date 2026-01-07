import sqlite3
conn = sqlite3.connect('data/nexus.db')
c = conn.cursor()
c.execute("SELECT symbol, opened_at FROM positions WHERE status='open' ORDER BY symbol")
for r in c.fetchall():
    print(f"{r[0]}: {r[1]}")
