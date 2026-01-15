#!/usr/bin/env python3
"""Check what data is logged in trade events for AI analysis"""
import sqlite3
import json

conn = sqlite3.connect('/root/Nexus2/data/nexus.db')
c = conn.cursor()

# Get recent WARRIOR ENTRY events
c.execute('''
    SELECT position_id, reason, metadata_json, created_at
    FROM trade_events 
    WHERE strategy='WARRIOR' AND event_type='ENTRY'
    ORDER BY created_at DESC
    LIMIT 3
''')

print("=== WARRIOR ENTRY Metadata Check ===")
for row in c.fetchall():
    pos_id, reason, metadata_json, created = row
    print(f"\n{pos_id[:8]} @ {str(created)[:19]}")
    print(f"  Reason: {reason}")
    if metadata_json:
        meta = json.loads(metadata_json)
        print(f"  trigger_type: {meta.get('trigger_type', 'MISSING')}")
        print(f"  entry_price: {meta.get('entry_price', 'MISSING')}")
        print(f"  stop_price: {meta.get('stop_price', 'MISSING')}")
        print(f"  shares: {meta.get('shares', 'MISSING')}")
        print(f"  spy_price: {meta.get('spy_price', 'MISSING')}")
        print(f"  vix: {meta.get('vix', 'MISSING')}")
        print(f"  spy_ma_trend: {meta.get('spy_ma_trend', 'MISSING')}")

conn.close()
