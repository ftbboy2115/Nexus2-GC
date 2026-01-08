"""
HTF (High-Tight Flag) Scanner Service

Identifies KK-style High-Tight Flag patterns:
- +90%+ move in the "pole"
- ≤25% pullback in the "flag"
- Strong volume, liquid stocks

Based on legacy: core/scan_htf.py v3.0.0
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from enum import Enum

from nexus2.adapters.market_data import UnifiedMarketData


# =============================================================================
# SETTINGS & MODELS
# =============================================================================

@dataclass
class HTFScanSettings:
    """Settings for HTF scanning (KK-style High-Tight Flag)."""
    
    # Move requirements (the "pole")
    min_move_pct: Decimal = Decimal("90.0")  # +90% move minimum
    lookback_days: int = 60  # Window to find the move
    
    # Pullback requirements (the "flag")
    max_pullback_pct: Decimal = Decimal("25.0")  # Max 25% from high
    
    # Quality filters
    min_price: Decimal = Decimal("4.0")
    min_dollar_vol: Decimal = Decimal("5000000")  # $5M
    min_share_vol: int = 500000
    
    # Tightness (optional, for ranking)
    min_tightness_score: Decimal = Decimal("0.0")  # 0-100
    
    # Extended threshold (KK-style: stocks <5% from high are "extended")
    # Lower this for testing (e.g., 2.0) to include more candidates
    extended_threshold_pct: Decimal = Decimal("5.0")  # Default: KK-recommended


class HTFStatus(Enum):
    """Status of HTF candidate."""
    FORMING = "forming"       # Pattern is developing
    COMPLETE = "complete"     # Pattern complete, ready for breakout
    BREAKING_OUT = "breaking_out"  # Breaking out now
    EXTENDED = "extended"     # Too extended to trade
    INVALID = "invalid"       # Doesn't meet criteria


@dataclass
class HTFCandidate:
    """A stock showing High-Tight Flag pattern."""
    
    symbol: str
    name: str
    price: Decimal
    
    # Pattern metrics
    move_pct: Decimal           # Size of the pole move
    pullback_pct: Decimal       # Current pullback from high
    highest_high: Decimal       # Peak of the move
    lowest_low: Decimal         # Base of the move
    
    # Volume & Quality
    dollar_volume: Decimal
    rs_percentile: int = 0
    
    # Status
    status: HTFStatus = HTFStatus.FORMING
    
    # Entry/Stop zones
    entry_price: Optional[Decimal] = None  # Break of consolidation high
    stop_price: Optional[Decimal] = None   # Low of flag consolidation
    
    # Metadata
    sector: str = "Unknown"
    detected_at: datetime = field(default_factory=datetime.now)
    
    @property
    def risk_reward_ratio(self) -> Optional[Decimal]:
        """Calculate R:R if entry/stop defined."""
        if self.entry_price and self.stop_price and self.stop_price > 0:
            risk = self.entry_price - self.stop_price
            if risk > 0:
                # Target = 2x the pole move (conservative)
                target = self.entry_price + (self.move_pct / 100 * self.entry_price)
                reward = target - self.entry_price
                return reward / risk
        return None


@dataclass
class HTFScanResult:
    """Result from HTF scan."""
    candidates: List[HTFCandidate]
    processed_count: int
    scan_time: datetime = field(default_factory=datetime.now)


# =============================================================================
# BLACKLISTS
# =============================================================================

BLACKLIST_SECTORS = ["Aerospace & Defense", "Tobacco"]
BLACKLIST_TICKERS = ["PLBY"]


# =============================================================================
# SERVICE
# =============================================================================

class HTFScannerService:
    """
    High-Tight Flag Scanner Service.
    
    Identifies KK-style HTF patterns:
    - Big move (+90%+) = the "pole"
    - Tight consolidation (≤25% pullback) = the "flag"
    - Looking for breakout above flag high
    
    Based on legacy scan_htf.py v3.0.0
    """
    
    def __init__(
        self,
        settings: Optional[HTFScanSettings] = None,
        market_data: Optional[UnifiedMarketData] = None,
    ):
        self.settings = settings or HTFScanSettings()
        self.market_data = market_data or UnifiedMarketData()
    
    def scan(
        self,
        symbols: Optional[List[str]] = None,
        verbose: bool = False,
    ) -> HTFScanResult:
        """
        Scan for HTF candidates.
        
        Args:
            symbols: List of symbols to scan. If None, uses trend leaders.
            verbose: Print verbose output
            
        Returns:
            HTFScanResult with candidates
        """
        if symbols is None:
            # Get symbols from trend leaders (high RS stocks likely to have big moves)
            symbols = self.market_data.get_trend_leaders(limit=100)
            if verbose:
                print(f"[HTF] Scanning {len(symbols)} trend leaders")
        
        candidates = []
        processed = 0
        total = len(symbols)
        progress_thresholds = {25, 50, 75}
        logged_thresholds = set()
        
        for symbol in symbols:
            processed += 1
            
            # Log progress at 25%, 50%, 75%
            if total > 0:
                pct = int((processed / total) * 100)
                for threshold in progress_thresholds:
                    if pct >= threshold and threshold not in logged_thresholds:
                        print(f"🔄 [HTF Scanner] Processing {processed}/{total} ({threshold}%)...")
                        logged_thresholds.add(threshold)
            
            try:
                candidate = self._evaluate_symbol(symbol, verbose)
                if candidate:
                    candidates.append(candidate)
                    if verbose:
                        print(f"  ✓ {symbol}: +{candidate.move_pct:.0f}% move, -{candidate.pullback_pct:.1f}% pullback")
            except Exception as e:
                if verbose:
                    print(f"  ✗ {symbol}: Error - {e}")
        
        # Sort by move size (biggest poles first)
        candidates.sort(key=lambda x: x.move_pct, reverse=True)
        
        if verbose:
            print(f"[HTF] Found {len(candidates)} candidates from {processed} scanned")
        
        return HTFScanResult(
            candidates=candidates,
            processed_count=processed,
        )
    
    def _evaluate_symbol(
        self,
        symbol: str,
        verbose: bool = False,
    ) -> Optional[HTFCandidate]:
        """Evaluate a symbol for HTF pattern."""
        
        # Check blacklist
        if symbol.upper() in BLACKLIST_TICKERS:
            return None
        
        # Get historical data
        try:
            history = self.market_data.get_historical_prices(
                symbol,
                days=self.settings.lookback_days + 30,  # Extra buffer
            )
        except Exception:
            return None
        
        if not history or len(history) < self.settings.lookback_days:
            return None
        
        # Use most recent lookback_days
        window = history[-self.settings.lookback_days:]
        
        # Current price and volume
        current = window[-1]
        current_close = Decimal(str(current.get("close", 0)))
        current_volume = int(current.get("volume", 0))
        
        if current_close <= 0:
            return None
        
        # Price filter
        if current_close < self.settings.min_price:
            return None
        
        # Dollar volume filter
        dollar_vol = current_close * current_volume
        if dollar_vol < self.settings.min_dollar_vol:
            return None
        
        # KK-style MA stacking check: price > SMA10 > SMA20 > SMA50
        # This ensures stock is in a proper uptrend, not just a bounce
        closes = [Decimal(str(d.get("close", 0))) for d in window]
        if len(closes) >= 50:
            sma10 = sum(closes[-10:]) / 10
            sma20 = sum(closes[-20:]) / 20
            sma50 = sum(closes[-50:]) / 50
            ma_stacked = current_close > sma10 > sma20 > sma50
            if not ma_stacked:
                return None  # Not in proper uptrend
        
        # Calculate move (pole size)
        highs = [Decimal(str(d.get("high", 0))) for d in window]
        lows = [Decimal(str(d.get("low", 0))) for d in window]
        
        highest_high = max(highs)
        lowest_low = min([l for l in lows if l > 0])  # Avoid div by zero
        
        if lowest_low <= 0:
            return None
        
        move_pct = ((highest_high - lowest_low) / lowest_low) * 100
        
        # Check minimum move
        if move_pct < self.settings.min_move_pct:
            return None
        
        # Calculate pullback (flag depth)
        if highest_high <= 0:
            return None
        
        pullback_pct = ((highest_high - current_close) / highest_high) * 100
        
        # Check max pullback
        if pullback_pct > self.settings.max_pullback_pct:
            return None
        
        # Determine status
        # Stocks very close to highs are "extended" — not ideal entries
        if pullback_pct < self.settings.extended_threshold_pct:
            status = HTFStatus.EXTENDED  # Very near highs, might be extended
        elif pullback_pct < Decimal("15"):
            status = HTFStatus.COMPLETE  # Ideal flag depth
        else:
            status = HTFStatus.FORMING  # Still pulling back
        
        # Calculate entry zone
        # Entry: break of recent consolidation high (use last 5 days)
        recent_highs = highs[-5:] if len(highs) >= 5 else highs
        entry_price = max(recent_highs)
        
        # KK methodology: stop = flag low (recent consolidation low)
        # This is the same pattern as breakout scanner (consolidation_low)
        recent_lows = lows[-5:] if len(lows) >= 5 else lows
        stop_price = min(recent_lows)  # Flag low
        
        # Get company name (if available)
        try:
            name = self.market_data.get_company_name(symbol) or symbol
        except Exception:
            name = symbol
        
        return HTFCandidate(
            symbol=symbol,
            name=name,
            price=current_close,
            move_pct=move_pct,
            pullback_pct=pullback_pct,
            highest_high=highest_high,
            lowest_low=lowest_low,
            dollar_volume=dollar_vol,
            status=status,
            entry_price=entry_price,
            stop_price=stop_price,  # None - calculated at entry
        )
    
    def get_htf_trend(self, symbol: str, sector: str = "Unknown") -> dict:
        """
        Symbol-level HTF query (compatible with legacy API).
        
        Returns:
            {
                "htf_trend": str | None,
                "htf_trend_score": float | None,
                "htf_raw": dict | None,
            }
        """
        candidate = self._evaluate_symbol(symbol)
        
        if not candidate:
            return {
                "htf_trend": None,
                "htf_trend_score": None,
                "htf_raw": None,
            }
        
        # Calculate a simple score (0-100) based on move size and tightness
        move_score = min(float(candidate.move_pct), 200) / 2  # Cap at 200% = 100 pts
        tightness_score = max(0, 25 - float(candidate.pullback_pct)) * 4  # 0-100
        htf_score = (move_score + tightness_score) / 2
        
        raw = {
            "symbol": candidate.symbol,
            "sector": sector,
            "move_pct": float(candidate.move_pct),
            "pullback_pct": float(candidate.pullback_pct),
            "close": float(candidate.price),
            "dollar_vol": float(candidate.dollar_volume),
            "highest_high": float(candidate.highest_high),
            "lowest_low": float(candidate.lowest_low),
            "status": candidate.status.value,
            "entry_price": float(candidate.entry_price) if candidate.entry_price else None,
            "stop_price": float(candidate.stop_price) if candidate.stop_price else None,
        }
        
        return {
            "htf_trend": "HTF" if candidate.status != HTFStatus.INVALID else None,
            "htf_trend_score": htf_score,
            "htf_raw": raw,
        }


# =============================================================================
# SINGLETON
# =============================================================================

_htf_scanner: Optional[HTFScannerService] = None


def get_htf_scanner_service() -> HTFScannerService:
    """Get singleton HTF scanner service."""
    global _htf_scanner
    if _htf_scanner is None:
        _htf_scanner = HTFScannerService()
    return _htf_scanner
