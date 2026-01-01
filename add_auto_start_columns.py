"""Add auto-start columns to scheduler_settings table."""
from nexus2.db import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    db.execute(text('ALTER TABLE scheduler_settings ADD COLUMN auto_start_enabled VARCHAR(5) DEFAULT "false"'))
    db.execute(text('ALTER TABLE scheduler_settings ADD COLUMN auto_start_time VARCHAR(5) DEFAULT NULL'))
    db.commit()
    print("✅ Columns added successfully")
except Exception as e:
    if "duplicate column" in str(e).lower():
        print("⚠️ Columns already exist")
    else:
        print(f"❌ Error: {e}")
finally:
    db.close()
