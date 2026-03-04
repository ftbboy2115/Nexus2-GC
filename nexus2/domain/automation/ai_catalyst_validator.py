"""
AI Catalyst Validator & Multi-Model Comparison System

CATALYST VALIDATION PIPELINE:
==============================
This module implements a parallel assessment system for catalyst validation,
designed to improve accuracy while generating training data for regex pattern
refinement.

FLOW:
           Headline detected
                  │
                  ▼
    ┌─────────────────────────────┐
    │   PARALLEL ASSESSMENT       │
    │  ┌─────────┐  ┌──────────┐  │
    │  │  Regex  │  │Flash-Lite│  │
    │  │Classify │  │   AI     │  │
    │  └────┬────┘  └────┬─────┘  │
    └───────┼────────────┼────────┘
            │            │
            ▼            ▼
         ┌──────────────────┐
         │   Agreement?     │
         └────────┬─────────┘
           ┌──────┴──────┐
           │             │
         YES            NO
           │             │
           ▼             ▼
    ┌────────────┐  ┌────────────┐
    │ Consensus  │  │Pro Model   │
    │ Result     │  │Tiebreaker  │
    └─────┬──────┘  └─────┬──────┘
          │               │
          └───────┬───────┘
                  ▼
    ┌─────────────────────────────┐
    │  Cache in HeadlineCache     │
    │  - regex_passed: bool       │
    │  - flash_passed: bool       │
    │  - method: consensus |      │
    │           tiebreaker |      │
    │           regex_only        │
    └──────────────┬──────────────┘
                   ▼
    Log to data/catalyst_comparison.jsonl

TRAINING FEEDBACK LOOP:
  - API: GET /data/ai-comparisons - Review Regex vs Flash vs Pro results
  - API: GET /warrior/scanner/catalyst-audit - Review headline evaluations
  - Purpose: Identify false negatives where regex is missing patterns,
    then add new patterns to catalyst_classifier.py

COMPONENTS:
  - CatalystCache: Short-term (5-min TTL) cross-strategy validation cache
  - HeadlineCache: Persistent (14-day TTL) disk-backed headline storage
  - AICatalystValidator: Single-model Gemini validator (legacy)
  - MultiModelValidator: Parallel assessment with tiebreaker system

USAGE:
  # In warrior_scanner_service.py:
  multi_validator = get_multi_validator()
  final_valid, final_type, regex_passed, flash_passed, method = \\
      multi_validator.validate_sync(headline, symbol, regex_passed, regex_type)
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass
from nexus2.utils.time_utils import now_et, now_utc
from nexus2.db.telemetry_db import get_telemetry_session, AIComparison as AIComparisonDB, CatalystAudit

logger = logging.getLogger(__name__)


# =============================================================================
# SHARED CATALYST CACHE (Cross-Strategy)
# =============================================================================

@dataclass
class CachedCatalyst:
    """Cached catalyst validation result."""
    is_valid: bool
    catalyst_type: Optional[str]
    description: str
    cached_at: datetime


class CatalystCache:
    """
    Shared cache for catalyst validation results.
    
    Both Warrior and NAC strategies can reuse AI validation results
    to reduce API calls and avoid rate limiting.
    """
    
    def __init__(self, ttl_minutes: int = 5):
        self._cache: Dict[str, CachedCatalyst] = {}
        self._ttl = timedelta(minutes=ttl_minutes)
    
    def get(self, symbol: str) -> Optional[CachedCatalyst]:
        """Get cached catalyst if fresh, else None."""
        if symbol not in self._cache:
            return None
        
        cached = self._cache[symbol]
        if now_et() - cached.cached_at > self._ttl:
            # Expired
            del self._cache[symbol]
            return None
        
        return cached
    
    def set(self, symbol: str, is_valid: bool, catalyst_type: Optional[str], description: str):
        """Cache a catalyst validation result."""
        self._cache[symbol] = CachedCatalyst(
            is_valid=is_valid,
            catalyst_type=catalyst_type,
            description=description,
            cached_at=now_et(),
        )
    
    def clear(self):
        """Clear all cached results."""
        self._cache.clear()
    
    def stats(self) -> dict:
        """Return cache statistics."""
        return {
            "size": len(self._cache),
            "valid_count": sum(1 for c in self._cache.values() if c.is_valid),
            "invalid_count": sum(1 for c in self._cache.values() if not c.is_valid),
        }


# Singleton cache instance
_catalyst_cache: Optional[CatalystCache] = None


def get_catalyst_cache() -> CatalystCache:
    """Get shared catalyst cache singleton."""
    global _catalyst_cache
    if _catalyst_cache is None:
        _catalyst_cache = CatalystCache(ttl_minutes=5)
    return _catalyst_cache


# =============================================================================
# PERSISTENT HEADLINE CACHE (14-day TTL, disk-backed)
# =============================================================================

import json
import hashlib


@dataclass
class CachedHeadline:
    """A cached headline with its validation result."""
    text_hash: str
    text: str
    fetched_at: str  # ISO format
    is_valid: bool
    catalyst_type: Optional[str]
    regex_passed: bool
    flash_passed: Optional[bool]
    method: str  # "regex_only", "consensus", "tiebreaker"


class HeadlineCache:
    """
    Persistent cache for headlines and their validation results.
    
    Headlines are stored by symbol with text hash for deduplication.
    Cache persists to JSON file for survival across restarts.
    TTL is 7 days - old headlines are pruned on load.
    """
    
    def __init__(self, cache_path: Optional[Path] = None, ttl_days: int = 7):
        self._cache_path = cache_path or Path(__file__).parent.parent.parent.parent / "data" / "headline_cache.json"
        self._ttl = timedelta(days=ttl_days)
        self._data: Dict[str, List[dict]] = {}
        self._load()
    
    def _hash(self, text: str) -> str:
        """Create short hash of headline text."""
        return hashlib.md5(text.encode()).hexdigest()[:12]
    
    def _load(self):
        """Load cache from disk, prune expired entries."""
        if self._cache_path.exists():
            try:
                with open(self._cache_path, 'r') as f:
                    self._data = json.load(f)
                self._prune()
                logger.info(f"[HeadlineCache] Loaded {sum(len(v) for v in self._data.values())} headlines")
            except Exception as e:
                logger.warning(f"[HeadlineCache] Load error: {e}")
                self._data = {}
        else:
            self._data = {}
    
    def _save(self):
        """Save cache to disk."""
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_path, 'w') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.warning(f"[HeadlineCache] Save error: {e}")
    
    def _prune(self):
        """Remove headlines older than TTL."""
        now = now_et()
        for symbol in list(self._data.keys()):
            self._data[symbol] = [
                h for h in self._data[symbol]
                if now - datetime.fromisoformat(h["fetched_at"]) < self._ttl
            ]
            if not self._data[symbol]:
                del self._data[symbol]
    
    def get_cached_headlines(self, symbol: str) -> List[CachedHeadline]:
        """Get all cached headlines for a symbol."""
        if symbol not in self._data:
            return []
        return [
            CachedHeadline(
                text_hash=h["text_hash"],
                text=h["text"],
                fetched_at=h["fetched_at"],
                is_valid=h["is_valid"],
                catalyst_type=h.get("catalyst_type"),
                regex_passed=h.get("regex_passed", False),
                flash_passed=h.get("flash_passed"),
                method=h.get("method", "unknown"),
            )
            for h in self._data[symbol]
        ]
    
    def get_new_headlines(self, symbol: str, fetched_headlines: List[str]) -> List[str]:
        """Filter to only headlines not already in cache."""
        cached_hashes = set(h["text_hash"] for h in self._data.get(symbol, []))
        return [h for h in fetched_headlines if self._hash(h) not in cached_hashes]
    
    def has_valid_catalyst(self, symbol: str) -> Tuple[bool, Optional[str]]:
        """Check if any cached headline is a valid catalyst."""
        for h in self._data.get(symbol, []):
            if h.get("is_valid"):
                return True, h.get("catalyst_type")
        return False, None
    
    def add(
        self,
        symbol: str,
        headline: str,
        is_valid: bool,
        catalyst_type: Optional[str],
        regex_passed: bool,
        flash_passed: Optional[bool] = None,
        method: str = "unknown",
    ):
        """Add a headline with its validation result."""
        if symbol not in self._data:
            self._data[symbol] = []
        
        text_hash = self._hash(headline)
        
        # Don't duplicate
        if any(h["text_hash"] == text_hash for h in self._data[symbol]):
            return
        
        self._data[symbol].append({
            "text_hash": text_hash,
            "text": headline[:200],  # Truncate for storage
            "fetched_at": now_et().isoformat(),
            "is_valid": is_valid,
            "catalyst_type": catalyst_type,
            "regex_passed": regex_passed,
            "flash_passed": flash_passed,
            "method": method,
        })
        self._save()
    
    def stats(self) -> dict:
        """Return cache statistics."""
        total = sum(len(v) for v in self._data.values())
        valid = sum(1 for v in self._data.values() for h in v if h.get("is_valid"))
        return {"symbols": len(self._data), "headlines": total, "valid": valid}


# Singleton instance
_headline_cache: Optional[HeadlineCache] = None


def get_headline_cache() -> HeadlineCache:
    """Get shared headline cache singleton."""
    global _headline_cache
    if _headline_cache is None:
        _headline_cache = HeadlineCache()
    return _headline_cache


@dataclass
class AIValidationResult:
    """Result from AI catalyst validation."""
    is_valid: bool
    catalyst_type: Optional[str]
    reason: str
    raw_response: str


# =============================================================================
# STRATEGY-SPECIFIC SYSTEM PROMPTS
# =============================================================================

# Ross Cameron (Warrior) — broad momentum catalyst definition
WARRIOR_SYSTEM_PROMPT = """You are a trading catalyst validator for Ross Cameron-style momentum day trading.

