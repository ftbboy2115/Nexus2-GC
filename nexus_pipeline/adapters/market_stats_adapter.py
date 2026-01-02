"""
File: nexus_pipeline/stage2/adapters/adapter_market_stats.py
Version: 2.0.0
Date: 2025-12-18
Author: Copilot & Clay

Changelog:
- v2.0.0: Modernized header, normalized return schema, aligned naming
          with Stage‑2 adapter architecture.
- v1.0.0: Initial adapter wrapping get_sector_performance().
"""

from typing import Dict, Any
from core import market_stats


class MarketStatsAdapter:
    """
    Stage 2 Adapter: Market Rotation / Sector Performance

    Stage 2 expects:
        get_stats(symbol: str) -> Dict[str, Any]

    Market stats are global, not symbol-specific, so the adapter loads
    sector performance once and returns the same data for any symbol.
    """

    def __init__(self):
        try:
            df = market_stats.get_sector_performance()
            self.df = df if df is not None else None
        except Exception:
            self.df = None

    def get_stats(self, symbol: str) -> Dict[str, Any]:
        """
        Return market rotation metadata in Stage‑2 format:

            {
                "market_rotation": str | None,
                "market_rotation_strength": float | None,
                "market_stats_raw": list[dict] | None
            }
        """

        if self.df is None or self.df.empty:
            return {
                "market_rotation": None,
                "market_rotation_strength": None,
                "market_stats_raw": None,
            }

        try:
            top_row = self.df.iloc[0]
            rotation = top_row["Sector"]
            strength = top_row["Change (%)"]

            return {
                "market_rotation": rotation,
                "market_rotation_strength": strength,
                "market_stats_raw": self.df.to_dict(orient="records"),
            }

        except Exception:
            return {
                "market_rotation": None,
                "market_rotation_strength": None,
                "market_stats_raw": None,
            }