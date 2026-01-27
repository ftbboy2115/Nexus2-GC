"""
AI Catalyst Validator

Uses Gemini AI to validate ambiguous headlines when regex doesn't match.
Only called as a fallback when deterministic checks are inconclusive.

Includes shared cache for cross-strategy catalyst validation.
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass
from nexus2.utils.time_utils import now_et

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
    TTL is 14 days - old headlines are pruned on load.
    """
    
    def __init__(self, cache_path: Optional[Path] = None, ttl_days: int = 14):
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


# Qullamaggie-aligned system prompt
SYSTEM_PROMPT = """You are a trading catalyst validator for Qullamaggie-style (Kristjan Kullamägi) momentum trading.

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
        }


class MultiModelValidator:
    """
    Run catalyst validation across multiple AI models for comparison.
    
    Used to train regex patterns by comparing regex vs AI results.
    Trading decisions still use regex only.
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
            
            user_prompt = f"""Headline: "{headline}"
Symbol: {symbol}

Is this a valid Qullamaggie EP catalyst?"""
            
            response = client.models.generate_content(
                model=config.model_id,
                contents=user_prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
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
        """Log comparison to JSONL file for training data."""
        import json
        
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a") as f:
                f.write(json.dumps(result.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"[MultiModel] Failed to log comparison: {e}")
    
    def validate_sync(
        self,
        headline: str,
        symbol: str,
        regex_passed: bool,
        regex_type: Optional[str] = None,
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
            return (regex_passed, regex_type, regex_passed, None, "regex_only")
        
        flash_result = self._validate_with_model("flash_lite", headline, symbol)
        flash_passed = flash_result.is_valid
        
        # Step 2: Compare regex vs flash
        if regex_passed == flash_passed:
            # Agreement - use consensus result
            method = "consensus"
            final_valid = regex_passed
            final_type = regex_type if regex_passed else flash_result.catalyst_type
            logger.info(f"[AI vs Regex] {symbol}: Regex={'PASS' if regex_passed else 'FAIL'} Flash={'PASS' if flash_passed else 'FAIL'} → {method}")
        else:
            # Disagreement - need tiebreaker
            if "pro" in self.models and self._can_call_model("pro"):
                pro_result = self._validate_with_model("pro", headline, symbol)
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
        
        # Log for training
        comparison = ComparisonResult(
            symbol=symbol,
            headline=headline,
            timestamp=now_et(),
            regex_type=regex_type,
            regex_confidence=0.9 if regex_passed else 0.0,
            model_results={"flash_lite": flash_result},
        )
        self._log_comparison(comparison)
        
        # Debug logging for tracing catalyst decisions
        logger.info(f"[validate_sync] {symbol}: regex={regex_passed}, flash={flash_passed}, final={final_valid}, method={method}")
        
        return (final_valid, final_type, regex_passed, flash_passed, method)
    
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
