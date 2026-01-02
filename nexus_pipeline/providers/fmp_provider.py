"""
File: nexus_pipeline/adapters/fmp_provider.py
Version: 1.0.0
Author: Nexus Project (Clay + Copilot)

Purpose:
    FMP market data provider adapter.
    - Primary data provider for Nexus
    - Fetches latest quote data from FMP
    - Normalizes FMP's schema into the unified Quote object
    - Includes a diagnostic ping() for latency testing
"""

import requests
from core.quote_schema import Quote
from config import FMP_KEY


class FMPProvider:
    BASE_URL = "https://financialmodelingprep.com/api/v3"
    API_KEY = FMP_KEY

    # ---------------------------------------------------------
    # Normalization Layer → returns a Quote object
    # ---------------------------------------------------------
    def normalize_quote(self, raw: dict) -> Quote:
        """
        Convert FMP's quote schema into a strongly‑typed Quote.
        FMP does not provide bid/ask, so we synthesize minimal values.
        """
        price = float(raw["price"])
        symbol = raw["symbol"]
        timestamp = str(raw.get("timestamp", ""))

        return Quote(
            symbol=symbol,
            bid_price=price,
            bid_size=0,
            bid_exchange="FMP",
            ask_price=price,
            ask_size=0,
            ask_exchange="FMP",
            conditions=[],
            timestamp=timestamp,
            tape="FMP",
        )

    # ---------------------------------------------------------
    # Production Method
    # ---------------------------------------------------------
    def get_latest_quote(self, symbol: str) -> Quote:
        """Return the latest normalized quote for a symbol."""
        url = f"{self.BASE_URL}/quote/{symbol}?apikey={self.API_KEY}"

        response = requests.get(url, timeout=5)
        response.raise_for_status()

        data = response.json()

        if not data or not isinstance(data, list):
            raise ValueError(f"Unexpected FMP response format: {data}")

        return self.normalize_quote(data[0])

    # ---------------------------------------------------------
    # Diagnostic Method
    # ---------------------------------------------------------
    def ping(self) -> int:
        """
        Diagnostic-only method.
        Returns status code for a lightweight FMP request.
        """
        url = f"{self.BASE_URL}/quote/AAPL?apikey={self.API_KEY}"

        try:
            response = requests.get(url, timeout=5)
            return response.status_code
        except Exception:
            return 0