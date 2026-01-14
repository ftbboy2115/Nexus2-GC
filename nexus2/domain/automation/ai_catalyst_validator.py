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
        if datetime.now() - cached.cached_at > self._ttl:
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
            cached_at=datetime.now(),
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
        
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Remove old entries
        self._call_counts[model_name] = [
            t for t in self._call_counts[model_name]
            if t > minute_ago
        ]
        
        return len(self._call_counts[model_name]) < config.rpm_limit
    
    def _record_call(self, model_name: str):
        """Record a call for rate limiting."""
        self._call_counts[model_name].append(datetime.now())
    
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
                    timestamp=datetime.now(),
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
    
    def get_stats(self) -> dict:
        """Get rate limit and queue stats."""
        now = datetime.now()
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
