"""
File: nexus_pipeline/catalyst_engine/catalyst_score.py
Version: 1.1.0
Author: Clay & Copilot

Title:
    Catalyst Engine — Catalyst Scoring

Purpose:
    - Convert catalyst classification + metadata into a numerical score.
    - Weight catalyst strength, recency, and sentiment.
    - Provide a deterministic scoring function for Stage 3.

Notes:
    - v1.1.0 is the first real implementation of scoring logic.
    - Future versions may add:
        • sentiment analysis
        • multi-headline aggregation
        • provider-specific weighting
"""

from typing import Dict, Any
from datetime import datetime, timezone


class CatalystScorer:
    def __init__(self, logger):
        self.logger = logger

        # Base scores for catalyst types (KK-aligned)
        self.base_scores = {
            "fda": 10.0,
            "contract": 8.0,
            "earnings": 6.0,
            "guidance": 6.0,
            "upgrade_downgrade": 4.0,
            "mna": 8.0,
            "share_actions": 3.0,
            "offering": -5.0,  # offerings are bearish
            "sec_or_legal": -8.0,
            "other_positive": 3.0,
            "other_negative": -3.0,
            None: 0.0,
        }

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------
    def score(self, catalyst_data: Dict[str, Any]) -> float:
        """
        Compute a catalyst score using:
            - catalyst type
            - classifier confidence
            - recency weighting

        Returns a float score.
        """
        if not catalyst_data:
            return 0.0

        ctype = catalyst_data.get("catalyst_type")
        confidence = catalyst_data.get("confidence", 0.0)
        published = catalyst_data.get("published_utc")

        # Base score from catalyst type
        base = self.base_scores.get(ctype, 0.0)

        # Confidence multiplier (0.0–1.0)
        conf_mult = 0.5 + (confidence * 0.5)  # ranges 0.5–1.0

        # Recency multiplier
        recency_mult = self._recency_multiplier(published)

        score = base * conf_mult * recency_mult
        return round(score, 2)

    # ----------------------------------------------------------------------
    # Recency Weighting
    # ----------------------------------------------------------------------
    def _recency_multiplier(self, published_utc: str) -> float:
        """
        Weight catalyst strength by recency:
            < 6 hours: 1.0
            < 24 hours: 0.8
            < 72 hours: 0.5
            older: 0.3
        """
        if not published_utc:
            return 0.3

        try:
            dt = datetime.fromisoformat(published_utc.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours = (now - dt).total_seconds() / 3600.0

            if hours < 6:
                return 1.0
            if hours < 24:
                return 0.8
            if hours < 72:
                return 0.5
            return 0.3

        except Exception:
            return 0.3