"""
Scanner Pulse Check — Verify Ross's ticker was detected by our scanner.

Usage:
  python scripts/scanner_pulse_check.py NDRA 2026-02-26
  python scripts/scanner_pulse_check.py ENVB 2026-02-19

Queries VPS /data/warrior-scan-history endpoint to check if the scanner
found and graded the stock on the given trade date.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")


def check_scanner(symbol: str, trade_date: str) -> None:
    """Query VPS for scanner results on a symbol + date."""
    url = (
        f"{BASE_URL}/data/warrior-scan-history"
        f"?symbol={symbol.upper()}"
        f"&date_from={trade_date}"
        f"&date_to={trade_date}"
        f"&limit=50"
    )

    print(f"\n  Scanner Pulse Check: {symbol.upper()} on {trade_date}")
    print(f"  Querying: {BASE_URL}/data/warrior-scan-history")
    print(f"  {'─' * 50}")

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  ❌ Failed to connect: {e}")
        print(f"  scanner_result: CONNECTION_FAILED")
        sys.exit(2)

    entries = data.get("entries", [])
    total = data.get("total", 0)

    if total == 0:
        print(f"  ⚠️  NOT FOUND in scanner DB")
        print(f"  Scanner may not have been running, or ticker didn't appear in gainers.")
        print(f"\n  scanner_result: \"NOT_IN_DB\"")
        sys.exit(1)

    # Show all scan results for this symbol on that date
    passes = [e for e in entries if e.get("result") == "PASS"]
    fails = [e for e in entries if e.get("result") == "FAIL"]

    print(f"  Found {total} scan record(s): {len(passes)} PASS, {len(fails)} FAIL")
    print()

    for e in entries:
        result = e.get("result", "?")
        score = e.get("score", "—")
        gap = e.get("gap_pct")
        rvol = e.get("rvol")
        catalyst = e.get("catalyst") or e.get("catalyst_type") or "—"
        reason = e.get("reason") or ""
        ts = e.get("timestamp", "")
        flt = e.get("float") or "—"

        icon = "✅" if result == "PASS" else "❌"
        gap_str = f"{gap:.1f}%" if gap is not None else "—"
        rvol_str = f"{rvol:.1f}x" if rvol is not None else "—"

        print(f"  {icon} {result} | score={score} | gap={gap_str} | rvol={rvol_str} | float={flt} | catalyst={catalyst}")
        if reason:
            print(f"     └─ reason: {reason}")
        print(f"     └─ time: {ts}")

    # Generate YAML snippet
    print(f"\n  {'─' * 50}")
    best = passes[0] if passes else entries[0]
    r = best.get("result", "?")
    s = best.get("score", "?")
    g = f"{best['gap_pct']:.1f}%" if best.get("gap_pct") is not None else "?"
    rv = f"{best['rvol']:.1f}x" if best.get("rvol") is not None else "?"
    cat = best.get("catalyst") or best.get("catalyst_type") or "?"
    rsn = best.get("reason") or ""

    if r == "PASS":
        yaml_val = f"PASS (score={s}, gap={g}, rvol={rv}, catalyst={cat})"
    else:
        yaml_val = f"FAIL (reason={rsn})"

    print(f"  YAML snippet:")
    print(f'    scanner_result: "{yaml_val}"')
    print()

    sys.exit(0 if passes else 1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/scanner_pulse_check.py SYMBOL YYYY-MM-DD")
        print("Example: python scripts/scanner_pulse_check.py NDRA 2026-02-26")
        sys.exit(1)

    check_scanner(sys.argv[1], sys.argv[2])
