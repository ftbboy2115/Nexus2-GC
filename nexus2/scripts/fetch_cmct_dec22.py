"""Fetch CMCT Dec 22, 2025 intraday data for retrospective test."""
import os
from pathlib import Path
from dotenv import load_dotenv
import httpx
import json

# Load .env from project root
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)
api_key = os.getenv("FMP_API_KEY")

symbol = "CMCT"
date = "2025-12-22"

url = f"https://financialmodelingprep.com/api/v3/historical-chart/1min/{symbol}?from={date}&to={date}&apikey={api_key}"

resp = httpx.get(url, timeout=30)
data = list(reversed(resp.json()))  # FMP returns newest first

# Summary stats
high = max(c["high"] for c in data)
low = min(c["low"] for c in data)
open_price = data[0]["open"]
close_price = data[-1]["close"]
total_volume = sum(c["volume"] for c in data)

print(f"=== CMCT {date} ===")
print(f"Open: ${open_price:.2f} | High: ${high:.2f} | Low: ${low:.2f} | Close: ${close_price:.2f}")
print(f"Total Volume: {total_volume:,}")

# Find when Ross's entry ($4.65) was hit
entry_price = 4.65
for i, c in enumerate(data):
    if c["high"] >= entry_price:
        print(f"\nFirst candle above ${entry_price}: {c['date']}")
        print(f"  High: ${c['high']:.2f}, Low: ${c['low']:.2f}, Close: ${c['close']:.2f}")
        break
else:
    print(f"\nPrice never reached ${entry_price}")

# Show key moments
print("\n=== First 10 candles (market open) ===")
for c in data[:10]:
    print(f"  {c['date']} O:{c['open']:.2f} H:{c['high']:.2f} L:{c['low']:.2f} C:{c['close']:.2f} V:{c['volume']:,}")

# Find HOD candle
hod_candle = max(data, key=lambda c: c["high"])
print(f"\n=== High of Day ===")
print(f"  {hod_candle['date']} High: ${hod_candle['high']:.2f}")

# Save full data for test case
output_file = f"data/cmct_{date.replace('-', '')}_1min.json"
with open(output_file, "w") as f:
    json.dump(data, f, indent=2)
print(f"\nSaved {len(data)} candles to {output_file}")