Your job: Determine if a news headline is a VALID CATALYST for a momentum day trade.
A catalyst is any confirmed news event that could cause a significant price gap or move.

VALID MOMENTUM CATALYSTS (approve these):
- ALL earnings results — beat, miss, or neutral. The gap itself is the catalyst.
  Examples of valid earnings headlines:
    "[Company] Q4 2025 Earnings Call Transcript" → VALID: earnings
    "[Company]: Q4 Earnings Snapshot" → VALID: earnings
    "[Company] Reports Q4 Results" → VALID: earnings
    "[Company] Reports Strong Revenue Growth" → VALID: earnings
    "[Company] Misses Q4 Estimates" → VALID: earnings (miss still causes gap)
- FDA approval, clinical trial results, breakthrough designation
- Major contract wins, strategic partnerships, collaborations
- Crypto/bitcoin treasury announcements
- Clinical study data, feasibility study results
- Acquisitions, mergers, takeover bids
- Significant guidance raises
- IPO or newly listed
- Rebrands, asset sales, divestitures

NOT VALID CATALYSTS (REJECT THESE):
- "Earnings Scheduled For [date]" — this is a FUTURE event, not actual results
- Analyst upgrades/downgrades alone (not fundamental)
- Stock offerings or dilution news (negative)
- General market commentary
- Speculation or rumors without confirmation
- Price target changes only
- Technical breakouts without fundamental news
- Dividend announcements
- Stock splits

