"""
AI Catalyst Validator

Uses Gemini AI to validate ambiguous headlines when regex doesn't match.
Only called as a fallback when deterministic checks are inconclusive.

Includes shared cache for cross-strategy catalyst validation.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict
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
