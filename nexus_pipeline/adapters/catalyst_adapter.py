"""
File: nexus_pipeline/stage2/adapters/adapter_catalyst.py
Version: 2.0.0
Date: 2025-12-18
Author: Copilot & Clay

Changelog:
- v2.0.0: Modernized header, aligned with Stage‑2 adapter architecture.
- v1.0.0: Initial implementation wrapping CatalystEngine.score().
"""

from typing import Dict, Any
from core.catalyst_engine import CatalystEngine, CatalystContext


class CatalystAdapter:
    """
    Stage 2 Adapter: Catalyst Engine

    Stage 2 expects:
        get_catalyst(symbol: str, **kwargs) -> Dict[str, Any]

    This adapter wraps CatalystEngine.score() and normalizes the output
    into the Stage‑2 enrichment schema.
    """

    def __init__(self):
        self.engine = CatalystEngine()

    def get_catalyst(
        self,
        symbol: str,
        gap_pct: float | None = None,
        rvol: float | None = None,
        rs_rank: float | None = None,
        sector: str | None = None,
        has_recent_earnings: bool | None = None,
        has_earnings_beat: bool | None = None,
        has_guidance_raise: bool | None = None,
        has_major_news: bool | None = None,
        has_fda: bool | None = None,
        has_mna: bool | None = None,
        analyst_upgrade: bool | None = None,
        sector_hot: bool | None = None,
        recency_hours: float | None = None,
    ) -> Dict[str, Any]:
        """
        Return catalyst metadata in Stage‑2 format:

            {
                "catalyst_score": int | None,
                "catalyst_strength": str | None,
                "catalyst_tags": list[str] | None,
                "catalyst_raw": dict | None
            }
        """

        try:
            ctx = CatalystContext(
                symbol=symbol,
                gap_pct=gap_pct,
                rvol=rvol,
                rs_rank=rs_rank,
                sector=sector,
                has_recent_earnings=has_recent_earnings,
                has_earnings_beat=has_earnings_beat,
                has_guidance_raise=has_guidance_raise,
                has_major_news=has_major_news,
                has_fda=has_fda,
                has_mna=has_mna,
                analyst_upgrade=analyst_upgrade,
                sector_hot=sector_hot,
                recency_hours=recency_hours,
            )

            result = self.engine.score(ctx)

            return {
                "catalyst_score": result.score,
                "catalyst_strength": result.strength,
                "catalyst_tags": result.tags,
                "catalyst_raw": result.to_dict(),
            }

        except Exception:
            return {
                "catalyst_score": None,
                "catalyst_strength": None,
                "catalyst_tags": None,
                "catalyst_raw": None,
            }