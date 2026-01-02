# core/diagnostic_strategy_preview.py

"""
Diagnostic Strategy Preview (v1.0.0)
-----------------------------------
Quick utility to validate Strategy Engine v1.6.0 with RS v2 integration.

- Builds a few sample strategies using the Strategy Engine
- Prints enriched strategy objects (without logging them)
- Confirms RS v2 fields are attached correctly
"""

import json
from core.strategy_engine import build_strategy


def pretty(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)


def run_preview():
    print("\n=== Strategy Engine Diagnostic Preview ===\n")

    samples = [
        ("AAPL", "EP", {"reason": "Test EP", "pivot": None, "stop": None}),
        ("NVDA", "HTF", {"reason": "Test HTF"}),
        ("TSLA", "TREND", {"reason": "Test Trend"}),
    ]

    for symbol, setup, data in samples:
        print(f"\n--- Building strategy for {symbol} ({setup}) ---")
        strategy = build_strategy(symbol, setup, data)
        print(pretty(strategy))


if __name__ == "__main__":
    run_preview()