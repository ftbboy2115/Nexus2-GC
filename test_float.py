#!/usr/bin/env python3
"""Test FMP float endpoint - using stable API."""
import httpx
from nexus2 import config as app_config

symbols = ["GITS", "OCC", "NUWE", "RR"]

for sym in symbols:
    try:
        response = httpx.get(
            "https://financialmodelingprep.com/stable/shares-float",
            params={"symbol": sym, "apikey": app_config.FMP_API_KEY},
            timeout=5.0,
        )
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            float_val = data[0].get("floatShares", "missing")
            print(f"{sym}: {float_val:,}" if isinstance(float_val, (int, float)) else f"{sym}: {float_val}")
        else:
            print(f"{sym}: No data returned")
    except Exception as e:
        print(f"{sym}: Error - {e}")
