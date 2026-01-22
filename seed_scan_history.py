"""
Seed ScanHistoryLogger from warrior_scan.log

Parses existing log entries and populates the scan history for backtesting.
"""

import re
from datetime import datetime
from pathlib import Path

# Add project to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from nexus2.domain.lab.scan_history_logger import get_scan_history_logger

# Pattern: 2026-01-13 20:24:38 | PASS | AGH | Gap:14.9% | RVOL:2.4x | Score:1
PASS_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}\s+\|\s+PASS\s+\|\s+(\w+)\s+\|\s+Gap:([\d.]+)%\s+\|\s+RVOL:([\d.]+)x\s+\|\s+Score:(\d+)"
)


def parse_log_file(log_path: Path) -> list[dict]:
    """Parse warrior_scan.log for PASS entries."""
    entries = []
    seen = set()  # (date, symbol) pairs to dedupe
    
    with open(log_path, "r") as f:
        for line in f:
            match = PASS_PATTERN.search(line)
            if match:
                date_str, symbol, gap, rvol, score = match.groups()
                key = (date_str, symbol)
                
                if key not in seen:
                    seen.add(key)
                    entries.append({
                        "date": datetime.strptime(date_str, "%Y-%m-%d").date(),
                        "symbol": symbol,
                        "gap_percent": float(gap),
                        "rvol": float(rvol),
                        "score": int(score),
                    })
    
    return entries


def seed_history(entries: list[dict]) -> dict:
    """Seed entries into ScanHistoryLogger."""
    logger = get_scan_history_logger()
    
    added = 0
    for entry in entries:
        logger.log_passed_symbol(
            symbol=entry["symbol"],
            scan_date=entry["date"],
            gap_percent=entry["gap_percent"],
            rvol=entry["rvol"],
            score=entry["score"],
            catalyst=None,  # Not in log format
        )
        added += 1
    
    return logger.get_stats()


def main():
    # Find log files
    root = Path(__file__).parent
    log_paths = [
        root / "warrior_scan.log",
        root / "data" / "warrior_scan.log",
    ]
    
    all_entries = []
    for log_path in log_paths:
        if log_path.exists():
            print(f"📂 Parsing: {log_path}")
            entries = parse_log_file(log_path)
            print(f"   Found: {len(entries)} unique PASS entries")
            all_entries.extend(entries)
    
    if not all_entries:
        print("❌ No log files found or no PASS entries")
        return
    
    # Dedupe across files
    seen = set()
    unique_entries = []
    for e in all_entries:
        key = (e["date"].isoformat(), e["symbol"])
        if key not in seen:
            seen.add(key)
            unique_entries.append(e)
    
    print(f"\n📊 Total unique entries: {len(unique_entries)}")
    
    # Seed
    print("\n🌱 Seeding ScanHistoryLogger...")
    stats = seed_history(unique_entries)
    
    print(f"\n✅ Complete!")
    print(f"   Total entries: {stats['total_entries']}")
    print(f"   Unique symbols: {stats['unique_symbols']}")
    print(f"   Total dates: {stats['total_dates']}")
    print(f"   Date range: {stats['date_range']}")


if __name__ == "__main__":
    main()
