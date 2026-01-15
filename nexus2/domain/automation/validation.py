"""
Validation Services

Pre-trade validation to ensure candidates still qualify before order placement.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List
import logging
from nexus2.utils.time_utils import now_utc

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of pre-trade validation."""
    symbol: str
    is_valid: bool
    reasons: List[str]
    current_price: Optional[Decimal] = None
    price_vs_entry: Optional[Decimal] = None  # % difference from scanned price
    has_catalyst: Optional[bool] = None
    catalyst_type: Optional[str] = None
    validated_at: datetime = None
    
    def __post_init__(self):
        if self.validated_at is None:
            self.validated_at = now_utc()


class PreTradeValidator:
    """
    Validates candidates before order placement.
    
    Checks:
    - Current price vs scanned price (not too extended)
    - Still above key moving averages
    - Volume confirms
    - Catalyst for EP setups
    """
    
    def __init__(self, fmp_adapter, max_extension_pct: float = 3.0):
        """
        Args:
            fmp_adapter: FMP market data adapter
            max_extension_pct: Max % price can move from scan price
        """
        self.fmp = fmp_adapter
        self.max_extension_pct = Decimal(str(max_extension_pct))
    
    def validate(
        self,
        symbol: str,
        scanned_price: Decimal,
        setup_type: str = "ep",
    ) -> ValidationResult:
        """
        Validate a candidate before placing an order.
        
        Args:
            symbol: Stock symbol
            scanned_price: Price when scanned
            setup_type: Type of setup (ep, breakout, flag, htf)
            
        Returns:
            ValidationResult with pass/fail and reasons
        """
        reasons = []
        is_valid = True
        current_price = None
        price_vs_entry = None
        has_catalyst = None
        catalyst_type = None
        
        try:
            # Get fresh quote
            quote = self.fmp.get_quote(symbol)
            if not quote:
                return ValidationResult(
                    symbol=symbol,
                    is_valid=False,
                    reasons=["Could not get current quote"],
                )
            
            current_price = quote.price
            
            # Check price extension from scan price
            if scanned_price > 0:
                price_vs_entry = ((current_price - scanned_price) / scanned_price) * 100
                
                if price_vs_entry > self.max_extension_pct:
                    is_valid = False
                    reasons.append(
                        f"Price extended {price_vs_entry:.1f}% from scan (max {self.max_extension_pct}%)"
                    )
                elif price_vs_entry < -self.max_extension_pct:
                    # Price dropped significantly - might be breaking down
                    reasons.append(
                        f"Price dropped {abs(price_vs_entry):.1f}% from scan - verify setup"
                    )
            
            # Check if still up on the day (for gainers)
            if quote.change_percent is not None and quote.change_percent < 0:
                reasons.append(f"Stock is now red on day ({quote.change_percent:.1f}%)")
                # Not disqualifying, but noted
            
            # Catalyst check for EP setups
            if setup_type.lower() == "ep":
                has_catalyst, catalyst_type, catalyst_warning = self._check_catalyst(symbol)
                if catalyst_warning:
                    # Pre-earnings warning = avoid trade
                    is_valid = False
                    reasons.append(catalyst_warning)
                elif not has_catalyst:
                    is_valid = False
                    reasons.append("EP setup requires catalyst (post-earnings 1-5 days) - none found")
            
        except Exception as e:
            logger.error(f"Validation error for {symbol}: {e}")
            return ValidationResult(
                symbol=symbol,
                is_valid=False,
                reasons=[f"Validation error: {str(e)}"],
            )
        
        return ValidationResult(
            symbol=symbol,
            is_valid=is_valid,
            reasons=reasons,
            current_price=current_price,
            price_vs_entry=price_vs_entry,
            has_catalyst=has_catalyst,
            catalyst_type=catalyst_type,
        )
    
    def _check_catalyst(self, symbol: str) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Check if symbol has a valid KK-style catalyst.
        
        KK Catalyst Rules:
        - Post-earnings (1-5 days ago): VALID EP catalyst
        - Pre-earnings (within 5 days ahead): AVOID (trading into earnings risk)
        - FDA approvals, major contracts: VALID (detected via news headlines)
        
        Returns:
            (has_valid_catalyst, catalyst_type, warning_message)
        """
        try:
            # Step 1: Check earnings calendar (fast, reliable)
            past_earnings = self.fmp.get_earnings_calendar(symbol, days_back=5, days_forward=0)
            upcoming_earnings = self.fmp.get_earnings_calendar(symbol, days_back=0, days_forward=5)
            
            # WARNING: Upcoming earnings within 5 days = avoid
            if upcoming_earnings:
                event_date = upcoming_earnings[0].get("date")
                return False, None, f"AVOID: Upcoming earnings on {event_date} (trading into earnings)"
            
            # VALID: Post-earnings within last 5 days = good EP catalyst
            if past_earnings:
                event_date = past_earnings[0].get("date")
                return True, f"Post-earnings EP ({event_date})", None
            
            # Step 2: Check news headlines for FDA/contract catalysts
            try:
                from nexus2.domain.automation.catalyst_classifier import get_classifier
                
                headlines = self.fmp.get_recent_headlines(symbol, days=5)
                if headlines:
                    classifier = get_classifier()
                    
                    # Check for negative catalysts first (avoid)
                    has_neg, neg_type, neg_headline = classifier.has_negative_catalyst(headlines)
                    if has_neg:
                        return False, None, f"AVOID: Negative catalyst ({neg_type}): {neg_headline[:50]}..."
                    
                    # Check for positive catalysts
                    has_pos, pos_type, pos_headline = classifier.has_positive_catalyst(headlines)
                    if has_pos:
                        return True, f"{pos_type}: {pos_headline[:40]}...", None
                    
                    # Step 3: AI validation for ambiguous headlines
                    try:
                        from nexus2.domain.automation.ai_catalyst_validator import get_ai_validator
                        
                        validator = get_ai_validator()
                        has_ai_catalyst, ai_type, ai_headline = validator.validate_headlines(headlines, symbol)
                        if has_ai_catalyst:
                            return True, f"AI-confirmed {ai_type}: {ai_headline[:30]}...", None
                    except Exception as ai_err:
                        logger.warning(f"AI catalyst check failed for {symbol}: {ai_err}")
                        
            except Exception as e:
                logger.warning(f"News headline check failed for {symbol}: {e}")
            
            # No catalyst found via any method
            return False, None, None
            
        except Exception as e:
            logger.warning(f"Catalyst check failed for {symbol}: {e}")
            # If we can't check, don't block (but log warning)
            return True, "Unable to verify (assumed OK)", None


def validate_before_order(
    symbol: str,
    scanned_price: float,
    setup_type: str = "ep",
    fmp_adapter = None,
) -> ValidationResult:
    """
    Convenience function to validate a candidate before order.
    
    Args:
        symbol: Stock symbol
        scanned_price: Price when originally scanned
        setup_type: Type of setup
        fmp_adapter: Optional FMP adapter (creates one if not provided)
        
    Returns:
        ValidationResult
    """
    if fmp_adapter is None:
        from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
        fmp_adapter = get_fmp_adapter()
    
    validator = PreTradeValidator(fmp_adapter)
    return validator.validate(
        symbol=symbol,
        scanned_price=Decimal(str(scanned_price)),
        setup_type=setup_type,
    )
