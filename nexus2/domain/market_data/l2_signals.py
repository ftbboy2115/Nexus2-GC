"""
L2 Signal Detection Module

Pure functions that analyze L2BookSnapshot data to identify trading-relevant
order book patterns: walls, thin asks, spread quality, and book summaries.

All functions are stateless with no side effects — thresholds are parameters
with sensible defaults for tuning after observing real market data.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from nexus2.domain.market_data.l2_types import L2BookSnapshot


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class WallSignal:
    """A single large-volume level indicating support (bid) or resistance (ask)."""
    price: Decimal
    volume: int
    side: str  # "bid" or "ask"


@dataclass
class ThinAskSignal:
    """Indicates thin resistance above current price — stock can move up easily."""
    levels_count: int
    total_volume: int
    price_range: Decimal


@dataclass
class SpreadQuality:
    """Overall order book quality assessment."""
    spread: Decimal
    spread_bps: float
    bid_depth: int
    ask_depth: int
    imbalance: float
    quality: str  # "tight", "normal", "wide"


@dataclass
class L2Summary:
    """One-call summary combining all signal outputs for logging/dashboard."""
    symbol: str
    timestamp: datetime
    best_bid: Optional[Decimal]
    best_ask: Optional[Decimal]
    spread: Optional[Decimal]
    bid_wall: Optional[WallSignal]
    ask_wall: Optional[WallSignal]
    thin_ask: Optional[ThinAskSignal]
    spread_quality: SpreadQuality


# ---------------------------------------------------------------------------
# Signal Functions
# ---------------------------------------------------------------------------

def detect_bid_wall(
    book: L2BookSnapshot,
    threshold_volume: int = 10_000,
) -> Optional[WallSignal]:
    """
    Detect a bid wall — a single bid level with unusually large volume,
    suggesting strong support below the current price.

    Returns the *largest* wall found, or None if no level meets the threshold.
    """
    if not book.bids:
        return None

    largest: Optional[WallSignal] = None
    for level in book.bids:
        if level.total_volume >= threshold_volume:
            if largest is None or level.total_volume > largest.volume:
                largest = WallSignal(
                    price=level.price,
                    volume=level.total_volume,
                    side="bid",
                )
    return largest


def detect_ask_wall(
    book: L2BookSnapshot,
    threshold_volume: int = 10_000,
) -> Optional[WallSignal]:
    """
    Detect an ask wall — a single ask level with unusually large volume,
    suggesting strong resistance above the current price.

    Returns the *largest* wall found, or None if no level meets the threshold.
    """
    if not book.asks:
        return None

    largest: Optional[WallSignal] = None
    for level in book.asks:
        if level.total_volume >= threshold_volume:
            if largest is None or level.total_volume > largest.volume:
                largest = WallSignal(
                    price=level.price,
                    volume=level.total_volume,
                    side="ask",
                )
    return largest


def detect_thin_ask(
    book: L2BookSnapshot,
    price_range_pct: float = 0.5,
    min_levels: int = 3,
) -> Optional[ThinAskSignal]:
    """
    Detect a thin ask — very little resistance above the current price,
    meaning the stock can move up easily.

    Looks at ask levels within ``price_range_pct`` percent of best ask.
    Returns a ThinAskSignal when:
      - fewer than ``min_levels`` ask levels exist in that range, OR
      - total ask volume in range is less than total bid volume (buyers dominate)

    Returns None when resistance is sufficient (not thin).
    """
    if not book.asks:
        return None

    best_ask = book.best_ask
    if best_ask is None or best_ask <= 0:
        return None

    # Upper bound of the price window
    upper_bound = best_ask * (1 + Decimal(str(price_range_pct)) / 100)

    # Collect ask levels within the window
    levels_in_range = [
        level for level in book.asks
        if level.price <= upper_bound
    ]

    levels_count = len(levels_in_range)
    total_ask_vol = sum(level.total_volume for level in levels_in_range)
    price_range = upper_bound - best_ask

    # Thin if fewer than min_levels OR ask volume beaten by bid volume
    is_thin = (
        levels_count < min_levels
        or total_ask_vol < book.total_bid_volume
    )

    if is_thin:
        return ThinAskSignal(
            levels_count=levels_count,
            total_volume=total_ask_vol,
            price_range=price_range,
        )
    return None


def get_spread_quality(
    book: L2BookSnapshot,
    tight_bps: float = 10.0,
    wide_bps: float = 50.0,
) -> SpreadQuality:
    """
    Assess overall order book quality for trading.

    Spread quality tiers (basis-point thresholds are tunable):
      - "tight"  : spread_bps <= tight_bps   (very liquid, easy to trade)
      - "normal" : tight_bps < spread_bps <= wide_bps
      - "wide"   : spread_bps > wide_bps     (costly to cross)

    For empty books, returns zeroed metrics with quality "wide".
    """
    bid_depth = book.total_bid_volume
    ask_depth = book.total_ask_volume
    total_depth = bid_depth + ask_depth

    # Handle empty / one-sided books
    best_bid = book.best_bid
    best_ask = book.best_ask

    if best_bid is None or best_ask is None or best_bid <= 0:
        return SpreadQuality(
            spread=Decimal("0"),
            spread_bps=0.0,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            imbalance=0.0,
            quality="wide",
        )

    spread = best_ask - best_bid
    midpoint = (best_ask + best_bid) / 2

    # Spread in basis points (1 bp = 0.01%)
    if midpoint > 0:
        spread_bps = float(spread / midpoint) * 10_000
    else:
        spread_bps = 0.0

    # Imbalance: positive = more buyers, negative = more sellers
    if total_depth > 0:
        imbalance = (bid_depth - ask_depth) / total_depth
    else:
        imbalance = 0.0

    # Quality classification
    if spread_bps <= tight_bps:
        quality = "tight"
    elif spread_bps <= wide_bps:
        quality = "normal"
    else:
        quality = "wide"

    return SpreadQuality(
        spread=spread,
        spread_bps=spread_bps,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        imbalance=imbalance,
        quality=quality,
    )


def get_book_summary(
    book: L2BookSnapshot,
    wall_threshold: int = 10_000,
    thin_ask_range_pct: float = 0.5,
    thin_ask_min_levels: int = 3,
    tight_bps: float = 10.0,
    wide_bps: float = 50.0,
) -> L2Summary:
    """
    One-call summary combining all signal detections.

    Useful for logging, dashboard display, and downstream decision modules.
    All threshold parameters are forwarded to the individual signal functions.
    """
    return L2Summary(
        symbol=book.symbol,
        timestamp=book.timestamp,
        best_bid=book.best_bid,
        best_ask=book.best_ask,
        spread=book.spread,
        bid_wall=detect_bid_wall(book, threshold_volume=wall_threshold),
        ask_wall=detect_ask_wall(book, threshold_volume=wall_threshold),
        thin_ask=detect_thin_ask(
            book,
            price_range_pct=thin_ask_range_pct,
            min_levels=thin_ask_min_levels,
        ),
        spread_quality=get_spread_quality(
            book,
            tight_bps=tight_bps,
            wide_bps=wide_bps,
        ),
    )