ENTITY MATCHING RULE:
Only validate if the headline is ABOUT the queried symbol.
Example: "Nasdaq Gains 1%; TJX Posts Earnings" for symbol XWEL → INVALID (headline is about TJX, not XWEL)

RESPONSE FORMAT:
Respond with EXACTLY one line:
- "VALID: [catalyst type]" if headline indicates a confirmed momentum catalyst
- "INVALID: [reason]" if not a valid catalyst

Examples:
- "VALID: earnings"
- "VALID: fda_approval"
- "VALID: crypto_treasury"
- "VALID: clinical_data"
- "INVALID: scheduled earnings (future event)"
- "INVALID: analyst upgrade only"
- "INVALID: about different symbol"
"""

# Qullamaggie (KK) — stricter EP catalyst definition
KK_SYSTEM_PROMPT = """You are a trading catalyst validator for Qullamaggie-style (Kristjan Kullamägi) momentum trading.

QULLAMAGGIE VALID EP CATALYSTS:
- Earnings beat with strong reaction (gap up on volume)
- Positive earnings surprise with guidance raise
- FDA approval or positive clinical trial results (biotech)
- Major contract wins or strategic partnerships
- Significant guidance raises
- Transformative M&A announcements

NOT VALID CATALYSTS (REJECT THESE):
- Analyst upgrades/downgrades alone (not fundamental)
- Stock offerings or dilution news (negative)
- General market commentary
- Speculation or rumors without confirmation
- Price target changes only
- Technical breakouts without fundamental news
- Dividend announcements
- Stock splits

RESPONSE FORMAT:
Respond with EXACTLY one line:
- "VALID: [catalyst type]" if headline indicates a confirmed Qullamaggie-style catalyst
- "INVALID: [reason]" if not a valid catalyst

Examples:
- "VALID: earnings_beat" 
- "VALID: fda_approval"
- "VALID: major_contract"
- "INVALID: analyst upgrade only"
- "INVALID: offering/dilution"
- "INVALID: no clear catalyst"
"""

# Backward compatibility alias (used by AICatalystValidator legacy class)
SYSTEM_PROMPT = WARRIOR_SYSTEM_PROMPT

# =============================================================================
# NEGATIVE CATALYST REVIEW PROMPT
# =============================================================================

NEGATIVE_REVIEW_PROMPT = """You are reviewing a negative catalyst detection for a momentum day trading scanner.

The regex classifier flagged this headline as potentially harmful. Your job is to determine
whether the headline is GENUINELY NEGATIVE or if the regex MISCLASSIFIED a non-harmful headline.

GENUINELY NEGATIVE (confirm regex — BLOCK the trade):
- Stock offering, direct offering, ATM offering, shelf offering (dilutive)
- SEC investigation, SEC inquiry, subpoena, class action lawsuit
- Earnings miss, guidance cut, lowered outlook, revenue decline
- Bankruptcy, delisting, going concern

FALSE POSITIVES (regex got it wrong — ALLOW the trade):
- "Initial Public Offering" or "IPO" — this is a POSITIVE catalyst, not dilutive
- "Oversubscribed offering" — indicates strong demand, neutral/positive
- "Settlement" in M&A/acquisition context ("settlement of acquisition") — not legal
- "Investigation" in scientific/FDA context ("FDA investigation shows promising results") — not legal
- "Warns of strong demand" or positive warning context — not a guidance cut
- Any headline where the matched word is used in a positive or neutral context

