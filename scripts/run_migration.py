#!/usr/bin/env python3
"""Run warrior_db migration to add quote tracking columns."""
from nexus2.db.warrior_db import init_warrior_db
init_warrior_db()
print("Migration complete!")
