"""Quick migration to add quality score columns to positions table."""
import sqlite3
import os

# Find the database
db_path = os.path.join(os.path.dirname(__file__), "..", "data", "nexus.db")
print(f"Database path: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Add columns (ignore if already exist)
columns = [
    ("quality_score", "INTEGER"),
    ("tier", "TEXT"),
    ("rs_percentile", "INTEGER"),
    ("adr_percent", "TEXT"),
]

for col_name, col_type in columns:
    try:
        cursor.execute(f"ALTER TABLE positions ADD COLUMN {col_name} {col_type}")
        print(f"Added column: {col_name}")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print(f"Column {col_name} already exists")
        else:
            print(f"Error adding {col_name}: {e}")

conn.commit()
conn.close()
print("Migration complete!")
