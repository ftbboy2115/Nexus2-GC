"""
Breakout/Flag Scanner Service

Identifies KK-style consolidation and breakout patterns.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from enum import Enum

from nexus2.adapters.market_data import UnifiedMarketData
from nexus2.utils.time_utils import now_et


class BreakoutStatus(Enum):
    """Status of a breakout candidate."""
    CONSOLIDATING = "consolidating"    # In tight consolidation, not yet breaking
    BREAKING_OUT = "breaking_out"      # Currently breaking above consolidation
    EXTENDED = "extended"              # Too extended, missed the entry
    INVALID = "invalid"                # Doesn't meet criteria


@dataclass
class BreakoutScanSettings:
    """Settings for breakout/flag scanning."""
    # Qualifying filters
    min_price: Decimal = Decimal("5.0")
    min_dollar_vol: Decimal = Decimal("5000000")  # $5M+
    min_rs_percentile: int = 50  # Lowered - RS calc needs improvement
    
    # Consolidation criteria
    max_pullback_pct: Decimal = Decimal("15.0")   # Max 15% from highs
    tightness_threshold: Decimal = Decimal("0.50") # Recent range < 50% of prior (tighter)
    volume_contraction: Decimal = Decimal("0.95")  # Volume < 95% of avg (relaxed)
    
    # Breakout criteria
    breakout_volume_multiple: Decimal = Decimal("1.5")  # Volume > 1.5x avg
    
    # Lookback periods
    consolidation_days: int = 10  # Days to check for consolidation
    prior_trend_days: int = 20    # Days to check for prior trend


@dataclass
class BreakoutCandidate:
    """A stock showing breakout/flag pattern."""
    symbol: str
    name: str
    price: Decimal
    
    # Pattern metrics
    consolidation_high: Decimal
    consolidation_low: Decimal
    tightness_score: Decimal      # 0-1, lower = tighter
    volume_ratio: Decimal         # Current vol / avg vol
    
    # Position in pattern
    distance_to_breakout: Decimal # % below consolidation high
    pullback_from_high: Decimal   # % below 20-day high
    
    # Quality metrics
    rs_percentile: int
    ma_stacked: bool
    
    # Status
    status: BreakoutStatus
    
    # Entry/Stop levels
    entry_price: Optional[Decimal] = None  # Consolidation high
    stop_price: Optional[Decimal] = None   # Consolidation low
    
    # Metadata
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class BreakoutScanResult:
    """Result from breakout scan."""
    candidates: List[BreakoutCandidate]
    processed_count: int
    scan_time: datetime


class BreakoutScannerService:
    """
    Breakout/Flag Scanner Service.
    
    Identifies consolidation patterns and potential breakouts.
    """
    
    def __init__(
        self,
        settings: Optional[BreakoutScanSettings] = None,
        market_data: Optional[UnifiedMarketData] = None,
    ):
        self.settings = settings or BreakoutScanSettings()
        self.market_data = market_data or UnifiedMarketData()
    
    def scan(self, symbols: Optional[List[str]] = None, verbose: bool = False) -> BreakoutScanResult:
        """
        Scan for breakout candidates.
        
        Args:
            symbols: Additional symbols to include (merged with screener universe)
            verbose: Print verbose output
            
        Returns:
            BreakoutScanResult with candidates
        """
        # Get universe from screener
        candidates = self.market_data.fmp.screen_stocks(
            min_market_cap=500_000_000,
            min_price=float(self.settings.min_price),
            min_volume=500_000,
            limit=200,
        )
        universe = [c["symbol"] for c in candidates]
        
        # Merge with extra symbols (e.g., recent exits for re-entry)
        if symbols:
            extra_count = len([s for s in symbols if s not in universe])
            universe = list(set(universe + symbols))
            if verbose and extra_count > 0:
                print(f"[Breakout] Added {extra_count} extra symbols for re-entry eval")
        
        if verbose:
            print(f"[Breakout] Scanning {len(universe)} symbols...")
        
        results = []
        processed = 0
        total = len(universe)
        progress_thresholds = {25, 50, 75}
        logged_thresholds = set()
        
        for symbol in universe:
            processed += 1
            
            # Log progress at 25%, 50%, 75%
            if total > 0:
                pct = int((processed / total) * 100)
                for threshold in progress_thresholds:
                    if pct >= threshold and threshold not in logged_thresholds:
                        print(f"🔄 [Breakout Scanner] Processing {processed}/{total} ({threshold}%)...")
                        logged_thresholds.add(threshold)
            
            try:
                candidate = self._evaluate_symbol(symbol, verbose)
                if candidate and candidate.status != BreakoutStatus.INVALID:
                    results.append(candidate)
            except Exception as e:
                if verbose:
                    print(f"[Breakout] Error on {symbol}: {e}")
        
        # Sort by tightness (tighter = better)
        results.sort(key=lambda c: c.tightness_score)
        
        return BreakoutScanResult(
            candidates=results,
            processed_count=processed,
            scan_time=now_et(),
        )
    
    def _evaluate_symbol(self, symbol: str, verbose: bool = False) -> Optional[BreakoutCandidate]:
        """Evaluate a symbol for breakout pattern."""
        # Get daily bars
        bars = self.market_data.fmp.get_daily_bars(symbol, limit=60)
        if not bars or len(bars) < 30:
            return None
        
        # Get current quote
        quote = self.market_data.fmp.get_quote(symbol)
        if not quote:
            return None
        
        current_price = Decimal(str(quote.price))
        
        # Pre-filter: price
        if current_price < self.settings.min_price:
            return None
        
        # Get stock info for name
        info = self.market_data.fmp.get_stock_info(symbol)
        name = info.name if info else symbol
        
        # Calculate metrics
        closes = [Decimal(str(b.close)) for b in bars]
        highs = [Decimal(str(b.high)) for b in bars]
        lows = [Decimal(str(b.low)) for b in bars]
        volumes = [b.volume for b in bars]
        
        # Check dollar volume
        avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else sum(volumes) / len(volumes)
        dollar_vol = current_price * Decimal(str(avg_volume))
        if dollar_vol < self.settings.min_dollar_vol:
            return None
        
        # Check MA alignment (stacked)
        sma10 = sum(closes[-10:]) / 10
        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sma20
        ma_stacked = current_price > sma10 > sma20 > sma50
        
        # ENFORCE: MAs must be stacked for flag breakouts (KK-style)
        # This filters out downtrend bounces (e.g., CMCSA above 20 but below 50)
        if not ma_stacked:
            return None
        
        # Calculate RS percentile using RS Service (true percentile ranking)
        from nexus2.domain.scanner.rs_service import get_rs_service
        rs_percentile = get_rs_service().get_rs_percentile(symbol)
        
        if rs_percentile < self.settings.min_rs_percentile:
            return None
        
        # Consolidation detection
        consol_days = self.settings.consolidation_days
        prior_days = self.settings.prior_trend_days
        
        # Recent consolidation range
        recent_highs = highs[-consol_days:]
        recent_lows = lows[-consol_days:]
        consolidation_high = max(recent_highs)
        consolidation_low = min(recent_lows)
        recent_range = consolidation_high - consolidation_low
        
        # Prior range (for tightness comparison)
        prior_highs = highs[-(consol_days + prior_days):-consol_days]
        prior_lows = lows[-(consol_days + prior_days):-consol_days]
        if prior_highs and prior_lows:
            prior_range = max(prior_highs) - min(prior_lows)
        else:
            prior_range = recent_range
        
        # Tightness score (lower = tighter)
        tightness_score = recent_range / prior_range if prior_range > 0 else Decimal("1")
        
        # Volume contraction
        recent_avg_vol = sum(volumes[-consol_days:]) / consol_days
        prior_avg_vol = sum(volumes[-(consol_days + prior_days):-consol_days]) / prior_days if prior_days > 0 else recent_avg_vol
        volume_ratio = Decimal(str(recent_avg_vol / prior_avg_vol)) if prior_avg_vol > 0 else Decimal("1")
        
        # Distance to breakout
        distance_to_breakout = ((consolidation_high - current_price) / consolidation_high) * 100
        
        # Pullback from 20-day high
        high_20d = max(highs[-20:])
        pullback_from_high = ((high_20d - current_price) / high_20d) * 100
        
        # Determine status
        status = BreakoutStatus.INVALID
        
        # Check if too extended (pullback too small, already ran)
        if pullback_from_high < Decimal("2"):
            status = BreakoutStatus.EXTENDED
        # Check if consolidating (tight, volume contracting, near highs)
        elif (tightness_score <= self.settings.tightness_threshold and
              volume_ratio <= self.settings.volume_contraction and
              pullback_from_high <= self.settings.max_pullback_pct):
            status = BreakoutStatus.CONSOLIDATING
        # Check if breaking out (above consolidation high with volume)
        elif current_price >= consolidation_high:
            current_vol = volumes[-1] if volumes else 0
            if current_vol > avg_volume * float(self.settings.breakout_volume_multiple):
                status = BreakoutStatus.BREAKING_OUT
            else:
                status = BreakoutStatus.EXTENDED  # Broke out but no volume
        
        if status == BreakoutStatus.INVALID:
            return None
        
        return BreakoutCandidate(
            symbol=symbol,
            name=name,
            price=current_price,
            consolidation_high=consolidation_high,
            consolidation_low=consolidation_low,
            tightness_score=tightness_score,
            volume_ratio=volume_ratio,
            distance_to_breakout=distance_to_breakout,
            pullback_from_high=pullback_from_high,
            rs_percentile=rs_percentile,
            ma_stacked=ma_stacked,
            status=status,
            entry_price=consolidation_high,
            stop_price=consolidation_low,
        )


# Singleton instance
_breakout_scanner: Optional[BreakoutScannerService] = None


def get_breakout_scanner_service() -> BreakoutScannerService:
    """Get singleton breakout scanner service."""
    global _breakout_scanner
    if _breakout_scanner is None:
        _breakout_scanner = BreakoutScannerService()
    return _breakout_scanner
