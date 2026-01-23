#!/usr/bin/env python3
"""Run warrior_db migration to add quote tracking columns."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus2.db.warrior_db import init_warrior_db
init_warrior_db()
print("Migration complete!")
