"""
EP Detection Service

Identifies and validates EP candidates.
Based on: ep_setup_research.md, implementation_plan.md
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Protocol

from nexus2.domain.setup_detection.ep_models import (
    EPCandidate,
    EPSetup,
    EPCandidateStatus,
    EPValidationResult,
    CatalystType,
    OpeningRange,
)


@dataclass
class EPSettings:
    """Settings for EP detection."""
    
    # Gap thresholds
    min_gap_percent: Decimal = Decimal("8.0")   # KK: 8-10%+
    ideal_gap_percent: Decimal = Decimal("10.0")
    
    # Volume thresholds
    min_relative_volume: Decimal = Decimal("2.0")   # 2x average
    ideal_relative_volume: Decimal = Decimal("3.0")  # 3x+ preferred
    
    # Opening range
    opening_range_minutes: int = 5  # 1, 5, or 60
    
    # ATR constraint
    max_atr_ratio: Decimal = Decimal("1.0")
    ideal_atr_ratio: Decimal = Decimal("0.5")
    
    # Price filters (inherit from scanner)
    min_price: Decimal = Decimal("5.0")
    abs_min_price: Decimal = Decimal("2.0")


class MarketDataProvider(Protocol):
    """Protocol for market data."""
    
    def get_prev_close(self, symbol: str) -> Decimal:
        ...
    
    def get_current_price(self, symbol: str) -> Decimal:
        ...
    
    def get_atr(self, symbol: str, period: int = 14) -> Decimal:
        ...
    
    def get_adr_percent(self, symbol: str, period: int = 14) -> Decimal:
        ...
    
    def get_average_volume(self, symbol: str, period: int = 20) -> int:
        ...


class EPDetectionService:
    """
    Identifies and validates EP candidates.
    
    Responsibilities:
    - Scan for stocks with catalyst gaps
    - Validate candidates against EP criteria
    - Establish opening ranges
    - Create actionable EPSetup objects
    """
    
    def __init__(self, settings: EPSettings):
        self.settings = settings
    
    def create_candidate(
        self,
        symbol: str,
        catalyst_date,
        catalyst_type: CatalystType,
        catalyst_description: str,
        prev_close: Decimal,
        open_price: Decimal,
        pre_market_volume: int,
        avg_volume: int,
        atr: Decimal,
        adr_percent: Decimal,
    ) -> EPCandidate:
        """
        Create an EP candidate from raw data.
        
        Args:
            symbol: Stock symbol
            catalyst_date: Date of catalyst
            catalyst_type: Type of catalyst
            catalyst_description: Description of catalyst
            prev_close: Previous day's close
            open_price: Today's open price
            pre_market_volume: Pre-market volume
            avg_volume: Average daily volume
            atr: Average True Range
            adr_percent: Average Daily Range %
            
        Returns:
            EPCandidate object
        """
        gap_percent = ((open_price - prev_close) / prev_close) * 100
        relative_volume = Decimal(pre_market_volume) / Decimal(avg_volume) if avg_volume > 0 else Decimal("0")
        
        return EPCandidate(
            symbol=symbol,
            catalyst_date=catalyst_date,
            catalyst_type=catalyst_type,
            catalyst_description=catalyst_description,
            gap_percent=gap_percent,
            prev_close=prev_close,
            open_price=open_price,
            pre_market_volume=pre_market_volume,
            relative_volume=relative_volume,
            atr=atr,
            adr_percent=adr_percent,
            status=EPCandidateStatus.PENDING,
        )
    
    def validate_candidate(
        self,
        candidate: EPCandidate,
    ) -> EPValidationResult:
        """
        Validate candidate against EP criteria.
        
        Checks:
        - Gap percentage meets minimum
        - Relative volume meets minimum
        - Price meets minimum
        - Not too extended
        
        Args:
            candidate: EP candidate to validate
            
        Returns:
            Validation result
        """
        s = self.settings
        
        # Check gap
        if candidate.gap_percent < s.min_gap_percent:
            return EPValidationResult.INVALID_GAP
        
        # Check volume
        if candidate.relative_volume < s.min_relative_volume:
            return EPValidationResult.INVALID_VOLUME
        
        # Check price (using open as current)
        if candidate.open_price < s.abs_min_price:
            return EPValidationResult.INVALID_PRICE
        
        return EPValidationResult.VALID
    
    def establish_opening_range(
        self,
        candidate: EPCandidate,
        high: Decimal,
        low: Decimal,
        timeframe_minutes: Optional[int] = None,
    ) -> EPCandidate:
        """
        Establish opening range for candidate.
        
        Args:
            candidate: EP candidate
            high: High of opening range
            low: Low of opening range (LOD)
            timeframe_minutes: Opening range timeframe
            
        Returns:
            Updated candidate with opening range
        """
        tf = timeframe_minutes or self.settings.opening_range_minutes
        
        candidate.opening_range = OpeningRange(
            high=high,
            low=low,
            timeframe_minutes=tf,
            established_at=datetime.now(),
        )
        candidate.status = EPCandidateStatus.ACTIVE
        
        return candidate
    
    def set_ep_candle_low(
        self,
        candidate: EPCandidate,
        ep_candle_low: Decimal,
    ) -> EPCandidate:
        """
        Set the EP candle low (setup invalidation level).
        
        This is typically the full day low of the EP candle.
        
        Args:
            candidate: EP candidate
            ep_candle_low: Low of the EP day
            
        Returns:
            Updated candidate
        """
        candidate.ep_candle_low = ep_candle_low
        return candidate
    
    def check_orh_break(
        self,
        candidate: EPCandidate,
        current_price: Decimal,
    ) -> bool:
        """
        Check if Opening Range High has been broken.
        
        Args:
            candidate: Active EP candidate
            current_price: Current price
            
        Returns:
            True if ORH has been broken
        """
        if not candidate.opening_range:
            return False
        
        return current_price > candidate.opening_range.high
    
    def create_setup(
        self,
        candidate: EPCandidate,
        entry_price: Optional[Decimal] = None,
    ) -> EPSetup:
        """
        Create actionable setup from validated candidate.
        
        Args:
            candidate: Validated EP candidate
            entry_price: Entry price (defaults to ORH)
            
        Returns:
            EPSetup object
        """
        if not candidate.opening_range:
            raise ValueError("Candidate must have opening range")
        
        # Validate ATR constraint
        orh = candidate.opening_range.high
        lod = candidate.opening_range.low
        entry = entry_price or orh
        stop_distance = entry - lod
        stop_atr_ratio = stop_distance / candidate.atr if candidate.atr > 0 else Decimal("999")
        
        setup = EPSetup.from_candidate(candidate, entry_price=entry)
        
        # Additional validation
        if stop_atr_ratio > self.settings.max_atr_ratio:
            setup.is_valid = False
            setup.invalidation_reason = f"Stop {stop_atr_ratio:.2f}x ATR exceeds max {self.settings.max_atr_ratio}x"
        
        return setup
    
    def scan_for_candidates(
        self,
        symbols: List[str],
        market_data: MarketDataProvider,
        catalyst_info: dict,  # symbol -> (type, description)
    ) -> List[EPCandidate]:
        """
        Scan list of symbols for EP candidates.
        
        Args:
            symbols: Symbols to scan
            market_data: Market data provider
            catalyst_info: Dict of catalyst info per symbol
            
        Returns:
            List of EP candidates meeting criteria
        """
        candidates = []
        today = datetime.now().date()
        
        for symbol in symbols:
            try:
                prev_close = market_data.get_prev_close(symbol)
                current_price = market_data.get_current_price(symbol)
                
                # Calculate gap
                gap_pct = ((current_price - prev_close) / prev_close) * 100
                
                # Quick filter before full candidate creation
                if gap_pct < self.settings.min_gap_percent:
                    continue
                
                # Get additional data
                atr = market_data.get_atr(symbol)
                adr = market_data.get_adr_percent(symbol)
                avg_vol = market_data.get_average_volume(symbol)
                
                # Get catalyst info
                cat_type, cat_desc = catalyst_info.get(
                    symbol, 
                    (CatalystType.OTHER, "Unknown catalyst")
                )
                
                candidate = self.create_candidate(
                    symbol=symbol,
                    catalyst_date=today,
                    catalyst_type=cat_type,
                    catalyst_description=cat_desc,
                    prev_close=prev_close,
                    open_price=current_price,  # Using current as proxy
                    pre_market_volume=0,  # Would need pre-market data
                    avg_volume=avg_vol,
                    atr=atr,
                    adr_percent=adr,
                )
                
                # Validate
                if self.validate_candidate(candidate) == EPValidationResult.VALID:
                    candidates.append(candidate)
                    
            except Exception as e:
                print(f"Error scanning {symbol}: {e}")
        
        return candidates
