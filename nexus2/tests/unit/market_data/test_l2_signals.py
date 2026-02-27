"""
Unit tests for L2 Signal Detection Module.

Tests cover:
- Wall detection (bid and ask)
- Thin ask detection
- Spread quality assessment
- Book summary aggregation
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from nexus2.domain.market_data.l2_types import L2BookSnapshot, L2PriceLevel
from nexus2.domain.market_data.l2_signals import (
    WallSignal,
    ThinAskSignal,
    SpreadQuality,
    L2Summary,
    detect_bid_wall,
    detect_ask_wall,
    detect_thin_ask,
    get_spread_quality,
    get_book_summary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ts() -> datetime:
    """Consistent test timestamp."""
    return datetime(2026, 2, 27, 14, 30, 0, tzinfo=timezone.utc)


def _level(price: str, volume: int) -> L2PriceLevel:
    """Shorthand to build a price level."""
    return L2PriceLevel(price=Decimal(price), total_volume=volume)


def _empty_book() -> L2BookSnapshot:
    """Book with no bids or asks."""
    return L2BookSnapshot(symbol="TEST", timestamp=_ts(), bids=[], asks=[])


def _simple_book(
    bids: list[tuple[str, int]] | None = None,
    asks: list[tuple[str, int]] | None = None,
) -> L2BookSnapshot:
    """Build a book from (price, volume) tuples, sorted correctly."""
    bid_levels = [_level(p, v) for p, v in (bids or [])]
    ask_levels = [_level(p, v) for p, v in (asks or [])]
    # Bids: highest first
    bid_levels.sort(key=lambda l: l.price, reverse=True)
    # Asks: lowest first
    ask_levels.sort(key=lambda l: l.price)
    return L2BookSnapshot(
        symbol="TEST", timestamp=_ts(), bids=bid_levels, asks=ask_levels,
    )


# ===================================================================
# detect_bid_wall
# ===================================================================

class TestDetectBidWall:
    """Tests for detect_bid_wall."""

    def test_empty_book_returns_none(self):
        """Claim 2: empty book → None."""
        result = detect_bid_wall(_empty_book())
        assert result is None

    def test_no_level_exceeds_threshold_returns_none(self):
        book = _simple_book(bids=[("10.00", 5000), ("9.90", 3000)])
        result = detect_bid_wall(book, threshold_volume=10_000)
        assert result is None

    def test_one_level_exceeds_threshold(self):
        """Claim 3: returns WallSignal when volume ≥ threshold."""
        book = _simple_book(bids=[("10.00", 15000), ("9.90", 3000)])
        result = detect_bid_wall(book, threshold_volume=10_000)
        assert result is not None
        assert isinstance(result, WallSignal)
        assert result.price == Decimal("10.00")
        assert result.volume == 15000
        assert result.side == "bid"

    def test_returns_largest_wall(self):
        """When multiple levels exceed threshold, return the largest."""
        book = _simple_book(
            bids=[("10.00", 15000), ("9.90", 20000), ("9.80", 12000)]
        )
        result = detect_bid_wall(book, threshold_volume=10_000)
        assert result is not None
        assert result.price == Decimal("9.90")
        assert result.volume == 20000

    def test_exact_threshold_match(self):
        """Volume exactly at threshold should be included (≥)."""
        book = _simple_book(bids=[("10.00", 10000)])
        result = detect_bid_wall(book, threshold_volume=10_000)
        assert result is not None
        assert result.volume == 10000

    def test_side_is_bid(self):
        book = _simple_book(bids=[("10.00", 15000)])
        result = detect_bid_wall(book, threshold_volume=10_000)
        assert result.side == "bid"


# ===================================================================
# detect_ask_wall
# ===================================================================

class TestDetectAskWall:
    """Tests for detect_ask_wall — Claim 4: symmetric to bid wall."""

    def test_empty_book_returns_none(self):
        result = detect_ask_wall(_empty_book())
        assert result is None

    def test_no_level_exceeds_threshold_returns_none(self):
        book = _simple_book(asks=[("10.10", 5000), ("10.20", 3000)])
        result = detect_ask_wall(book, threshold_volume=10_000)
        assert result is None

    def test_one_level_exceeds_threshold(self):
        book = _simple_book(asks=[("10.10", 18000), ("10.20", 3000)])
        result = detect_ask_wall(book, threshold_volume=10_000)
        assert result is not None
        assert isinstance(result, WallSignal)
        assert result.price == Decimal("10.10")
        assert result.volume == 18000
        assert result.side == "ask"

    def test_returns_largest_wall(self):
        book = _simple_book(
            asks=[("10.10", 12000), ("10.20", 25000), ("10.30", 11000)]
        )
        result = detect_ask_wall(book, threshold_volume=10_000)
        assert result is not None
        assert result.price == Decimal("10.20")
        assert result.volume == 25000

    def test_side_is_ask(self):
        book = _simple_book(asks=[("10.10", 15000)])
        result = detect_ask_wall(book, threshold_volume=10_000)
        assert result.side == "ask"


# ===================================================================
# detect_thin_ask
# ===================================================================

class TestDetectThinAsk:
    """Tests for detect_thin_ask — Claim 5."""

    def test_empty_book_returns_none(self):
        result = detect_thin_ask(_empty_book())
        assert result is None

    def test_many_ask_levels_returns_none(self):
        """Enough levels and sufficient volume → not thin → None."""
        # 5 ask levels within 0.5% of best ask ($10.10)
        # upper bound = 10.10 * 1.005 = 10.1505
        # All 5 levels are within range, >= min_levels=3
        # Total ask vol = 50000 > total bid vol = 1000, so not thin on volume either
        book = _simple_book(
            bids=[("10.00", 1000)],
            asks=[
                ("10.10", 10000),
                ("10.11", 10000),
                ("10.12", 10000),
                ("10.13", 10000),
                ("10.14", 10000),
            ],
        )
        result = detect_thin_ask(book, min_levels=3)
        assert result is None

    def test_few_ask_levels_returns_thin(self):
        """Claim 5: fewer than min_levels → ThinAskSignal."""
        book = _simple_book(
            bids=[("10.00", 1000)],
            asks=[("10.10", 500), ("10.11", 500)],
        )
        result = detect_thin_ask(book, min_levels=3)
        assert result is not None
        assert isinstance(result, ThinAskSignal)
        assert result.levels_count == 2

    def test_low_ask_volume_vs_bid_volume(self):
        """Total ask vol < total bid vol → thin (buyers dominate)."""
        book = _simple_book(
            bids=[("10.00", 50000)],
            asks=[
                ("10.10", 1000),
                ("10.11", 1000),
                ("10.12", 1000),
            ],
        )
        # 3 levels in range (meets min_levels=3), but ask vol 3000 < bid vol 50000
        result = detect_thin_ask(book, min_levels=3)
        assert result is not None
        assert result.total_volume == 3000

    def test_no_asks_returns_none(self):
        """Only bids, no asks → None (no thin-ask signal possible)."""
        book = _simple_book(bids=[("10.00", 5000)])
        result = detect_thin_ask(book)
        assert result is None


# ===================================================================
# get_spread_quality
# ===================================================================

class TestGetSpreadQuality:
    """Tests for get_spread_quality — Claims 6 & 7."""

    def test_empty_book_returns_wide(self):
        """Claim 6: empty book → quality='wide', spread=0."""
        result = get_spread_quality(_empty_book())
        assert isinstance(result, SpreadQuality)
        assert result.quality == "wide"
        assert result.spread == Decimal("0")
        assert result.spread_bps == 0.0

    def test_tight_spread(self):
        """Claim 7: ≤10 bps → 'tight'."""
        # Spread = 10.01 - 10.00 = 0.01
        # Midpoint = 10.005
        # BPS = (0.01 / 10.005) * 10000 ≈ 9.995 → tight (≤ 10)
        book = _simple_book(
            bids=[("10.00", 1000)],
            asks=[("10.01", 1000)],
        )
        result = get_spread_quality(book, tight_bps=10.0, wide_bps=50.0)
        assert result.quality == "tight"
        assert result.spread == Decimal("0.01")
        assert result.spread_bps == pytest.approx(9.995, abs=0.1)

    def test_normal_spread(self):
        """Claim 7: 10-50 bps → 'normal'."""
        # Spread = 10.03 - 10.00 = 0.03
        # Midpoint = 10.015
        # BPS = (0.03 / 10.015) * 10000 ≈ 29.955 → normal
        book = _simple_book(
            bids=[("10.00", 1000)],
            asks=[("10.03", 1000)],
        )
        result = get_spread_quality(book, tight_bps=10.0, wide_bps=50.0)
        assert result.quality == "normal"

    def test_wide_spread(self):
        """Claim 7: >50 bps → 'wide'."""
        # Spread = 10.10 - 10.00 = 0.10
        # Midpoint = 10.05
        # BPS = (0.10 / 10.05) * 10000 ≈ 99.5 → wide
        book = _simple_book(
            bids=[("10.00", 1000)],
            asks=[("10.10", 1000)],
        )
        result = get_spread_quality(book, tight_bps=10.0, wide_bps=50.0)
        assert result.quality == "wide"

    def test_imbalance_more_bids(self):
        """More bid volume → positive imbalance."""
        book = _simple_book(
            bids=[("10.00", 8000)],
            asks=[("10.01", 2000)],
        )
        result = get_spread_quality(book)
        # imbalance = (8000 - 2000) / 10000 = 0.6
        assert result.imbalance == pytest.approx(0.6)

    def test_imbalance_more_asks(self):
        """More ask volume → negative imbalance."""
        book = _simple_book(
            bids=[("10.00", 2000)],
            asks=[("10.01", 8000)],
        )
        result = get_spread_quality(book)
        # imbalance = (2000 - 8000) / 10000 = -0.6
        assert result.imbalance == pytest.approx(-0.6)

    def test_imbalance_equal(self):
        """Equal bid/ask volume → imbalance ≈ 0."""
        book = _simple_book(
            bids=[("10.00", 5000)],
            asks=[("10.01", 5000)],
        )
        result = get_spread_quality(book)
        assert result.imbalance == pytest.approx(0.0)

    def test_bid_depth_and_ask_depth(self):
        """Depths reflect total volume across all levels."""
        book = _simple_book(
            bids=[("10.00", 3000), ("9.99", 2000)],
            asks=[("10.01", 1500), ("10.02", 500)],
        )
        result = get_spread_quality(book)
        assert result.bid_depth == 5000
        assert result.ask_depth == 2000

    def test_one_sided_book_bids_only(self):
        """Only bids, no asks → quality='wide'."""
        book = _simple_book(bids=[("10.00", 5000)])
        result = get_spread_quality(book)
        assert result.quality == "wide"
        assert result.spread == Decimal("0")


# ===================================================================
# get_book_summary
# ===================================================================

class TestGetBookSummary:
    """Tests for get_book_summary — Claim 8."""

    def test_empty_book_summary(self):
        """Empty book: all signals None/defaults."""
        book = _empty_book()
        result = get_book_summary(book)
        assert isinstance(result, L2Summary)
        assert result.symbol == "TEST"
        assert result.best_bid is None
        assert result.best_ask is None
        assert result.spread is None
        assert result.bid_wall is None
        assert result.ask_wall is None
        assert result.thin_ask is None
        assert result.spread_quality.quality == "wide"

    def test_full_book_aggregation(self):
        """Claim 8: summary aggregates all signal outputs."""
        book = _simple_book(
            bids=[("10.00", 20000), ("9.90", 5000)],
            asks=[("10.01", 15000), ("10.05", 3000)],
        )
        result = get_book_summary(book, wall_threshold=10_000)
        assert isinstance(result, L2Summary)
        assert result.symbol == "TEST"
        assert result.best_bid == Decimal("10.00")
        assert result.best_ask == Decimal("10.01")
        assert result.spread == Decimal("0.01")
        # Bid wall: 20000 at 10.00
        assert result.bid_wall is not None
        assert result.bid_wall.volume == 20000
        assert result.bid_wall.side == "bid"
        # Ask wall: 15000 at 10.01
        assert result.ask_wall is not None
        assert result.ask_wall.volume == 15000
        assert result.ask_wall.side == "ask"
        # Spread quality should exist
        assert result.spread_quality is not None
        assert result.spread_quality.quality in ("tight", "normal", "wide")

    def test_summary_passes_thresholds(self):
        """Verify that threshold parameters are forwarded correctly."""
        book = _simple_book(
            bids=[("10.00", 8000)],
            asks=[("10.01", 8000)],
        )
        # With wall_threshold=10000, no walls should be detected
        result = get_book_summary(book, wall_threshold=10_000)
        assert result.bid_wall is None
        assert result.ask_wall is None

        # With wall_threshold=5000, walls should appear
        result = get_book_summary(book, wall_threshold=5_000)
        assert result.bid_wall is not None
        assert result.ask_wall is not None

    def test_summary_timestamp_matches(self):
        """Summary timestamp matches the book timestamp."""
        book = _empty_book()
        result = get_book_summary(book)
        assert result.timestamp == book.timestamp
