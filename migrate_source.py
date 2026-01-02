import sqlite3

db = sqlite3.connect('data/nexus.db')

# Add new columns
try:
    db.execute("ALTER TABLE positions ADD COLUMN source VARCHAR(20) DEFAULT 'manual'")
    print("Added 'source' column")
except Exception as e:
    print(f"source column: {e}")

try:
    db.execute("ALTER TABLE positions ADD COLUMN exit_price VARCHAR(20)")
    print("Added 'exit_price' column")
except Exception as e:
    print(f"exit_price column: {e}")

try:
    db.execute("ALTER TABLE positions ADD COLUMN exit_date DATETIME")
    print("Added 'exit_date' column")
except Exception as e:
    print(f"exit_date column: {e}")

db.commit()
print("\nMigration complete!")

# Verify columns exist
cursor = db.execute("PRAGMA table_info(positions)")
columns = [row[1] for row in cursor.fetchall()]
print(f"Columns in positions table: {columns}")
