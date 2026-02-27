"""
Unit tests for L2 (Level 2) order book data types and parser.

Tests:
- Parsing a mock schwab-py book message into L2BookSnapshot
- Bid sorting (highest-price-first)
- Ask sorting (lowest-price-first)
- Computed properties: best_bid, best_ask, spread, bid_ask_ratio
- Empty book edge cases
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from nexus2.domain.market_data.l2_types import (
    L2BookSide,
    L2BookSnapshot,
    L2ExchangeEntry,
    L2PriceLevel,
    parse_schwab_book_message,
)


# ---------------------------------------------------------------------------
# Fixtures: mock schwab-py relabeled book messages
# ---------------------------------------------------------------------------

def _make_schwab_book_msg(
    symbol: str = "AAPL",
    book_time_ms: int = 1709000000000,
    bids: list | None = None,
    asks: list | None = None,
) -> dict:
    """Build a mock schwab-py book message in relabeled format."""
    if bids is None:
        bids = [
            {
                "BID_PRICE": 150.10,
                "TOTAL_VOLUME": 500,
                "NUM_BIDS": 2,
                "BIDS": [
                    {"EXCHANGE": "NSDQ", "BID_VOLUME": 300, "SEQUENCE": 1},
                    {"EXCHANGE": "ARCA", "BID_VOLUME": 200, "SEQUENCE": 2},
                ],
            },
            {
                "BID_PRICE": 150.05,
                "TOTAL_VOLUME": 1200,
                "NUM_BIDS": 1,
                "BIDS": [
                    {"EXCHANGE": "NSDQ", "BID_VOLUME": 1200, "SEQUENCE": 3},
                ],
            },
            {
                "BID_PRICE": 150.20,
                "TOTAL_VOLUME": 800,
                "NUM_BIDS": 1,
                "BIDS": [
                    {"EXCHANGE": "NYSE", "BID_VOLUME": 800, "SEQUENCE": 4},
                ],
            },
        ]
    if asks is None:
        asks = [
            {
                "ASK_PRICE": 150.30,
                "TOTAL_VOLUME": 600,
                "NUM_ASKS": 1,
                "ASKS": [
                    {"EXCHANGE": "NSDQ", "ASK_VOLUME": 600, "SEQUENCE": 5},
                ],
            },
            {
                "ASK_PRICE": 150.25,
                "TOTAL_VOLUME": 400,
                "NUM_ASKS": 2,
                "ASKS": [
                    {"EXCHANGE": "ARCA", "ASK_VOLUME": 250, "SEQUENCE": 6},
                    {"EXCHANGE": "NYSE", "ASK_VOLUME": 150, "SEQUENCE": 7},
                ],
            },
            {
                "ASK_PRICE": 150.50,
                "TOTAL_VOLUME": 2000,
                "NUM_ASKS": 1,
                "ASKS": [
                    {"EXCHANGE": "NSDQ", "ASK_VOLUME": 2000, "SEQUENCE": 8},
                ],
            },
        ]
    return {
        "content": [
            {
                "key": symbol,
                "BOOK_TIME": book_time_ms,
                "BIDS": bids,
                "ASKS": asks,
            }
        ]
    }


# ---------------------------------------------------------------------------
# Tests: parse_schwab_book_message
# ---------------------------------------------------------------------------

class TestParseSchwabBookMessage:
    """Tests for the top-level parser function."""

    def test_parses_valid_message(self):
        msg = _make_schwab_book_msg()
        result = parse_schwab_book_message(msg)
        assert result is not None
        assert isinstance(result, L2BookSnapshot)
        assert result.symbol == "AAPL"

    def test_timestamp_parsed_from_book_time(self):
        msg = _make_schwab_book_msg(book_time_ms=1709000000000)
        result = parse_schwab_book_message(msg)
        expected_ts = datetime.fromtimestamp(1709000000, tz=timezone.utc)
        assert result.timestamp == expected_ts

    def test_returns_none_for_empty_content(self):
        result = parse_schwab_book_message({"content": []})
        assert result is None

    def test_returns_none_for_missing_key(self):
        msg = {"content": [{"BOOK_TIME": 123, "BIDS": [], "ASKS": []}]}
        result = parse_schwab_book_message(msg)
        assert result is None

    def test_handles_raw_dict_without_content_wrapper(self):
        raw = {
            "key": "TSLA",
            "BOOK_TIME": 1709000000000,
            "BIDS": [],
            "ASKS": [],
        }
        result = parse_schwab_book_message(raw)
        assert result is not None
        assert result.symbol == "TSLA"

    def test_handles_malformed_message_gracefully(self):
        result = parse_schwab_book_message({"garbage": True})
        # Should not raise, returns None or empty
        # The parser wraps in try/except


# ---------------------------------------------------------------------------
# Tests: bid sorting
# ---------------------------------------------------------------------------

class TestBidSorting:
    """Bids should be sorted highest-price-first (best bid at index 0)."""

    def test_bids_sorted_highest_first(self):
        msg = _make_schwab_book_msg()
        result = parse_schwab_book_message(msg)
        prices = [level.price for level in result.bids]
        # Should be: 150.20, 150.10, 150.05
        assert prices == sorted(prices, reverse=True)
        assert prices[0] == Decimal("150.20")
        assert prices[-1] == Decimal("150.05")


# ---------------------------------------------------------------------------
# Tests: ask sorting
# ---------------------------------------------------------------------------

class TestAskSorting:
    """Asks should be sorted lowest-price-first (best ask at index 0)."""

    def test_asks_sorted_lowest_first(self):
        msg = _make_schwab_book_msg()
        result = parse_schwab_book_message(msg)
        prices = [level.price for level in result.asks]
        # Should be: 150.25, 150.30, 150.50
        assert prices == sorted(prices)
        assert prices[0] == Decimal("150.25")
        assert prices[-1] == Decimal("150.50")


# ---------------------------------------------------------------------------
# Tests: computed properties on L2BookSnapshot
# ---------------------------------------------------------------------------

class TestL2BookSnapshotProperties:
    """Test best_bid, best_ask, spread, bid_ask_ratio, depth_levels."""

    def test_best_bid(self):
        msg = _make_schwab_book_msg()
        snap = parse_schwab_book_message(msg)
        assert snap.best_bid == Decimal("150.20")

    def test_best_ask(self):
        msg = _make_schwab_book_msg()
        snap = parse_schwab_book_message(msg)
        assert snap.best_ask == Decimal("150.25")

    def test_spread(self):
        msg = _make_schwab_book_msg()
        snap = parse_schwab_book_message(msg)
        assert snap.spread == Decimal("0.05")

    def test_total_bid_volume(self):
        msg = _make_schwab_book_msg()
        snap = parse_schwab_book_message(msg)
        # 500 + 1200 + 800 = 2500
        assert snap.total_bid_volume == 2500

    def test_total_ask_volume(self):
        msg = _make_schwab_book_msg()
        snap = parse_schwab_book_message(msg)
        # 600 + 400 + 2000 = 3000
        assert snap.total_ask_volume == 3000

    def test_bid_ask_ratio(self):
        msg = _make_schwab_book_msg()
        snap = parse_schwab_book_message(msg)
        # 2500 / 3000 ≈ 0.8333
        ratio = snap.bid_ask_ratio
        assert ratio is not None
        assert abs(ratio - (2500 / 3000)) < 0.001

    def test_depth_levels(self):
        msg = _make_schwab_book_msg()
        snap = parse_schwab_book_message(msg)
        assert snap.depth_levels == 3

    def test_summary_returns_string(self):
        msg = _make_schwab_book_msg()
        snap = parse_schwab_book_message(msg)
        s = snap.summary()
        assert isinstance(s, str)
        assert "AAPL" in s


# ---------------------------------------------------------------------------
# Tests: empty book edge cases
# ---------------------------------------------------------------------------

class TestEmptyBook:
    """When bids or asks are empty, optional properties return None."""

    def test_empty_bids_best_bid_is_none(self):
        snap = L2BookSnapshot(
            symbol="TEST", timestamp=datetime.now(timezone.utc), bids=[], asks=[]
        )
        assert snap.best_bid is None

    def test_empty_asks_best_ask_is_none(self):
        snap = L2BookSnapshot(
            symbol="TEST", timestamp=datetime.now(timezone.utc), bids=[], asks=[]
        )
        assert snap.best_ask is None

    def test_spread_is_none_when_empty(self):
        snap = L2BookSnapshot(
            symbol="TEST", timestamp=datetime.now(timezone.utc), bids=[], asks=[]
        )
        assert snap.spread is None

    def test_bid_ask_ratio_none_when_no_asks(self):
        snap = L2BookSnapshot(
            symbol="TEST",
            timestamp=datetime.now(timezone.utc),
            bids=[L2PriceLevel(price=Decimal("10.00"), total_volume=100)],
            asks=[],
        )
        assert snap.bid_ask_ratio is None

    def test_depth_levels_zero_when_empty(self):
        snap = L2BookSnapshot(
            symbol="TEST", timestamp=datetime.now(timezone.utc), bids=[], asks=[]
        )
        assert snap.depth_levels == 0


# ---------------------------------------------------------------------------
# Tests: L2PriceLevel.is_wall
# ---------------------------------------------------------------------------

class TestL2PriceLevelIsWall:
    """Test the wall detection heuristic."""

    def test_is_wall_true_at_10k(self):
        level = L2PriceLevel(price=Decimal("5.00"), total_volume=10_000)
        assert level.is_wall is True

    def test_is_wall_false_below_threshold(self):
        level = L2PriceLevel(price=Decimal("5.00"), total_volume=9_999)
        assert level.is_wall is False


# ---------------------------------------------------------------------------
# Tests: exchange entry parsing
# ---------------------------------------------------------------------------

class TestExchangeEntryParsing:
    """Verify per-exchange data is parsed from the message."""

    def test_exchange_entries_populated(self):
        msg = _make_schwab_book_msg()
        snap = parse_schwab_book_message(msg)
        # The highest bid (150.20) has 1 exchange entry
        best_bid_level = snap.bids[0]
        assert len(best_bid_level.exchanges) == 1
        assert best_bid_level.exchanges[0].exchange_id == "NYSE"
        assert best_bid_level.exchanges[0].volume == 800

    def test_multiple_exchange_entries(self):
        msg = _make_schwab_book_msg()
        snap = parse_schwab_book_message(msg)
        # The bid at 150.10 has 2 exchange entries
        second_bid = snap.bids[1]  # 150.10 after sorting
        assert len(second_bid.exchanges) == 2


# ---------------------------------------------------------------------------
# Tests: numeric key fallback (pre-relabeling format)
# ---------------------------------------------------------------------------

class TestNumericKeyFallback:
    """Parser should handle numeric keys within bid/ask level dicts."""

    def test_parses_numeric_price_volume_keys(self):
        """Within a bid level, parser falls back to '0' for price, '1' for volume."""
        msg = {
            "content": [
                {
                    "key": "XYZ",
                    "BOOK_TIME": 1709000000000,
                    "BIDS": [
                        {"0": 10.50, "1": 200, "2": 1, "3": []},
                    ],
                    "ASKS": [
                        {"0": 10.60, "1": 150, "2": 1, "3": []},
                    ],
                }
            ]
        }
        result = parse_schwab_book_message(msg)
        assert result is not None
        assert result.symbol == "XYZ"
        assert result.best_bid == Decimal("10.5")
        assert result.best_ask == Decimal("10.6")
