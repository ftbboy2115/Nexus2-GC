"""
Scanner Domain Models

Entities and value objects for the scanner bounded context.
Based on: scanner_architecture.md
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID
from nexus2.utils.time_utils import now_et, now_utc_factory


# =============================================================================
# VALUE OBJECTS
# =============================================================================

class Exchange(Enum):
    """Stock exchange enumeration."""
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    AMEX = "AMEX"
    OTC = "OTC"  # Disqualified


class WatchlistTier(Enum):
    """Watchlist tier levels."""
    UNIVERSE = "universe"  # Broad scan
    WIDE = "wide"          # Weekly curated
    FOCUS = "focus"        # Daily 1-5 names


class PatternType(Enum):
    """Detected chart pattern types."""
    HTF = "high_tight_flag"
    FLAG = "flag"
    FLAT_BASE = "flat_base"
    VCP = "volatility_contraction"
    CUP_HANDLE = "cup_and_handle"
    TRIANGLE = "triangle"
    CHANNEL = "channel"
    EP_CANDIDATE = "ep_candidate"


class QualityRating(Enum):
    """Quality rating categories."""
    HIGH = "high"      # Score 8-10
    MEDIUM = "medium"  # Score 5-7
    LOW = "low"        # Score <5


# =============================================================================
# ENTITIES
# =============================================================================

@dataclass
class Stock:
    """
    Base entity representing a tradeable stock.
    
    Contains static/slowly-changing stock information.
    """
    symbol: str
    name: str
    exchange: Exchange
    price: Decimal
    market_cap: Decimal
    float_shares: int
    avg_volume_20d: int  # KK-aligned: uses avgv20 in TC2000 scans
    dollar_volume: Decimal
    adr_percent: Decimal


@dataclass
class StockMetrics:
    """
    Calculated metrics for scanner evaluation.
    
    Contains momentum, technical, volume, and quality metrics.
    Updated on each scan.
    """
    symbol: str
    
    # Momentum
    performance_1m: Decimal
    performance_3m: Decimal
    performance_6m: Decimal
    rs_percentile: int  # 0-100
    rs_line_52w_high: bool
    
    # Technical (SMA)
    price_vs_sma10: Decimal  # % distance
    price_vs_sma20: Decimal
    price_vs_sma50: Decimal
    price_vs_sma200: Decimal
    
    # Technical (EMA) - KK uses both SMA and EMA
    price_vs_ema10: Decimal
    price_vs_ema20: Decimal
    price_vs_ema21: Decimal  # Common alternative
    
    ma_stacked: bool  # 10 > 20 > 50 > 200
    
    # Volatility
    atr: Decimal
    adr_percent: Decimal
    
    # Volume (20-day lookback is KK-aligned per avgv20>300000)
    avg_volume_20d: int  # KK also uses 14-day for EP (flexible)
    dollar_volume: Decimal
    volume_contraction: bool  # In consolidation
    
    # Proximity
    distance_to_52w_high: Decimal
    
    # Calculated
    quality_score: int  # 0-10
    updated_at: datetime = field(default_factory=now_utc_factory)


@dataclass
class ScannerResult:
    """
    Result of scanning a stock against criteria.
    
    Contains pass/fail status, quality score, and detected patterns.
    """
    stock: Stock
    metrics: StockMetrics
    passes_filter: bool
    failed_criteria: List[str]  # Which criteria failed
    quality_score: int
    tier_recommendation: WatchlistTier
    patterns_detected: List[PatternType]
    scanned_at: datetime = field(default_factory=now_utc_factory)
    
    @property
    def quality_rating(self) -> QualityRating:
        """Get quality rating from score."""
        if self.quality_score >= 8:
            return QualityRating.HIGH
        elif self.quality_score >= 5:
            return QualityRating.MEDIUM
        return QualityRating.LOW


@dataclass
class WatchlistEntry:
    """
    An entry in a watchlist.
    
    Tracks when and why a stock was added.
    """
    symbol: str
    added_at: datetime
    added_reason: str
    notes: str = ""
    priority: int = 3  # 1-5, higher = more important


@dataclass
class Watchlist:
    """
    Represents a watchlist tier.
    
    Contains a list of stocks at a specific tier level.
    """
    id: UUID
    tier: WatchlistTier
    name: str
    stocks: List[WatchlistEntry]
    created_at: datetime = field(default_factory=now_utc_factory)
    updated_at: datetime = field(default_factory=now_utc_factory)
    
    def __len__(self) -> int:
        return len(self.stocks)
    
    def add(self, symbol: str, reason: str, notes: str = "", priority: int = 3) -> WatchlistEntry:
        """Add a stock to this watchlist."""
        entry = WatchlistEntry(
            symbol=symbol,
            added_at=now_et(),
            added_reason=reason,
            notes=notes,
            priority=priority
        )
        self.stocks.append(entry)
        self.updated_at = now_et()
        return entry
    
    def remove(self, symbol: str) -> bool:
        """Remove a stock from this watchlist."""
        for i, entry in enumerate(self.stocks):
            if entry.symbol == symbol:
                self.stocks.pop(i)
                self.updated_at = now_et()
                return True
        return False
    
    def contains(self, symbol: str) -> bool:
        """Check if a stock is in this watchlist."""
        return any(e.symbol == symbol for e in self.stocks)


@dataclass
class DetectedPattern:
    """
    A detected chart pattern.
    
    Contains pattern details for setup detection.
    """
    type: PatternType
    symbol: str
    confidence: Decimal  # 0-100
    entry_zone: Decimal
    stop_zone: Decimal
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
