"""
File: nexus_pipeline/adapters/alpaca_provider.py
Version: 1.2.0
Author: Nexus Project (Clay + Copilot)

Purpose:
    Alpaca market data provider adapter.
    - Fetches latest quote data from Alpaca
    - Normalizes Alpaca's cryptic schema into descriptive fields
    - Returns a strongly‑typed Quote object
    - Includes a diagnostic ping() for debugging and latency testing
"""

import requests
from core.quote_schema import Quote
from config import ALPACA_KEY_A, ALPACA_SECRET_A, ALPACA_BASE_DATA_URL


class AlpacaProvider:
    BASE_URL = ALPACA_BASE_DATA_URL
    API_KEY = ALPACA_KEY_A
    API_SECRET = ALPACA_SECRET_A

    # ---------------------------------------------------------
    # Normalization Layer → returns a Quote object directly
    # ---------------------------------------------------------
    def normalize_quote(self, raw: dict) -> Quote:
        """Convert Alpaca's cryptic quote schema into a strongly‑typed Quote."""
        q = raw["quote"]

        return Quote(
            symbol=raw["symbol"],
            bid_price=float(q["bp"]),
            bid_size=int(q["bs"]),
            bid_exchange=q["bx"],
            ask_price=float(q["ap"]),
            ask_size=int(q["as"]),
            ask_exchange=q["ax"],
            conditions=q["c"],
            timestamp=q["t"],
            tape=q["z"],
        )

    # ---------------------------------------------------------
    # Production Method
    # ---------------------------------------------------------
    def get_latest_quote(self, symbol: str) -> Quote:
        """Return the latest normalized quote for a symbol."""
        url = f"{self.BASE_URL}/stocks/{symbol}/quotes/latest"
        headers = {
            "APCA-API-KEY-ID": self.API_KEY,
            "APCA-API-SECRET-KEY": self.API_SECRET,
        }

        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()

        raw = response.json()
        return self.normalize_quote(raw)

    # ---------------------------------------------------------
    # Diagnostic Method
    # ---------------------------------------------------------
    def ping(self) -> int:
        """
        Diagnostic-only method.
        Returns status code and prints raw response for debugging.
        """
        url = f"{self.BASE_URL}/stocks/AAPL/quotes/latest"
        headers = {
            "APCA-API-KEY-ID": self.API_KEY,
            "APCA-API-SECRET-KEY": self.API_SECRET,
        }

        print("\n--- Alpaca Diagnostic ---")
        print("URL:", url)

        try:
            response = requests.get(url, headers=headers, timeout=5)
            print("Status:", response.status_code)
            print("Body:", response.text[:200])
            print("--- End Diagnostic ---\n")
            return response.status_code
        except Exception as e:
            print("Exception:", e)
            print("--- End Diagnostic (Exception) ---\n")
            return 0