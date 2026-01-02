"""
File: nexus_pipeline/catalyst_engine/news_client.py
Version: 1.1.0
Author: Clay & Copilot

Title:
    Catalyst Engine — News Client

Purpose:
    - Fetch news from external providers (starting with FMP).
    - Normalize raw news payloads into a consistent structure.
    - Deduplicate headlines.
    - Provide clean, timestamped catalyst candidates to the Catalyst Engine.

Notes:
    - Supports FMP as the initial provider.
    - Additional providers (Benzinga, TradingView, etc.) can be added in v1.2.0+.
"""

import requests
from typing import List, Dict, Any
from datetime import datetime, timezone


class NewsClient:
    def __init__(self, api_key: str, logger):
        self.api_key = api_key
        self.logger = logger
        self.endpoint = "https://financialmodelingprep.com/api/v3/stock_news"

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch and normalize news for a given symbol.

        Returns a list of dicts:
            {
                "symbol": str,
                "headline": str,
                "source": str,
                "published_utc": str,
                "url": str,
                "raw": dict
            }
        """
        raw = self._fetch_fmp_news(symbol, limit)
        normalized = [self._normalize_fmp_item(item) for item in raw]
        normalized = [n for n in normalized if n]  # drop None

        # Deduplicate by headline
        seen = set()
        deduped = []
        for item in normalized:
            h = item["headline"]
            if h not in seen:
                seen.add(h)
                deduped.append(item)

        self.logger.info(
            f"NewsClient: {symbol} → {len(deduped)} normalized news items (from {len(raw)} raw)."
        )
        return deduped

    # ----------------------------------------------------------------------
    # FMP Fetcher
    # ----------------------------------------------------------------------
    def _fetch_fmp_news(self, symbol: str, limit: int) -> List[Dict[str, Any]]:
        params = {
            "tickers": symbol,
            "limit": limit,
            "apikey": self.api_key,
        }

        try:
            resp = requests.get(self.endpoint, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            self.logger.warning("NewsClient: Unexpected FMP news payload shape.")
            return []
        except Exception as e:
            self.logger.error(f"NewsClient: FMP news request failed for {symbol}: {e}")
            return []

    # ----------------------------------------------------------------------
    # Normalization
    # ----------------------------------------------------------------------
    def _normalize_fmp_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        try:
            headline = item.get("title")
            if not headline:
                return None

            published = item.get("publishedDate")
            try:
                # FMP uses ISO8601 with timezone
                dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                published_utc = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                published_utc = None

            return {
                "symbol": item.get("symbol"),
                "headline": headline,
                "source": item.get("site") or "FMP",
                "published_utc": published_utc,
                "url": item.get("url"),
                "raw": item,
            }
        except Exception:
            return None