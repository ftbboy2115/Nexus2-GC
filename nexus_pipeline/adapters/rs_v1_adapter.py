"""
File: nexus_pipeline/stage2/adapters/adapter_rs_v1.py
Version: 2.0.0
Date: 2025-12-18
Author: Copilot & Clay

Changelog:
- v2.0.0: Updated adapter to use the new class-based RSEngineV1 from
          core/rs_v1.py. Removed procedural get_rs_metrics() calls and
          normalized return schema.
- v1.0.0: Initial adapter wrapping procedural rs_engine.get_rs_metrics().
"""

from typing import Dict, Any
from core.rs_engine import RSEngine


class RSv1Adapter:
    """
    Stage 2 Adapter: Relative Strength v1

    Stage 2 expects:
        get_rs(symbol: str) -> Dict[str, Any]

    This adapter wraps the new class-based RSEngineV1 and normalizes its
    output into the Stage‑2 enrichment schema.
    """

    def __init__(self):
        self.engine = RSEngine()

    def get_rs(self, symbol: str) -> Dict[str, Any]:
        """
        Return RS v1 metrics in Stage‑2 format:

            {
                "rs_value": float | None,
                "rs_rank": None,          # v1 has no percentile rank
                "rs_source": "v1",
                "rs_raw": dict | None
            }
        """

        try:
            result = self.engine.get_rs(symbol)

            return {
                "rs_value": result.get("rs_value"),
                "rs_rank": None,                 # RS v1 has no ranking
                "rs_source": "v1",
                "rs_raw": result,
            }

        except Exception:
            return {
                "rs_value": None,
                "rs_rank": None,
                "rs_source": "v1",
                "rs_raw": None,
            }