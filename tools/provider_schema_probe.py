"""
File: /tools/provider_schema_probe.py
Version: 1.1.0
Author: Nexus Project (Clay + Copilot)

Purpose:
    Provider schema validation probe.
    Ensures that the Quote object returned by AlpacaProvider
    matches the expected Nexus Quote schema.

    This protects against:
    - Provider API changes
    - Missing or null fields
    - Type mismatches
    - Normalization errors

Usage:
    python provider_schema_probe.py
"""

from datetime import datetime
from typing import List, get_origin, get_args

from nexus_pipeline.providers.alpaca_provider import AlpacaProvider
from core.quote_schema import Quote


# ---------------------------------------------------------
# Expected Schema (based on Quote dataclass)
# ---------------------------------------------------------
EXPECTED_FIELDS = {
    "symbol": str,
    "bid_price": float,
    "bid_size": int,
    "bid_exchange": str,
    "ask_price": float,
    "ask_size": int,
    "ask_exchange": str,
    "conditions": List[str],
    "timestamp": str,
    "tape": str,
}


def log(msg: str):
    """Timestamped logger."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}")


def validate_quote(quote: Quote) -> List[str]:
    """
    Validate a Quote instance against EXPECTED_FIELDS.
    Returns a list of errors (empty list = PASS).
    """
    errors = []

    for field_name, expected_type in EXPECTED_FIELDS.items():
        value = getattr(quote, field_name, None)

        # Missing field
        if value is None:
            errors.append(f"Missing field: {field_name}")
            continue

        # Handle List[str] type
        if get_origin(expected_type) is list:
            if not isinstance(value, list):
                errors.append(
                    f"Field '{field_name}' wrong type: expected List[str], got {type(value).__name__}"
                )
            else:
                # Validate list element types
                elem_type = get_args(expected_type)[0]
                for elem in value:
                    if not isinstance(elem, elem_type):
                        errors.append(
                            f"Field '{field_name}' contains non-{elem_type.__name__} element: {elem}"
                        )
            continue

        # Normal type check
        if not isinstance(value, expected_type):
            errors.append(
                f"Field '{field_name}' wrong type: expected {expected_type.__name__}, got {type(value).__name__}"
            )

    return errors


def run_schema_probe(symbol: str = "AAPL"):
    """
    Calls AlpacaProvider.get_latest_quote() and validates the Quote object.
    """
    provider = AlpacaProvider()

    print("\n=== Provider Schema Probe ===")
    print(f"Provider: {provider.__class__.__name__}")
    print(f"Symbol: {symbol}\n")

    try:
        quote = provider.get_latest_quote(symbol)
    except Exception as e:
        log(f"ERROR: Provider call failed: {e}")
        print("\n=== SCHEMA PROBE FAILED (provider error) ===\n")
        return

    print("Quote Object:")
    print(quote)
    print("\nValidating schema...\n")

    errors = validate_quote(quote)

    if not errors:
        print("=== SCHEMA PROBE PASSED ===")
        print("All fields present, correct types, no nulls.\n")
    else:
        print("=== SCHEMA PROBE FAILED ===")
        for err in errors:
            print(" -", err)
        print("\n")


if __name__ == "__main__":
    run_schema_probe("AAPL")