RESPONSE FORMAT:
Respond with EXACTLY one line:
- "NEGATIVE: [reason]" if this IS genuinely harmful and should BLOCK the trade
- "FALSE_POSITIVE: [actual_type]" if the regex misclassified a non-harmful headline
"""


class AICatalystValidator:
    """
    Gemini-based catalyst validator for edge cases.
    
    Only called when:
    1. No earnings found in calendar
    2. Regex classifier didn't match
    3. Headlines exist but are ambiguous
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._client = None
        self._model = None
    
    def _get_client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                self._model = "gemini-2.0-flash-exp"  # Fast and cheap
            except ImportError:
                logger.error("google-genai package not installed")
                raise
        return self._client
    
    def validate_headline(self, headline: str, symbol: str) -> AIValidationResult:
        """
        Validate a single headline using Gemini AI.
        
        Args:
            headline: News headline to validate
            symbol: Stock symbol for context
            
        Returns:
            AIValidationResult with is_valid, catalyst_type, reason
        """
        if not self.api_key:
            logger.warning("No GOOGLE_API_KEY configured, skipping AI validation")
            return AIValidationResult(
                is_valid=False,
                catalyst_type=None,
                reason="AI validation not configured",
                raw_response="",
            )
        
        try:
            client = self._get_client()
            
            user_prompt = f"""Headline: "{headline}"
Symbol: {symbol}

Is this a valid Qullamaggie EP catalyst?"""
            
            response = client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.0,  # Deterministic
                    "max_output_tokens": 50,
                },
            )
            
            raw = response.text.strip()
            
            # Parse response
            if raw.upper().startswith("VALID:"):
                catalyst_type = raw.split(":", 1)[1].strip().lower()
                return AIValidationResult(
                    is_valid=True,
                    catalyst_type=catalyst_type,
                    reason=f"AI confirmed: {catalyst_type}",
                    raw_response=raw,
                )
            elif raw.upper().startswith("INVALID:"):
                reason = raw.split(":", 1)[1].strip()
                return AIValidationResult(
                    is_valid=False,
                    catalyst_type=None,
                    reason=reason,
                    raw_response=raw,
                )
            else:
                # Unexpected format
                logger.warning(f"Unexpected AI response: {raw}")
                return AIValidationResult(
                    is_valid=False,
                    catalyst_type=None,
                    reason=f"Unparseable AI response: {raw[:50]}",
                    raw_response=raw,
                )
                
        except Exception as e:
            logger.error(f"AI validation error: {e}")
            return AIValidationResult(
                is_valid=False,
                catalyst_type=None,
                reason=f"AI error: {str(e)}",
                raw_response="",
            )
    
    def validate_headlines(
        self, 
        headlines: list[str], 
        symbol: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate multiple headlines, return first valid catalyst found.
        
        Returns:
            (has_valid_catalyst, catalyst_type, headline_snippet)
        """
        for headline in headlines[:5]:  # Limit to save API costs
            result = self.validate_headline(headline, symbol)
            if result.is_valid:
                return True, result.catalyst_type, headline[:50]
        
        return False, None, None


# Singleton instance
_validator = None

def get_ai_validator() -> AICatalystValidator:
    """Get or create singleton validator."""
    global _validator
    if _validator is None:
        _validator = AICatalystValidator()
    return _validator


def ai_validate_catalyst(
    headline: str, 
    symbol: str,
) -> AIValidationResult:
    """Convenience function for single headline validation."""
    validator = get_ai_validator()
    return validator.validate_headline(headline, symbol)


# =============================================================================
# MULTI-MODEL COMPARISON SYSTEM
# =============================================================================

@dataclass
class ModelConfig:
    """Configuration for a single AI model."""
    name: str
    model_id: str
    rpm_limit: int
    description: str


# Available models for comparison (Jan 2026 rate limits)
AVAILABLE_MODELS = {
    "flash_lite": ModelConfig(
        name="flash_lite",
        model_id="gemini-2.5-flash-lite",
        rpm_limit=15,
        description="Fast, highest RPM for comparison",
    ),
    "flash": ModelConfig(
        name="flash",
        model_id="gemini-2.5-flash",
        rpm_limit=10,
        description="Balanced speed/quality",
    ),
    "pro": ModelConfig(
        name="pro",
        model_id="gemini-2.5-pro",
        rpm_limit=5,
        description="Best reasoning, limited calls",
    ),
}


@dataclass
class ModelResult:
    """Result from a single model."""
    model_name: str
    is_valid: bool
    catalyst_type: Optional[str]
    reason: str
    latency_ms: int


@dataclass
class ComparisonResult:
    """Combined result from all models + regex."""
    symbol: str
    headline: str
    timestamp: datetime
    regex_type: Optional[str]
    regex_confidence: float
    model_results: Dict[str, ModelResult]
    article_url: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for logging."""
        return {
            "symbol": self.symbol,
            "headline": self.headline[:100],
            "timestamp": self.timestamp.isoformat(),
            "regex": {"type": self.regex_type, "conf": self.regex_confidence},
            "models": {
                name: {
                    "valid": r.is_valid,
                    "type": r.catalyst_type,
                    "reason": r.reason[:50] if r.reason else None,
                    "latency_ms": r.latency_ms,
                }
                for name, r in self.model_results.items()
            },
            "article_url": self.article_url,
        }


class MultiModelValidator:
    """
    Run catalyst validation across multiple AI models for comparison.
    
    Multi-model catalyst validation with tiebreaker system.
    Used for parallel assessment. AI can add catalysts regex missed
    (see warrior_scanner_service.py L1517).
    """
    
    def __init__(
        self,
        models: List[str] = None,
        api_key: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._client = None
        
        # Models to run (default: flash_lite + pro for high/low RPM coverage)
        model_names = models or ["flash_lite", "pro"]
        self.models = {
            name: AVAILABLE_MODELS[name]
            for name in model_names
            if name in AVAILABLE_MODELS
        }
        
        # Rate limiting: track calls per minute per model
        self._call_counts: Dict[str, List[datetime]] = {
            name: [] for name in self.models
        }
        
        # Comparison queue for deferred processing
        self._queue: List[Tuple[str, str, str, float]] = []  # (symbol, headline, regex_type, regex_conf)
        self._queue_lock = None  # Lazy init for async
        
        # Comparison log file
        self._log_path = Path(__file__).parent.parent.parent.parent / "data" / "catalyst_comparison.jsonl"
        
    def _get_client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                logger.error("google-genai package not installed")
                raise
        return self._client
    
    def _can_call_model(self, model_name: str) -> bool:
        """Check if we're under rate limit for this model."""
        config = self.models.get(model_name)
        if not config:
            return False
        
        now = now_et()
        minute_ago = now - timedelta(minutes=1)
        
        # Remove old entries
        self._call_counts[model_name] = [
            t for t in self._call_counts[model_name]
            if t > minute_ago
        ]
        
        return len(self._call_counts[model_name]) < config.rpm_limit
    
    def _record_call(self, model_name: str):
        """Record a call for rate limiting."""
        self._call_counts[model_name].append(now_et())
    
    def _validate_with_model(
        self,
        model_name: str,
        headline: str,
        symbol: str,
        strategy: str = "warrior",
    ) -> ModelResult:
        """Validate headline with a specific model."""
        import time
        
        config = self.models.get(model_name)
        if not config:
            return ModelResult(
                model_name=model_name,
                is_valid=False,
                catalyst_type=None,
                reason="Model not configured",
                latency_ms=0,
            )
        
        if not self._can_call_model(model_name):
            return ModelResult(
                model_name=model_name,
                is_valid=False,
                catalyst_type=None,
                reason="Rate limited",
                latency_ms=0,
            )
        
        try:
            client = self._get_client()
            self._record_call(model_name)
            
            start = time.perf_counter()
            
            if strategy == "warrior":
                user_prompt = f"""Headline: "{headline}"
Symbol: {symbol}

Is this a valid catalyst for a momentum day trade?"""
            else:
                user_prompt = f"""Headline: "{headline}"
Symbol: {symbol}

Is this a valid Qullamaggie EP catalyst?"""
            
            system_prompt = WARRIOR_SYSTEM_PROMPT if strategy == "warrior" else KK_SYSTEM_PROMPT
            
            response = client.models.generate_content(
                model=config.model_id,
                contents=user_prompt,
                config={
                    "system_instruction": system_prompt,
                    "temperature": 0.0,
                    "max_output_tokens": 50,
                },
            )
            
            latency = int((time.perf_counter() - start) * 1000)
            
            # Handle None response (Gemini sometimes returns empty)
            if response.text is None:
                return ModelResult(
                    model_name=model_name,
                    is_valid=False,
                    catalyst_type=None,
                    reason="Empty response from Gemini",
                    latency_ms=latency,
                )
            
            raw = response.text.strip()
            
            if raw.upper().startswith("VALID:"):
                catalyst_type = raw.split(":", 1)[1].strip().lower()
                return ModelResult(
                    model_name=model_name,
                    is_valid=True,
                    catalyst_type=catalyst_type,
                    reason=f"AI confirmed: {catalyst_type}",
                    latency_ms=latency,
                )
            else:
                reason = raw.split(":", 1)[1].strip() if ":" in raw else raw
                return ModelResult(
                    model_name=model_name,
                    is_valid=False,
                    catalyst_type=None,
                    reason=reason,
                    latency_ms=latency,
                )
                
        except Exception as e:
            logger.error(f"[{model_name}] Validation error: {e}")
            return ModelResult(
                model_name=model_name,
                is_valid=False,
                catalyst_type=None,
                reason=f"Error: {str(e)[:50]}",
                latency_ms=0,
            )
    
    def queue_comparison(
        self,
        symbol: str,
        headline: str,
        regex_type: Optional[str],
        regex_confidence: float,
    ):
        """Queue a headline for multi-model comparison (non-blocking)."""
        self._queue.append((symbol, headline, regex_type, regex_confidence))
        logger.debug(f"[MultiModel] Queued {symbol} for comparison (queue size: {len(self._queue)})")
    
    def process_queue(self, max_items: int = 5) -> List[ComparisonResult]:
        """Process queued comparisons (call periodically from background task).
        
        Strategy:
        1. Always run flash_lite (15 RPM - generous limit)
        2. Only run pro (5 RPM) as tiebreaker when regex and flash_lite disagree
        
        This conserves Pro's limited RPM for edge cases that need arbitration.
        """
        results = []
        processed = 0
        
        while self._queue and processed < max_items:
            # Need at least flash_lite available
            if not self._can_call_model("flash_lite"):
                break
            
            symbol, headline, regex_type, regex_conf = self._queue.pop(0)
            
            # Step 1: Always run Flash-Lite (primary AI comparison)
            model_results = {}
            flash_result = self._validate_with_model("flash_lite", headline, symbol)
            model_results["flash_lite"] = flash_result
            
            # Step 2: Determine if we need Pro as tiebreaker
            regex_valid = regex_type is not None and regex_conf >= 0.6
            flash_valid = flash_result.is_valid
            
            need_tiebreaker = regex_valid != flash_valid  # Disagreement
            
            # Step 3: Only call Pro if there's a disagreement AND we have capacity
            if need_tiebreaker and "pro" in self.models and self._can_call_model("pro"):
                pro_result = self._validate_with_model("pro", headline, symbol)
                model_results["pro"] = pro_result
                logger.info(f"[MultiModel] {symbol}: Tiebreaker called - regex={regex_valid}, flash={flash_valid}, pro={pro_result.is_valid}")
            
            if model_results:
                comparison = ComparisonResult(
                    symbol=symbol,
                    headline=headline,
                    timestamp=now_et(),
                    regex_type=regex_type,
                    regex_confidence=regex_conf,
                    model_results=model_results,
                )
                results.append(comparison)
                self._log_comparison(comparison)
                processed += 1
        
        if processed:
            logger.info(f"[MultiModel] Processed {processed} comparisons, {len(self._queue)} remaining in queue")
        
        return results
    
    def _log_comparison(self, result: ComparisonResult):
        """Log comparison to JSONL file for training data AND telemetry DB."""
        import json
        
        # Existing JSONL logging
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a") as f:
                f.write(json.dumps(result.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"[MultiModel] Failed to log comparison: {e}")
        
        # NEW: Write to telemetry DB for Data Explorer
        try:
            # Extract model results
            flash_result = result.model_results.get("flash_lite")
            pro_result = result.model_results.get("pro")
            
            # Determine winner based on method (from validate_sync logic)
            # If pro was called, pro is tiebreaker; otherwise consensus
            if pro_result:
                winner = "pro"
                final_result = "PASS" if pro_result.is_valid else "FAIL"
            elif flash_result:
                # Consensus with regex
                regex_valid = result.regex_type is not None and result.regex_confidence >= 0.6
                if regex_valid == flash_result.is_valid:
                    winner = "consensus"
                else:
                    winner = "flash_only"  # Flash used when Pro rate limited
                final_result = "PASS" if flash_result.is_valid else "FAIL"
            else:
                winner = "regex_only"
                final_result = "PASS" if result.regex_type else "FAIL"
            
            with get_telemetry_session() as db:
                db.add(AIComparisonDB(
                    timestamp=now_utc(),
                    symbol=result.symbol,
                    headline=result.headline[:200] if result.headline else None,
                    article_url=result.article_url,
                    source=None,  # Source not tracked in ComparisonResult
                    regex_result=result.regex_type if result.regex_type else "FAIL",
                    flash_result="PASS" if flash_result and flash_result.is_valid else "FAIL" if flash_result else None,
                    pro_result="PASS" if pro_result and pro_result.is_valid else "FAIL" if pro_result else None,
                    final_result=final_result,
                    winner=winner,
                ))
                db.commit()
        except Exception as e:
            logger.warning(f"[MultiModel] Failed to write AI comparison to DB: {e}")
    
    def validate_sync(
        self,
        headline: str,
        symbol: str,
        regex_passed: bool,
        regex_type: Optional[str] = None,
        article_url: Optional[str] = None,
        strategy: str = "warrior",
    ) -> Tuple[bool, Optional[str], bool, Optional[bool], str]:
        """
        Synchronous dual validation: Regex + Flash-Lite → Pro tiebreaker if disagree.
        
        Args:
            headline: News headline to validate
            symbol: Stock symbol
            regex_passed: Whether regex matched a valid catalyst
            regex_type: Catalyst type from regex (if any)
        
        Returns:
            Tuple of:
            - is_valid: Final verdict (bool)
            - catalyst_type: Type of catalyst (str or None)
            - regex_passed: Echo back for caching (bool)
            - flash_passed: What Flash-Lite said (bool or None if skipped)
            - method: "consensus", "tiebreaker", or "regex_only"
        """
        # Step 1: Call Flash-Lite
        if not self._can_call_model("flash_lite"):
            # Rate limited - fall back to regex only
            logger.warning(f"[MultiModel] {symbol}: Flash rate limited, using regex only")
            # Still write CatalystAudit so symbol appears in audit tab
            try:
                with get_telemetry_session() as db:
                    db.add(CatalystAudit(
                        timestamp=now_utc(),
                        symbol=symbol,
                        result="PASS" if regex_passed else "FAIL",
                        headline=headline[:200] if headline else None,
                        article_url=article_url,
                        source=None,
                        match_type=regex_type,
                        confidence="regex_only",
                    ))
                    db.commit()
            except Exception as e:
                logger.warning(f"Failed to write regex_only catalyst audit: {e}")
            return (regex_passed, regex_type, regex_passed, None, "regex_only")
        
        flash_result = self._validate_with_model("flash_lite", headline, symbol, strategy=strategy)
        flash_passed = flash_result.is_valid
        
        # Step 2: Compare regex vs flash
        if regex_passed == flash_passed:
            # Agreement - use consensus result
            method = "consensus"
            final_valid = regex_passed
            final_type = regex_type if regex_passed else flash_result.catalyst_type
            logger.info(f"[AI vs Regex] {symbol}: Regex={'PASS' if regex_passed else 'FAIL'} Flash={'PASS' if flash_passed else 'FAIL'} → {method}")
            
            # Log comparison (consensus case - flash only)
            model_results = {"flash_lite": flash_result}
        else:
            # Disagreement - need tiebreaker
            model_results = {"flash_lite": flash_result}
            if "pro" in self.models and self._can_call_model("pro"):
                pro_result = self._validate_with_model("pro", headline, symbol, strategy=strategy)
                model_results["pro"] = pro_result  # Include Pro in model_results
                final_valid = pro_result.is_valid
                final_type = pro_result.catalyst_type if pro_result.is_valid else None
                method = "tiebreaker"
                logger.info(f"[AI vs Regex] {symbol}: Regex={'PASS' if regex_passed else 'FAIL'} Flash={'PASS' if flash_passed else 'FAIL'} Pro={'PASS' if final_valid else 'FAIL'} → {method}")
            else:
                # Can't call Pro - fall back to Flash (more conservative than regex)
                final_valid = flash_passed
                final_type = flash_result.catalyst_type if flash_passed else None
                method = "flash_only"
                logger.warning(f"[MultiModel] {symbol}: Pro rate limited, using Flash result")
        
        # Log for training - now includes Pro when tiebreaker was used
        comparison = ComparisonResult(
            symbol=symbol,
            headline=headline,
            timestamp=now_et(),
            regex_type=regex_type,
            regex_confidence=0.9 if regex_passed else 0.0,
            model_results=model_results,
            article_url=article_url,
        )
        self._log_comparison(comparison)
        
        # Debug logging for tracing catalyst decisions
        logger.info(f"[validate_sync] {symbol}: regex={regex_passed}, flash={flash_passed}, final={final_valid}, method={method}")
        
        # Write CatalystAudit to telemetry DB
        try:
            with get_telemetry_session() as db:
                db.add(CatalystAudit(
                    timestamp=now_utc(),
                    symbol=symbol,
                    result="PASS" if final_valid else "FAIL",
                    headline=headline[:200] if headline else None,
                    article_url=article_url,
                    source=None,  # Source not tracked in validate_sync
                    match_type=final_type,
                    confidence=method,  # Use method as confidence (consensus/tiebreaker)
                ))
                db.commit()
        except Exception as e:
            logger.warning(f"Failed to write catalyst audit to DB: {e}")
        
        return (final_valid, final_type, regex_passed, flash_passed, method)
    
    def validate_negative_sync(
        self,
        headline: str,
        symbol: str,
        neg_type: str,
    ) -> Tuple[bool, str]:
        """
        3-party AI review of a negative catalyst rejection.
        
        Matches the positive pipeline pattern:
          Party 1: Regex says negative
          Party 2: Flash-Lite reviews — agrees or disagrees
          Party 3: If disagree → Pro breaks the tie
        
        Fail-closed: If any AI party is unavailable, defaults to
        regex rejection (safe).
        
        Args:
            headline: The flagged headline text
            symbol: Stock symbol
            neg_type: Regex-detected negative type (offering, sec_or_legal, etc.)
        
        Returns:
            Tuple of:
            - is_negative: True if genuinely negative, False if false positive
            - reason: Explanation string
        """
        import time
        
        user_prompt = f"""Headline: "{headline}"
Symbol: {symbol}
Regex match type: {neg_type}

Is this headline genuinely a NEGATIVE catalyst that should BLOCK a momentum trade?
Or is the regex wrong — is this actually a POSITIVE or NEUTRAL event being misclassified?"""
        
        # --- Party 2: Flash-Lite ---
        if not self._can_call_model("flash_lite"):
            logger.warning(f"[NegReview] {symbol}: Flash rate limited, defaulting to regex rejection (fail-closed)")
            return (True, "ai_unavailable_rate_limited")
        
        try:
            client = self._get_client()
            self._record_call("flash_lite")
            
            flash_config = self.models.get("flash_lite")
            if not flash_config:
                return (True, "flash_lite_not_configured")
            
            start = time.perf_counter()
            
            response = client.models.generate_content(
                model=flash_config.model_id,
                contents=user_prompt,
                config={
                    "system_instruction": NEGATIVE_REVIEW_PROMPT,
                    "temperature": 0.0,
                    "max_output_tokens": 60,
                },
            )
            
            flash_latency = int((time.perf_counter() - start) * 1000)
            
            if response.text is None:
                logger.warning(f"[NegReview] {symbol}: Empty Flash response, defaulting to rejection")
                return (True, "ai_empty_response")
            
            flash_raw = response.text.strip()
            flash_says_negative = not flash_raw.upper().startswith("FALSE_POSITIVE:")
            
        except Exception as e:
            logger.error(f"[NegReview] {symbol}: Flash error: {e}, defaulting to rejection (fail-closed)")
            return (True, f"ai_error:{str(e)[:50]}")
        
        # --- Consensus check: Regex (negative) vs Flash-Lite ---
        if flash_says_negative:
            # Both agree: genuinely negative → reject
            reason = flash_raw.split(":", 1)[1].strip() if ":" in flash_raw else flash_raw
            logger.info(
                f"[NegReview] {symbol}: CONSENSUS — Regex({neg_type}) + Flash both say NEGATIVE: {reason} | {flash_latency}ms"
            )
            return (True, f"consensus_negative:{reason}")
        
        # --- Disagreement: Regex says negative, Flash says false positive ---
        flash_actual_type = flash_raw.split(":", 1)[1].strip() if ":" in flash_raw else "unknown"
        logger.info(
            f"[NegReview] {symbol}: DISAGREE — Regex({neg_type}) vs Flash(FALSE_POSITIVE:{flash_actual_type}) | {flash_latency}ms → calling Pro tiebreaker"
        )
        
        # --- Party 3: Pro tiebreaker ---
        if "pro" not in self.models or not self._can_call_model("pro"):
            # Pro unavailable — use Flash verdict (it's the more contextual model)
            logger.warning(
                f"🔄 AI_NEG_OVERRIDE | {symbol} | Pro unavailable, using Flash verdict | "
                f"Regex: {neg_type} | Flash: FALSE_POSITIVE:{flash_actual_type} | "
                f"Headline: {headline[:80]}"
            )
            return (False, f"flash_override:{flash_actual_type}")
        
        try:
            self._record_call("pro")
            pro_config = self.models["pro"]
            
            start = time.perf_counter()
            
            pro_response = client.models.generate_content(
                model=pro_config.model_id,
                contents=user_prompt,
                config={
                    "system_instruction": NEGATIVE_REVIEW_PROMPT,
                    "temperature": 0.0,
                    "max_output_tokens": 1024,  # Pro uses thinking tokens; needs larger budget
                },
            )
            
            pro_latency = int((time.perf_counter() - start) * 1000)
            
            # Extract text — Pro thinking model may put response in candidates
            pro_text = None
            if pro_response.text is not None:
                pro_text = pro_response.text.strip()
            elif hasattr(pro_response, 'candidates') and pro_response.candidates:
                for part in pro_response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        pro_text = part.text.strip()
                        break
            
            if not pro_text:
                # Pro returned nothing — fail-closed, reject
                logger.warning(f"[NegReview] {symbol}: Empty Pro response, defaulting to rejection")
                return (True, "pro_empty_response")
            
            pro_says_negative = not pro_text.upper().startswith("FALSE_POSITIVE:")
            
            if pro_says_negative:
                # Pro agrees with regex: genuinely negative → reject
                pro_reason = pro_text.split(":", 1)[1].strip() if ":" in pro_text else pro_text
                logger.info(
                    f"[NegReview] {symbol}: PRO_TIEBREAKER → NEGATIVE: {pro_reason} | "
                    f"Regex({neg_type}) + Pro agree, Flash overruled | {pro_latency}ms"
                )
                return (True, f"pro_confirmed:{pro_reason}")
            else:
                # Pro agrees with Flash: false positive → allow through
                pro_actual_type = pro_text.split(":", 1)[1].strip() if ":" in pro_text else "unknown"
                logger.warning(
                    f"🔄 AI_NEG_OVERRIDE | {symbol} | PRO_TIEBREAKER → FALSE_POSITIVE | "
                    f"Regex: {neg_type} | Flash: {flash_actual_type} | Pro: {pro_actual_type} | "
                    f"Headline: {headline[:80]} | {pro_latency}ms"
                )
                return (False, f"tiebreaker_override:{pro_actual_type}")
                
        except Exception as e:
            # Pro error — fail-closed, reject (don't trust Flash alone without tiebreaker)
            logger.error(f"[NegReview] {symbol}: Pro error: {e}, defaulting to rejection (fail-closed)")
            return (True, f"pro_error:{str(e)[:50]}")

    
    def get_stats(self) -> dict:
        """Get rate limit and queue stats."""
        now = now_et()
        minute_ago = now - timedelta(minutes=1)
        
        return {
            "queue_size": len(self._queue),
            "models": {
                name: {
                    "rpm_limit": config.rpm_limit,
                    "calls_last_minute": len([
                        t for t in self._call_counts.get(name, [])
                        if t > minute_ago
                    ]),
                    "available": self._can_call_model(name),
                }
                for name, config in self.models.items()
            },
        }


# Singleton instance
_multi_validator: Optional[MultiModelValidator] = None


def get_multi_validator() -> MultiModelValidator:
    """Get or create singleton multi-model validator."""
    global _multi_validator
    if _multi_validator is None:
        _multi_validator = MultiModelValidator()
    return _multi_validator
