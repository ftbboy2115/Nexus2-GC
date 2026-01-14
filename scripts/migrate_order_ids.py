#!/usr/bin/env python3
"""Add order ID columns to warrior_trades table."""
import sqlite3

conn = sqlite3.connect('/root/Nexus2/data/warrior.db')
cursor = conn.cursor()

try:
    cursor.execute('ALTER TABLE warrior_trades ADD COLUMN entry_order_id TEXT')
    print('Added entry_order_id')
except Exception as e:
    print(f'entry_order_id: {e}')

try:
    cursor.execute('ALTER TABLE warrior_trades ADD COLUMN exit_order_id TEXT')
    print('Added exit_order_id')
except Exception as e:
    print(f'exit_order_id: {e}')

conn.commit()
conn.close()
print('Migration complete')
