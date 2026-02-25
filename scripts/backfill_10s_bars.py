"""
Backfill 10-second bar data from Polygon for all test cases.

Reads ross_*.json files from tests/test_cases/intraday/ to determine
symbol/date pairs. Fetches 10s aggregates from Polygon for each case
that doesn't already have a *_10s.json sidecar file.

Usage:
    cd Nexus
    python scripts/backfill_10s_bars.py [--dry-run] [--symbol SYMBOL]

Output files match the existing 10s format:
    {symbol}_{YYYYMMDD}_10s.json in tests/test_cases/intraday/
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Add project root to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env for API key
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import httpx

# ── Constants ──────────────────────────────────────────────────────────
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
POLYGON_BASE_URL = "https://api.polygon.io"
INTRADAY_DIR = PROJECT_ROOT / "nexus2" / "tests" / "test_cases" / "intraday"
ET = ZoneInfo("US/Eastern")
UTC = timezone.utc

# Developer tier ($200/mo) = unlimited API calls, just a small courtesy delay
RATE_LIMIT_SECONDS = 0.5

# Polygon returns max 50,000 results per call
POLYGON_LIMIT = 50000


def discover_test_cases() -> list[dict]:
    """
    Scan intraday/ for ross_*.json files and extract symbol + date.
    Format: ross_{symbol}_{YYYYMMDD}.json
    """
    cases = []
    pattern = re.compile(r"^ross_([a-z]+)_(\d{8})\.json$", re.IGNORECASE)

    for f in sorted(INTRADAY_DIR.iterdir()):
        m = pattern.match(f.name)
        if m:
            symbol = m.group(1).upper()
            date_str = m.group(2)
            cases.append({
                "symbol": symbol,
                "date": date_str,
                "source_file": f.name,
            })
    return cases


def has_10s_file(symbol: str, date_str: str) -> bool:
    """Check if 10s sidecar file already exists."""
    fname = f"{symbol.lower()}_{date_str}_10s.json"
    return (INTRADAY_DIR / fname).exists()


def fetch_10s_bars(symbol: str, date_str: str) -> list[dict] | None:
    """
    Fetch 10-second bars from Polygon for a single trading day.

    Returns list of bar dicts in the output format, or None on failure.
    The Polygon API may not return bars for every 10-second interval —
    only intervals with actual trades get a bar (same as existing files).
    """
    if not POLYGON_API_KEY:
        print("  ❌ POLYGON_API_KEY not set!")
        return None

    # Format date as YYYY-MM-DD for Polygon
    ymd = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    url = f"{POLYGON_BASE_URL}/v2/aggs/ticker/{symbol}/range/10/second/{ymd}/{ymd}"
    params = {
        "apiKey": POLYGON_API_KEY,
        "limit": POLYGON_LIMIT,
        "sort": "asc",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        print(f"  ❌ HTTP {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        print(f"  ❌ Request failed: {e}")
        return None

    if data.get("status") != "OK":
        print(f"  ❌ Polygon status: {data.get('status')} — {data.get('error', 'unknown')}")
        return None

    results = data.get("results", [])
    if not results:
        print(f"  ⚠️  No bars returned (stock may not have traded that day)")
        return None

    # Convert to output format
    bars = []
    for r in results:
        # Polygon timestamp is in milliseconds since epoch (UTC)
        ts_ms = r.get("t", 0)
        dt_utc = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
        dt_et = dt_utc.astimezone(ET)

        bars.append({
            "t": dt_et.strftime("%H:%M:%S"),
            "o": round(r.get("o", 0), 4),
            "h": round(r.get("h", 0), 4),
            "l": round(r.get("l", 0), 4),
            "c": round(r.get("c", 0), 4),
            "v": r.get("v", 0),
        })

    # Check if we got truncated (at the limit)
    if len(results) >= POLYGON_LIMIT:
        print(f"  ⚠️  Hit Polygon limit ({POLYGON_LIMIT}), data may be truncated!")

    return bars


def save_10s_file(symbol: str, date_str: str, bars: list[dict]) -> Path:
    """Save 10s bars in the standard sidecar format."""
    ymd = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    fname = f"{symbol.lower()}_{date_str}_10s.json"
    fpath = INTRADAY_DIR / fname

    output = {
        "symbol": symbol,
        "date": ymd,
        "timeframe": "10s",
        "timezone": "US/Eastern",
        "bar_count": len(bars),
        "bars": bars,
    }

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    return fpath


def main():
    parser = argparse.ArgumentParser(description="Backfill 10s bar data from Polygon")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched without fetching")
    parser.add_argument("--symbol", type=str, help="Only backfill a specific symbol (case-insensitive)")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if 10s file already exists")
    args = parser.parse_args()

    print("=" * 60)
    print("  10-Second Bar Backfill from Polygon")
    print("=" * 60)
    print()

    if not POLYGON_API_KEY:
        print("❌ POLYGON_API_KEY not set in environment. Set it in .env")
        sys.exit(1)

    # Discover test cases
    cases = discover_test_cases()
    print(f"Found {len(cases)} ross_*.json test cases in intraday/")
    print()

    # Filter by symbol if specified
    if args.symbol:
        cases = [c for c in cases if c["symbol"].upper() == args.symbol.upper()]
        print(f"Filtered to {len(cases)} cases for symbol {args.symbol.upper()}")
        print()

    # Partition into already-have vs need-to-fetch
    already_have = []
    to_fetch = []
    for case in cases:
        if has_10s_file(case["symbol"], case["date"]) and not args.force:
            already_have.append(case)
        else:
            to_fetch.append(case)

    print(f"Already have 10s data: {len(already_have)}")
    print(f"Need to fetch:        {len(to_fetch)}")
    print()

    if not to_fetch:
        print("✅ All test cases already have 10s data!")
        return

    if args.dry_run:
        print("DRY RUN — would fetch the following:")
        for case in to_fetch:
            print(f"  • {case['symbol']} {case['date']} ({case['source_file']})")
        print()
        estimated_time = len(to_fetch) * RATE_LIMIT_SECONDS
        print(f"Estimated time: {estimated_time // 60}m {estimated_time % 60}s")
        return

    # Fetch and save
    created = []
    failed = []
    total_size = 0

    for i, case in enumerate(to_fetch, 1):
        sym = case["symbol"]
        date = case["date"]
        print(f"[{i}/{len(to_fetch)}] Fetching {sym} {date}...", end=" ", flush=True)

        bars = fetch_10s_bars(sym, date)
        if bars:
            fpath = save_10s_file(sym, date, bars)
            fsize = fpath.stat().st_size
            total_size += fsize
            created.append({
                "symbol": sym,
                "date": date,
                "bars": len(bars),
                "size_kb": round(fsize / 1024, 1),
            })
            print(f"✅ {len(bars)} bars, {round(fsize / 1024, 1)} KB")
        else:
            failed.append({"symbol": sym, "date": date})
            print(f"❌ FAILED")

        # Rate limit (skip on last item)
        if i < len(to_fetch):
            print(f"    ⏳ Waiting {RATE_LIMIT_SECONDS}s for rate limit...", end=" ", flush=True)
            time.sleep(RATE_LIMIT_SECONDS)
            print("done")

    # Summary
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"Created: {len(created)} files")
    print(f"Failed:  {len(failed)} files")
    print(f"Total size: {round(total_size / 1024, 1)} KB ({round(total_size / (1024*1024), 2)} MB)")
    print()

    if created:
        print("Created files:")
        for c in created:
            print(f"  ✅ {c['symbol']}_{c['date']}_10s.json — {c['bars']} bars, {c['size_kb']} KB")
        print()

    if failed:
        print("Failed files:")
        for f in failed:
            print(f"  ❌ {f['symbol']}_{f['date']}")
        print()

    # Return counts for status report
    return {
        "created": len(created),
        "failed": len(failed),
        "total_size_kb": round(total_size / 1024, 1),
        "details": created,
        "failures": failed,
    }


if __name__ == "__main__":
    main()
