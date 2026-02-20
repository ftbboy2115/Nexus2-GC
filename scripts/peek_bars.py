"""
Peek at bars from a Mock Market test case JSON file.

Usage:
    python scripts/peek_bars.py <json_file> [start_time] [end_time]

Examples:
    # Show all bars around market open (default: 09:25 - 09:45)
    python scripts/peek_bars.py nexus2/tests/test_cases/intraday/ross_mlec_20260220.json

    # Custom time range
    python scripts/peek_bars.py nexus2/tests/test_cases/intraday/ross_mlec_20260220.json 09:30 10:00

    # Show premarket bars
    python scripts/peek_bars.py nexus2/tests/test_cases/intraday/ross_mlec_20260220.json 07:00 09:30

    # Show a single minute
    python scripts/peek_bars.py nexus2/tests/test_cases/intraday/ross_mlec_20260220.json 09:30 09:31
"""

import json
import sys
from pathlib import Path


def peek_bars(json_path: str, start_time: str = "09:25", end_time: str = "09:45"):
    """Display bars from a test case file within a time range."""
    path = Path(json_path)
    if not path.exists():
        # Try relative to test_cases/intraday
        alt = Path("nexus2/tests/test_cases/intraday") / json_path
        if alt.exists():
            path = alt
        else:
            print(f"Error: File not found: {json_path}")
            sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    # Print metadata - check both top-level and nested structures
    meta = data.get("metadata", data.get("premarket", {}))
    symbol = data.get("symbol", meta.get("symbol", "?"))
    date = data.get("date", meta.get("date", "?"))
    pmh = meta.get("pmh", data.get("pmh", "?"))
    gap = meta.get("gap_percent", data.get("gap_percent", "?"))
    catalyst = meta.get("catalyst", meta.get("catalyst_type", data.get("catalyst_type", "?")))

    print(f"\n{'='*70}")
    print(f"  {symbol} | {date} | PMH: ${pmh} | Gap: {gap}% | Catalyst: {catalyst}")
    print(f"  Time range: {start_time} - {end_time}")
    print(f"{'='*70}")

    # Filter bars
    bars = [b for b in data.get("bars", []) if start_time <= b["t"] <= end_time]

    if not bars:
        print(f"\n  No bars found between {start_time} and {end_time}")
        total = len(data.get("bars", []))
        if total > 0:
            first = data["bars"][0]["t"]
            last = data["bars"][-1]["t"]
            print(f"  Available range: {first} - {last} ({total} bars)")
        sys.exit(0)

    # Print header
    print(f"\n  {'Time':<8} {'Open':>8} {'High':>8} {'Low':>8} {'Close':>8} {'Volume':>10}")
    print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")

    # Track high/low for summary
    session_high = 0
    session_low = float("inf")
    total_vol = 0

    for b in bars:
        t = b["t"]
        o = b["o"]
        h = b["h"]
        l = b["l"]
        c = b["c"]
        v = b.get("v", 0)

        session_high = max(session_high, h)
        session_low = min(session_low, l)
        total_vol += v

        # Color hint: green if close >= open, red otherwise
        arrow = "▲" if c >= o else "▼"

        print(f"  {t:<8} {o:>8.2f} {h:>8.2f} {l:>8.2f} {c:>8.2f} {v:>10,} {arrow}")

    print(f"\n  Summary: {len(bars)} bars | High: ${session_high:.2f} | Low: ${session_low:.2f} | Volume: {total_vol:,}")

    # Show premarket vs market split
    pre_bars = [b for b in bars if b["t"] < "09:30"]
    mkt_bars = [b for b in bars if b["t"] >= "09:30"]
    if pre_bars and mkt_bars:
        print(f"  Split: {len(pre_bars)} premarket + {len(mkt_bars)} market bars")

    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    json_path = sys.argv[1]
    start_time = sys.argv[2] if len(sys.argv) > 2 else "09:25"
    end_time = sys.argv[3] if len(sys.argv) > 3 else "09:45"

    peek_bars(json_path, start_time, end_time)


if __name__ == "__main__":
    main()
