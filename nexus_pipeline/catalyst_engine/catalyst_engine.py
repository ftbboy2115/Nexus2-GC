"""
File: nexus_pipeline/catalyst_engine/catalyst_engine.py
Version: 1.1.0
Author: Clay & Copilot

Title:
    Catalyst Engine — Orchestrator

Purpose:
    - Coordinate catalyst detection, classification, and scoring.
    - Provide a unified interface for Stage 2 (build_contexts.py).
    - Return structured catalyst metadata for each symbol.

Pipeline Role:
    Stage 2 calls CatalystEngine.get_catalyst(symbol)
    and receives:
        {
            "has_catalyst": bool,
            "catalyst_type": str,
            "catalyst_score": float,
            "headline": str,
            "timestamp": str
        }

Notes:
    - v1.1.0 is the first real implementation of the orchestrator.
    - Logic:
        • fetch news
        • classify top headline
        • score catalyst
        • return structured metadata
"""

from typing import Dict, Any

from .news_client import NewsClient
from .catalyst_classifier import CatalystClassifier
from .catalyst_score import CatalystScorer


class CatalystEngine:
    def __init__(self, api_key: str, logger):
        self.logger = logger
        self.news_client = NewsClient(api_key, logger)
        self.classifier = CatalystClassifier(logger)
        self.scorer = CatalystScorer(logger)

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------
    def get_catalyst(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch news → classify → score → return catalyst metadata.

        Returns:
            {
                "has_catalyst": bool,
                "catalyst_type": Optional[str],
                "catalyst_score": float,
                "headline": Optional[str],
                "timestamp": Optional[str]
            }
        """
        try:
            news_items = self.news_client.fetch_news(symbol)

            if not news_items:
                return self._empty()

            top = news_items[0]
            headline = top.get("headline")
            timestamp = top.get("published_utc")

            classification = self.classifier.classify(headline)
            ctype = classification.get("catalyst_type")
            confidence = classification.get("confidence", 0.0)

            catalyst_data = {
                "catalyst_type": ctype,
                "confidence": confidence,
                "published_utc": timestamp,
            }
            score = self.scorer.score(catalyst_data)

            return {
                "has_catalyst": ctype is not None and score > 0,
                "catalyst_type": ctype,
                "catalyst_score": score,
                "headline": headline,
                "timestamp": timestamp,
            }

        except Exception as e:
            self.logger.error(f"CatalystEngine: failed for {symbol}: {e}")
            return self._empty()

    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------
    def _empty(self) -> Dict[str, Any]:
        return {
            "has_catalyst": False,
            "catalyst_type": None,
            "catalyst_score": 0.0,
            "headline": None,
            "timestamp": None,
        }