"""
Catalyst Classifier

Classify news headlines into catalyst categories using regex patterns.
Ported from legacy: nexus_pipeline/catalyst_engine/catalyst_classifier.py
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Dict
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

logger = logging.getLogger(__name__)


def _get_catalyst_audit_logger() -> logging.Logger:
    """Get or create the dedicated catalyst audit file logger."""
    audit_logger = logging.getLogger("catalyst_audit")
    
    if not audit_logger.handlers:
        # Create data directory if needed
        log_dir = Path("data")
        log_dir.mkdir(exist_ok=True)
        
        # Rotating file handler: 1MB max, keep 7 files
        handler = RotatingFileHandler(
            log_dir / "catalyst_audit.log",
            maxBytes=1_000_000,
            backupCount=7,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        audit_logger.addHandler(handler)
        audit_logger.setLevel(logging.INFO)
        # Don't propagate to root logger (avoid duplication in console)
        audit_logger.propagate = False
    
    return audit_logger


catalyst_audit_logger = _get_catalyst_audit_logger()


@dataclass
class CatalystMatch:
    """Result of headline classification."""
    headline: str
    catalyst_type: Optional[str]
    confidence: float
    is_positive: bool  # For KK, we want positive catalysts only


class CatalystClassifier:
    """
    Classify headlines into catalyst categories using regex.
    
    KK-style positive catalysts:
    - earnings (beat/raise)
    - fda (approval, positive trial)
    - contract (major deal/partnership)
    
    Negative catalysts (avoid):
    - offering (dilution)
    - sec/legal
    - misses/disappoints
    """
    
    def __init__(self):
        # Positive catalyst patterns (KK-aligned)
        self.positive_patterns = {
            "earnings": re.compile(
                r"\b(earnings|q[1-4]\s+results|eps|revenue|beats?\s+estimates?|raises?\s+guidance|strong\s+quarter|preliminary\s+(fourth|first|second|third)\s+quarter|full[- ]year\s+results?)\b",
                re.IGNORECASE,
            ),
            "fda": re.compile(
                r"\b(fda\s+approv\w*|fda\s+clear\w*|fda\s+(lifts?|removes?|clears?)\s+(clinical\s+)?hold|clinical\s+hold\s+(lifted|removed|resolved|cleared)|phase\s+[1-3]\s+(success|positive|met)|clinical\s+(trial\s+)?(success|positive|results?|data)|breakthrough\s+designation|drug\s+approv\w*|complete\s+resol\w*|complete\s+response|interim\s+safety|promising\s+(early\s+)?clinical|grants?\s+(accelerated\s+)?approval)\b",
                re.IGNORECASE,
            ),
            "contract": re.compile(
                r"\b(contract|awarded?|major\s+order|partnership|collaboration|strategic\s+(alliance|investment|partnership)|multi-year\s+deal|purchase\s+orders?|receives?\s+\$?\d+\s*(m|million|b|billion)|supplies?\s+\w+\s+(to|for)|government\s+(order|contract)|announces?\s+agreement|signs?\s+agreement|agreement\s+with\s+\w+|partners?\s+with|integration\s+with|project\s+wins?)\b",
                re.IGNORECASE,
            ),
            "guidance_raise": re.compile(
                r"\b(raises?\s+(outlook|guidance|forecast)|upward\s+revision|increases?\s+guidance)\b",
                re.IGNORECASE,
            ),
            "acquisition": re.compile(
                r"\b(acquires?|acquisition|acquired|merger|takeover|buyout|buys?\s+\d+%|agree\s+to\s+(buy|acquire)|definitive\s+agreement|takes?\s+control|major\s+investor|activist\s+investor|significant\s+stake|controlling\s+(interest|stake)|board\s+seats?|proxy\s+(fight|battle|contest)|new\s+ownership|change\s+of\s+control)\b",
                re.IGNORECASE,
            ),
            "ipo": re.compile(
                r"\b(ipo|initial\s+public\s+offering|newly\s+listed|begins\s+trading|starts\s+trading|debut|goes\s+public)\b",
                re.IGNORECASE,
            ),
            # Analyst valuations & price targets (HIND missed: "Analyst Values...at USD 1 Billion")
            "analyst_valuation": re.compile(
                r"\b(analyst\s+values?|price\s+target|price\s+objectiv|valuati?on\s+(of|at)|valued\s+at|worth\s+(?:\$|USD)?\s*[\d.]+\s*(?:billion|million)|rating\s+upgrade|initiates?\s+(?:buy|outperform)|upgrade[sd]?\s+to\s+(?:buy|strong\s+buy|outperform))\b",
                re.IGNORECASE,
            ),
            # Clinical trial advancement (HIND missed: "Phase 3 Study" advancement)
            "clinical_advance": re.compile(
                r"\b(advance[sd]?\s+(?:into|to)\s+(?:phase|pivotal)|phase\s+(?:3|iii|three)\s+(?:study|trial|program)|pivotal\s+(?:study|trial)|phase\s+[1-3]\s+(?:initiation|enrollment|dosing|completion)|first\s+patient\s+(?:dosed|enrolled)|topline\s+(?:data|results))\b",
                re.IGNORECASE,
            ),
            # Significant monetary valuations (HIND missed: "USD 1 Billion")
            "significant_value": re.compile(
                r"\b(?:\$|USD|EUR|GBP)\s*[\d.]+\s*(?:billion|bn|b)\b|\b[\d.]+\s*(?:billion|bn)\s*(?:dollar|usd|valuation|deal|agreement|contract)\b",
                re.IGNORECASE,
            ),
        }
        
        # Negative catalyst patterns (avoid these)
        self.negative_patterns = {
            "offering": re.compile(
                r"\b(offerings?|public\s+offering|registered\s+direct|at-the-market|atm\s+offering|dilution)\b",
                re.IGNORECASE,
            ),
            "sec_or_legal": re.compile(
                r"\b(sec\s+investigation|subpoena|lawsuit|settlement|class\s+action|investigation)\b",
                re.IGNORECASE,
            ),
            "guidance_cut": re.compile(
                r"\b(lowers?\s+(outlook|guidance)|cuts?\s+guidance|downward\s+revision|warns?)\b",
                re.IGNORECASE,
            ),
            "miss": re.compile(
                r"\b(misses?|disappoints?|falls?\s+short|below\s+estimates?|weak\s+quarter)\b",
                re.IGNORECASE,
            ),
        }
        
        # Sentiment keywords (fallback)
        self.positive_sentiment = re.compile(
            r"\b(soars?|jumps?|surges?|spikes?|gains?|rallies|skyrockets?|explodes?)\b",
            re.IGNORECASE,
        )
        self.negative_sentiment = re.compile(
            r"\b(sinks?|plunges?|drops?|falls?|crashes?|tumbles?|slides?)\b",
            re.IGNORECASE,
        )
    
    def classify(self, headline: str) -> CatalystMatch:
        """
        Classify a single headline.
        
        Returns:
            CatalystMatch with type, confidence, and polarity
        """
        if not headline or not headline.strip():
            return CatalystMatch(
                headline=headline,
                catalyst_type=None,
                confidence=0.0,
                is_positive=False,
            )
        
        h = headline.strip()
        
        # Check negative patterns first (to avoid bad trades)
        for ctype, pattern in self.negative_patterns.items():
            if pattern.search(h):
                return CatalystMatch(
                    headline=h,
                    catalyst_type=ctype,
                    confidence=0.9,
                    is_positive=False,
                )
        
        # Check positive patterns
        for ctype, pattern in self.positive_patterns.items():
            if pattern.search(h):
                return CatalystMatch(
                    headline=h,
                    catalyst_type=ctype,
                    confidence=0.9,
                    is_positive=True,
                )
        
        # Fallback: sentiment-based (0.5 confidence = below threshold, not a real catalyst)
        if self.positive_sentiment.search(h):
            return CatalystMatch(
                headline=h,
                catalyst_type="positive_sentiment",
                confidence=0.5,  # Below 0.6 threshold - sentiment alone is not enough
                is_positive=True,
            )
        
        if self.negative_sentiment.search(h):
            return CatalystMatch(
                headline=h,
                catalyst_type="negative_sentiment",
                confidence=0.6,
                is_positive=False,
            )
        
        # No match
        return CatalystMatch(
            headline=h,
            catalyst_type=None,
            confidence=0.0,
            is_positive=False,
        )
    
    def classify_headlines(self, headlines: List[str]) -> List[CatalystMatch]:
        """Classify multiple headlines."""
        return [self.classify(h) for h in headlines]
    
    def has_positive_catalyst(self, headlines: List[str]) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Check if any headline indicates a positive KK-style catalyst.
        
        Returns:
            (has_catalyst, catalyst_type, best_headline)
        """
        best_match = None
        best_confidence = 0.0
        
        for h in headlines:
            match = self.classify(h)
            if match.is_positive and match.confidence > best_confidence:
                best_match = match
                best_confidence = match.confidence
        
        if best_match and best_match.catalyst_type:
            return True, best_match.catalyst_type, best_match.headline
        
        return False, None, None
    
    def has_negative_catalyst(self, headlines: List[str]) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Check if any headline indicates a negative catalyst (avoid).
        
        Returns:
            (has_negative, catalyst_type, worst_headline)
        """
        for h in headlines:
            match = self.classify(h)
            if not match.is_positive and match.catalyst_type and match.confidence >= 0.9:
                return True, match.catalyst_type, match.headline
        
        return False, None, None


# Singleton instance
_classifier = None

def get_classifier() -> CatalystClassifier:
    """Get or create singleton classifier."""
    global _classifier
    if _classifier is None:
        _classifier = CatalystClassifier()
    return _classifier


def log_headline_evaluation(symbol: str, headlines: List[str], final_result: str, final_type: Optional[str] = None):
    """
    Log all headline evaluations for a symbol to the catalyst audit log.
    
    Args:
        symbol: Stock symbol
        headlines: List of headlines that were evaluated
        final_result: "PASS" or "FAIL"
        final_type: The catalyst type that matched, or None if no match
    """
    classifier = get_classifier()
    
    catalyst_audit_logger.info(f"=== {symbol} | Result: {final_result} | Type: {final_type or 'none'} ===")
    
    for i, headline in enumerate(headlines[:5], 1):  # Log top 5 headlines
        match = classifier.classify(headline)
        status = "✓" if match.is_positive and match.confidence >= 0.6 else "✗"
        type_str = match.catalyst_type or "no_match"
        catalyst_audit_logger.info(
            f"  [{i}] {status} {type_str} (conf={match.confidence:.2f}): {headline[:100]}"
        )
