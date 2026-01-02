"""
File: nexus_pipeline/stage2/adapters/adapter_daily_trend.py
Version: 2.0.0
Date: 2025-12-18
Author: Copilot & Clay

Changelog:
- v2.0.0: Updated adapter to use the new class-based DailyTrendScanner
          from core/scan_trend_daily.py. Removed procedural calls,
          monkey-patching, and chart suppression.
- v1.0.0: Initial adapter wrapping analyze_stock() procedural function.
"""

from typing import Dict, Any
from core.scan_trend_daily import DailyTrendScanner as CoreDailyTrendScanner
from core.scan_trend_daily import get_benchmark


class DailyTrendAdapter:
    """
    Stage 2 Adapter: Daily Trend

    Stage 2 expects:
        get_daily_trend(symbol: str) -> Dict[str, Any]

    This adapter wraps the new class-based DailyTrendScanner and
    normalizes its output into the Stage‑2 enrichment schema.
    """

    def __init__(self):
        # Preload SPY benchmark once for RS calculations
        self.spy_data = get_benchmark()
        self.engine = CoreDailyTrendScanner(spy_data=self.spy_data)

    def get_daily_trend(self, symbol: str) -> Dict[str, Any]:
        """
        Return daily trend metadata in Stage‑2 format:

            {
                "daily_trend": str | None,
                "daily_trend_score": float | None,
                "daily_trend_raw": dict | None
            }
        """

        try:
            result = self.engine.get_daily_trend(symbol)

            # DEBUG PRINT
            print("EP RAW:", result)

            return {
                "daily_trend": result.get("daily_trend"),
                "daily_trend_score": result.get("daily_trend_score"),
                "daily_trend_raw": result.get("daily_trend_raw"),
            }

        except Exception:
            return {
                "daily_trend": None,
                "daily_trend_score": None,
                "daily_trend_raw": None,
            }