import sqlite3
SYMBOLS = ['CMCSA', 'CP', 'MDLZ', 'PBR', 'T', 'WBD', 'WMB']
conn = sqlite3.connect('data/nexus.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
print('ORIGINAL ENTRY DATA:')
print('='*60)
for sym in SYMBOLS:
    c.execute('SELECT * FROM positions WHERE symbol = ? ORDER BY opened_at DESC LIMIT 1', (sym,))
    r = c.fetchone()
    if r:
        print(f"\n{r['symbol']}:")
        print(f"  Entry: ${float(r['entry_price'] or 0):.2f}")
        print(f"  Stop: ${float(r['current_stop'] or 0):.2f}")
        print(f"  Opened: {r['opened_at']}")
        print(f"  Setup Type: {r['setup_type']}")
        print(f"  Quality: {r['quality_score']}")
        print(f"  RS%: {r['rs_percentile']}")
        print(f"  Source: {r['source']}")
    else:
        print(f'\n{sym}: NOT FOUND')
