"""
File: nexus_pipeline/tradingview_client.py
Version: 1.1.0
Author: Clay & Copilot

Purpose:
    Provide a stable TradingView JSON API client for:
        • Premarket movers (existing)
        • Regular-hours movers (new in v1.1.0)

    This module is used by Stage 1 (scan_pre_market.py) as a fallback
    when FMP data is insufficient.

Notes:
    - Uses TradingView's official screener backend endpoint.
    - No HTML scraping, no Selenium, no websockets.
    - Returns a list of dicts compatible with RawScanRecord normalization.
"""

import requests
import logging

TV_ENDPOINT = "https://scanner.tradingview.com/america/scan"

# ------------------------------------------------------------------------------
# PREMARKET PAYLOAD (unchanged)
# ------------------------------------------------------------------------------
PREMARKET_PAYLOAD = {
    "filter": [
        {"left": "market_cap_basic", "operation": "nempty"},
        {"left": "type", "operation": "in_range", "right": ["stock"]},
        {"left": "is_primary", "operation": "equal", "right": True},
        {"left": "premarket_change", "operation": "greater", "right": 0}
    ],
    "options": {"lang": "en"},
    "symbols": {"query": {"types": []}, "tickers": []},
    "columns": [
        "name",
        "premarket_price",
        "premarket_change",
        "volume",
        "close",
        "description"
    ],
    "sort": {"sortBy": "premarket_change", "sortOrder": "desc"},
    "range": [0, 50]
}


def fetch_premarket_movers(logger: logging.Logger):
    """Return a list of dicts with symbol, price, change %, volume."""
    try:
        resp = requests.post(TV_ENDPOINT, json=PREMARKET_PAYLOAD, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"TradingView premarket request failed: {e}")
        return []

    results = []
    rows = data.get("data", [])

    for row in rows:
        try:
            symbol_full = row.get("s")
            symbol = symbol_full.split(":")[1] if ":" in symbol_full else symbol_full

            d = row.get("d", [])
            price = d[1]
            change_pct = d[2]
            volume = d[3]

            results.append({
                "symbol": symbol,
                "price": price,
                "changePercent": change_pct,
                "volume": volume
            })
        except Exception:
            continue

    logger.info(f"TradingView returned {len(results)} premarket movers.")
    return results


# ------------------------------------------------------------------------------
# REGULAR-HOURS PAYLOAD (new in v1.1.0)
# ------------------------------------------------------------------------------
REGULAR_PAYLOAD = {
    "filter": [
        {"left": "market_cap_basic", "operation": "nempty"},
        {"left": "type", "operation": "in_range", "right": ["stock"]},
        {"left": "is_primary", "operation": "equal", "right": True},
        {"left": "change_percent", "operation": "greater", "right": 0}
    ],
    "options": {"lang": "en"},
    "symbols": {"query": {"types": []}, "tickers": []},
    "columns": [
        "name",
        "close",
        "change",
        "change_percent",
        "volume"
    ],
    "sort": {"sortBy": "change_percent", "sortOrder": "desc"},
    "range": [0, 100]
}


def fetch_regular_movers(logger: logging.Logger):
    """Return a list of dicts with symbol, price, change %, volume (regular-hours)."""
    try:
        resp = requests.post(TV_ENDPOINT, json=REGULAR_PAYLOAD, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"TradingView regular-hours request failed: {e}")
        return []

    results = []
    rows = data.get("data", [])

    for row in rows:
        try:
            symbol_full = row.get("s")
            symbol = symbol_full.split(":")[1] if ":" in symbol_full else symbol_full

            d = row.get("d", [])
            price = d[1]          # close
            change_pct = d[3]     # change_percent
            volume = d[4]

            results.append({
                "symbol": symbol,
                "price": price,
                "changePercent": change_pct,
                "volume": volume
            })
        except Exception:
            continue

    logger.info(f"TradingView returned {len(results)} regular-hours movers.")
    return results