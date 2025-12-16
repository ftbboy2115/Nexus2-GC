"""
Script: Log Archiver (Clean Slate Tool)
Usage: python tools/archive_logs.py
Description: Moves active log files to a timestamped archive folder.
             Run this AFTER liquidating old positions to start fresh.
"""
import os
import shutil
import datetime

# CONFIG
# We assume this script runs from /tools, so we go up one level to find root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ARCHIVE_ROOT = os.path.join(DATA_DIR, "archive")

# FILES TO ARCHIVE
TARGETS = ["trade_log.csv", "sniper.log", "scanner_auto.log", "ep_auto.log"]


def archive_now():
    # 1. Ensure Archive Root Exists
    if not os.path.exists(ARCHIVE_ROOT):
        os.makedirs(ARCHIVE_ROOT)

    # 2. Create Timestamped Vault (e.g., data/archive/2025-12-14_203015)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest_dir = os.path.join(ARCHIVE_ROOT, timestamp)
    os.makedirs(dest_dir)

    print(f"📦 Archiving logs to: {dest_dir}...")

    moved_count = 0
    for filename in TARGETS:
        src = os.path.join(DATA_DIR, filename)
        if os.path.exists(src):
            shutil.move(src, os.path.join(dest_dir, filename))
            print(f"   -> Moved {filename}")
            moved_count += 1

    if moved_count > 0:
        print(f"✅ Success. {moved_count} files archived.")
        print("   The system starts fresh on next run.")
    else:
        print("ℹ️  No active logs found to archive.")
        # Cleanup empty folder if nothing moved
        try:
            os.rmdir(dest_dir)
            print("   (Cleaned up empty archive folder)")
        except:
            pass


if __name__ == "__main__":
    archive_now()