"""
File: nexus_pipeline/stage2/adapters/adapter_htf.py
Version: 2.0.0
Date: 2025-12-18
Author: Copilot & Clay

Changelog:
- v2.0.0: Updated adapter to use the new class-based HTFScanner from
          core/scan_htf.py. Removed procedural analyze_htf() calls and
          chart suppression logic.
- v1.0.0: Initial adapter wrapping analyze_htf() procedural function.
"""

from typing import Dict, Any
from core.scan_htf import HTFScanner as CoreHTFScanner


class HTFAdapter:
    """
    Stage 2 Adapter: High Tight Flag (HTF)

    Stage 2 expects:
        get_htf_trend(symbol: str) -> Dict[str, Any]

    This adapter wraps the new class-based HTFScanner and normalizes its
    output into the Stage‑2 enrichment schema.
    """

    def __init__(self):
        self.engine = CoreHTFScanner()

    def get_htf_trend(self, symbol: str) -> Dict[str, Any]:
        """
        Return HTF metadata in Stage‑2 format:

            {
                "htf_trend": str | None,
                "htf_trend_score": float | None,
                "htf_raw": dict | None
            }
        """

        try:
            result = self.engine.get_htf_trend(symbol)

            # DEBUG PRINT
            print("EP RAW:", result)

            return {
                "htf_trend": result.get("htf_trend"),
                "htf_trend_score": result.get("htf_trend_score"),
                "htf_raw": result.get("htf_raw"),
            }

        except Exception:
            return {
                "htf_trend": None,
                "htf_trend_score": None,
                "htf_raw": None,
            }