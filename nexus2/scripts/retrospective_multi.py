"""
Multi-Case Retrospective Test

Tests OPTX, ACON, FLYX with Ross-aligned logic:
- Stop = ORB/entry candle low (not fixed 15c)
- Scaling enabled (50% adds)
"""
import json
import os
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from dotenv import load_dotenv
import httpx

# Load .env
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)
fmp_key = os.getenv("FMP_API_KEY")

# Data directory
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "test_case_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Test cases (verified FMP data)
TEST_CASES = [
    {
        "symbol": "OPTX",
        "date": "2026-01-06",
        "pmh": 3.50,  # Estimated PMH break
        "ross_pnl": 3604.91,  # From transcript
        "ross_traded": True,
    },
    {
        "symbol": "ACON",
        "date": "2026-01-08",
        "pmh": 8.30,  # Estimated PMH break
        "ross_pnl": None,  # Ross did NOT trade
        "ross_traded": False,
    },
    {
        "symbol": "FLYX",
        "date": "2026-01-08",
        "pmh": 6.20,  # Estimated PMH break
        "ross_pnl": None,  # Ross did NOT trade
        "ross_traded": False,
    },
]

# Bot config
BOT_CONFIG = {
    "risk_per_trade": 250,
    "use_candle_low_stop": True,
    "stop_buffer_cents": 5,
    "enable_scaling": True,
    "scale_size_pct": 50,
    "max_scale_count": 2,
}


def fetch_intraday(symbol: str, date: str) -> list:
    """Fetch 1-min candles from FMP."""
    cache_file = DATA_DIR / f"{symbol}_{date.replace('-', '')}_1min.json"
    
    if cache_file.exists():
        with open(cache_file) as f:
            data = json.load(f)
            return data.get("candles", [])
    
    url = f"https://financialmodelingprep.com/api/v3/historical-chart/1min/{symbol}?from={date}&to={date}&apikey={fmp_key}"
    resp = httpx.get(url, timeout=30)
    raw = resp.json()
    
    if not isinstance(raw, list) or len(raw) == 0:
        return []
    
    candles = list(reversed(raw))  # Chronological order
    
    # Cache it
    fmp_stats = {
        "open": candles[0]["open"],
        "high": max(c["high"] for c in candles),
        "low": min(c["low"] for c in candles),
        "close": candles[-1]["close"],
        "volume": sum(c["volume"] for c in candles),
    }
    with open(cache_file, "w") as f:
        json.dump({"candles": candles, "fmp_stats": fmp_stats}, f, indent=2)
    
    return candles


def run_test(case: dict) -> dict:
    """Run retrospective test for a single case."""
    symbol = case["symbol"]
    date = case["date"]
    pmh = case["pmh"]
    
    print(f"\n{'='*60}")
    print(f"{symbol} - {date}")
    print("=" * 60)
    
    candles = fetch_intraday(symbol, date)
    if not candles:
        print("  ERROR: No candle data available")
        return {"symbol": symbol, "error": "no_data"}
    
    hod = max(c["high"] for c in candles)
    lod = min(c["low"] for c in candles)
    
    print(f"  Candles: {len(candles)} | HOD: ${hod:.2f} | LOD: ${lod:.2f}")
    
    # Find entry candle (PMH break)
    entry_candle = None
    entry_candle_idx = None
    for i, c in enumerate(candles):
        if c["high"] >= pmh:
            entry_candle = c
            entry_candle_idx = i
            break
    
    if not entry_candle:
        print(f"  PMH (${pmh}) never reached - no entry")
        return {"symbol": symbol, "error": "pmh_not_reached"}
    
    print(f"  Entry: PMH ${pmh} at {entry_candle['date']}")
    
    # Stop calculation (candle low - buffer)
    entry_candle_low = entry_candle["low"]
    stop_price = entry_candle_low - BOT_CONFIG["stop_buffer_cents"] / 100
    risk_per_share = pmh - stop_price
    
    print(f"  Entry candle low: ${entry_candle_low:.2f}")
    print(f"  Stop: ${stop_price:.2f} (low - 5c)")
    print(f"  Risk/share: ${risk_per_share:.2f}")
    
    # Position sizing
    initial_shares = int(BOT_CONFIG["risk_per_trade"] / risk_per_share)
    print(f"  Initial shares: {initial_shares}")
    
    # Scaling
    scale_adds = []
    if BOT_CONFIG["enable_scaling"]:
        last_high = pmh
        scale_count = 0
        for i in range(entry_candle_idx + 5, len(candles)):
            c = candles[i]
            if c["high"] > last_high and scale_count < BOT_CONFIG["max_scale_count"]:
                add_shares = int(initial_shares * BOT_CONFIG["scale_size_pct"] / 100)
                scale_adds.append({
                    "time": c["date"],
                    "price": c["high"],
                    "shares": add_shares,
                })
                last_high = c["high"]
                scale_count += 1
    
    total_shares = initial_shares + sum(a["shares"] for a in scale_adds)
    print(f"  Scaling: {len(scale_adds)} adds -> {total_shares} total shares")
    
    # P&L at HOD
    pnl = initial_shares * (hod - pmh)
    for add in scale_adds:
        pnl += add["shares"] * (hod - add["price"])
    
    print(f"  Theoretical P&L (HOD exit): ${pnl:.2f}")
    
    if case["ross_traded"] and case["ross_pnl"]:
        print(f"  Ross P&L: ${case['ross_pnl']:,.2f}")
        gap = case["ross_pnl"] - pnl
        print(f"  Gap: ${gap:,.2f}")
    else:
        print(f"  Ross did NOT trade this setup")
    
    return {
        "symbol": symbol,
        "entry_price": pmh,
        "stop": stop_price,
        "initial_shares": initial_shares,
        "total_shares": total_shares,
        "scales": len(scale_adds),
        "theoretical_pnl": pnl,
        "ross_pnl": case["ross_pnl"],
        "ross_traded": case["ross_traded"],
    }


# Run all tests
print("=" * 60)
print("MULTI-CASE RETROSPECTIVE TEST")
print("(Ross-aligned stop & scaling logic)")
print("=" * 60)

results = []
for case in TEST_CASES:
    result = run_test(case)
    results.append(result)

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

print("\n| Symbol | Entry | Stop | Shares | Scales | Bot P&L | Ross P&L |")
print("|--------|-------|------|--------|--------|---------|----------|")
for r in results:
    if "error" in r:
        print(f"| {r['symbol']} | ERROR: {r['error']} |")
    else:
        ross = f"${r['ross_pnl']:,.0f}" if r['ross_pnl'] else "N/A"
        print(f"| {r['symbol']} | ${r['entry_price']:.2f} | ${r['stop']:.2f} | {r['total_shares']} | {r['scales']} | ${r['theoretical_pnl']:.0f} | {ross} |")

print("\n" + "=" * 60)
print("COMPLETE")
print("=" * 60)
