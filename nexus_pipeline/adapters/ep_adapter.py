"""
File: nexus_pipeline/stage2/adapters/adapter_ep.py
Version: 2.0.0
Date: 2025-12-18
Author: Copilot & Clay

Changelog:
- v2.0.0: Updated adapter to use the new class-based EPScanner from
          core/scan_ep.py. Removed procedural process_stock() calls and
          chart suppression logic.
- v1.0.0: Initial adapter wrapping process_stock() procedural function.
"""

from typing import Dict, Any
from unittest import result

from core.scan_ep import EPScanner as CoreEPScanner


class EPAdapter:
    """
    Stage 2 Adapter: Episodic Pivot (EP)

    Stage 2 expects:
        get_episodic_pivot(symbol: str) -> Dict[str, Any]

    This adapter wraps the new class-based EPScanner and normalizes its
    output into the Stage‑2 enrichment schema.
    """

    def __init__(self):
        self.engine = CoreEPScanner()

    def get_episodic_pivot(self, symbol: str) -> Dict[str, Any]:
        """
        Return EP metadata in Stage‑2 format:

            {
                "ep_pivot_score": float | None,
                "ep_pivot_label": str | None,
                "ep_pivot_trigger": str | None,
                "ep_pivot_raw": dict | None
            }
        """

        try:
            result = self.engine.get_episodic_pivot(symbol)

            # DEBUG PRINT
            print("EP RAW:", result)

            return {
                "ep_pivot_score": result.get("ep_pivot_score"),
                "ep_pivot_label": result.get("ep_pivot_label"),
                "ep_pivot_trigger": result.get("ep_pivot_trigger"),
                "ep_pivot_raw": result.get("ep_pivot_raw"),
            }

        except Exception:
            return {
                "ep_pivot_score": None,
                "ep_pivot_label": None,
                "ep_pivot_trigger": None,
                "ep_pivot_raw": None,
            }
