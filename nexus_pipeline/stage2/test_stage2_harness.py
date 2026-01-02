"""
Stage 2 Diagnostic Harness
Version: 1.0.0

Purpose:
    Run Stage 2 enrichment independently and inspect the full enriched context
    for a list of symbols. This is the fastest way to validate adapter wiring,
    schema correctness, and enrichment behavior.
"""

import json
from nexus_pipeline.stage2.build_contexts import ContextBuilder


def pretty(obj):
    print(json.dumps(obj, indent=4, sort_keys=True))


def run_test(symbols):
    print("\n=== Stage 2 Diagnostic Harness ===")
    print(f"Testing {len(symbols)} symbols\n")

    s2 = ContextBuilder(logger=None)

    for sym in symbols:
        print("\n" + "=" * 80)
        print(f"ENRICHING: {sym}")
        print("=" * 80)

        ctx = s2.build([sym])[0]
        pretty(ctx)


if __name__ == "__main__":
    # You can modify this list anytime
    test_symbols = [
        "SMX",
        "MBAI",
        "BEAT",
        "ENGN",
        "QNRX",
        "NVDA",
        "TSLA",
        "AAPL",
        "SMCI",
        "AMD",
        "META",
    ]

    run_test(test_symbols)