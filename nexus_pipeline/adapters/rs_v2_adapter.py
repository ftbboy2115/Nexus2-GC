"""
File: nexus_pipeline/stage2/adapters/adapter_rs_v2.py
Version: 2.0.0
Date: 2025-12-18
Author: Copilot & Clay

Changelog:
- v2.0.0: Updated adapter to use the new class-based RSEngineV2 from
          core/rs_v2.py. Removed CSV lookup logic and normalized return
          schema to Stage‑2 standards.
- v1.0.0: Initial adapter using rs_v2.csv batch output.
"""

from typing import Dict, Any
from core.rs_v2_engine import RSEngineV2 as CoreRSEngineV2


class RSv2Adapter:
    """
    Stage 2 Adapter: Relative Strength v2

    Stage 2 expects:
        get_rs(symbol: str) -> Dict[str, Any]

    This adapter wraps the new class-based RSEngineV2 and normalizes its
    output into the Stage‑2 enrichment schema.
    """

    def __init__(self, strategy_log_path: str | None = None):
        # RSEngineV2 loads and parses strategy_log.jsonl internally
        self.engine = CoreRSEngineV2(strategy_log_path=strategy_log_path)

    def get_rs(self, symbol: str) -> Dict[str, Any]:
        """
        Return RS v2 metrics in Stage‑2 format:

            {
                "rs_value": float | None,
                "rs_rank": float | None,
                "rs_source": "v2",
                "rs_raw": dict | None
            }
        """

        try:
            result = self.engine.get_rs(symbol)

            return {
                "rs_value": result.get("rs_value"),
                "rs_rank": result.get("rs_rank"),
                "rs_source": "v2",
                "rs_raw": result,
            }

        except Exception:
            return {
                "rs_value": None,
                "rs_rank": None,
                "rs_source": "v2",
                "rs_raw": None,
            }