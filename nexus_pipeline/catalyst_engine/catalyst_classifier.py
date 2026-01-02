"""
File: nexus_pipeline/catalyst_engine/catalyst_classifier.py
Version: 1.2.0
Author: Clay & Copilot

Title:
    Catalyst Engine — Catalyst Classifier

Purpose:
    - Classify headlines into catalyst categories.
    - Provide deterministic, rule-based classification aligned with KK-style filters.
    - Return a primary catalyst_type and a confidence score.

Notes:
    - v1.2.0 implements a keyword/regex-based classifier.
    - Future versions may add:
        • multi-label classification
        • NLP-based sentiment analysis
        • provider-specific tuning
"""

import re
from typing import Dict, Any, Optional


class CatalystClassifier:
    def __init__(self, logger):
        self.logger = logger

        # Precompile regex patterns for performance and consistency
        self.patterns = {
            "earnings": re.compile(
                r"\b(earnings|q[1-4]\s+results|results for the quarter|eps|revenue|guidance)\b",
                re.IGNORECASE,
            ),
            "guidance": re.compile(
                r"\b(guidance|updates? (its )?outlook|raises? outlook|lowers? outlook)\b",
                re.IGNORECASE,
            ),
            "fda": re.compile(
                r"\b(fda|phase\s+[1-3]|clinical trial|pivotal trial|endpoint|investigational new drug)\b",
                re.IGNORECASE,
            ),
            "contract": re.compile(
                r"\b(contract|award|orders?|purchase order|supply agreement|partnership|collaboration|strategic alliance)\b",
                re.IGNORECASE,
            ),
            "upgrade_downgrade": re.compile(
                r"\b(upgrades?|downgrades?|initiates? coverage|price target|pt to|rating (to|from))\b",
                re.IGNORECASE,
            ),
            "mna": re.compile(
                r"\b(acquires?|acquisition|merger|merging with|to be acquired|buyout|takeover)\b",
                re.IGNORECASE,
            ),
            "offering": re.compile(
                r"\b(offerings?|public offering|registered direct|at-the-market|atm offering)\b",
                re.IGNORECASE,
            ),
            "share_actions": re.compile(
                r"\b(reverse split|stock split|share repurchase|buyback|dividend)\b",
                re.IGNORECASE,
            ),
            "sec_or_legal": re.compile(
                r"\b(sec|subpoena|lawsuit|settlement|class action|investigation)\b",
                re.IGNORECASE,
            ),
        }

    def classify(self, headline: str) -> Dict[str, Any]:
        """
        Classify a headline into a primary catalyst_type with a confidence score.

        Returns:
            {
                "catalyst_type": Optional[str],
                "confidence": float,
            }

        catalyst_type is one of:
            - "earnings"
            - "guidance"
            - "fda"
            - "contract"
            - "upgrade_downgrade"
            - "mna"
            - "offering"
            - "share_actions"
            - "sec_or_legal"
            - "other_positive"
            - "other_negative"
            - None
        """
        if not headline:
            return {
                "catalyst_type": None,
                "confidence": 0.0,
            }

        h = headline.strip()
        if not h:
            return {
                "catalyst_type": None,
                "confidence": 0.0,
            }

        try:
            # Primary deterministic categories
            for ctype, pattern in self.patterns.items():
                if pattern.search(h):
                    return {
                        "catalyst_type": ctype,
                        "confidence": 0.9,
                    }

            # Fallback: broad positive/negative buckets
            positive_pattern = re.compile(
                r"\b(soars?|jumps?|surges?|spikes?|gains?|rallies|beats?|tops?)\b",
                re.IGNORECASE,
            )
            negative_pattern = re.compile(
                r"\b(sinks?|plunges?|drops?|falls?|misses?|disappoints?)\b",
                re.IGNORECASE,
            )

            if positive_pattern.search(h):
                return {
                    "catalyst_type": "other_positive",
                    "confidence": 0.6,
                }

            if negative_pattern.search(h):
                return {
                    "catalyst_type": "other_negative",
                    "confidence": 0.6,
                }

            # No recognizable catalyst keywords
            return {
                "catalyst_type": None,
                "confidence": 0.0,
            }

        except Exception as e:
            # Defensive: never let classification break the pipeline
            self.logger.error(f"CatalystClassifier: failed to classify headline: {e}")
            return {
                "catalyst_type": None,
                "confidence": 0.0,
            }