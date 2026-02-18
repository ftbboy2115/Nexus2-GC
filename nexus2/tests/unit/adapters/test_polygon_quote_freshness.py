"""
Tests for Quote Data Quality Phase 1

Covers:
- _parse_polygon_timestamp: nanosecond parsing, None/zero/invalid fallbacks
- get_quote: timestamp propagation, quote_age_seconds, price_source fields
- Midpoint fallback: stale lastTrade triggers bid/ask midpoint during market hours
- get_quotes_batch: same timestamp + midpoint logic for batch calls
- Quote dataclass backward compatibility (new optional fields)
- Single-source warning in UnifiedMarketData.get_quote
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from nexus2.adapters.market_data.polygon_adapter import (
    PolygonAdapter,
    PolygonConfig,
    STALE_TRADE_THRESHOLD_SECONDS,
)
from nexus2.adapters.market_data.protocol import Quote


# =============================================================================
# Helpers
# =============================================================================

def _make_snapshot_response(
    symbol: str = "TEST",
    last_trade_price: float = 10.0,
    last_trade_timestamp_ns: int = None,
    bid: float = 0,
    ask: float = 0,
    day_volume: int = 100_000,
    prev_close: float = 9.0,
    day_close: float = 0,
) -> dict:
    """Build a Polygon snapshot API response dict for a single ticker."""
    return {
        "status": "OK",
        "ticker": {
            "day": {"c": day_close, "v": day_volume},
            "lastTrade": {"p": last_trade_price, "t": last_trade_timestamp_ns},
            "lastQuote": {"p": bid, "P": ask},
            "prevDay": {"c": prev_close},
        },
    }


def _make_batch_snapshot_response(tickers: list[dict]) -> dict:
    """Build a Polygon batch snapshot API response dict."""
    ticker_list = []
    for t in tickers:
        ticker_list.append({
            "ticker": t.get("symbol", "TEST"),
            "day": {"c": t.get("day_close", 0), "v": t.get("day_volume", 100_000)},
            "lastTrade": {"p": t.get("last_trade_price", 10.0), "t": t.get("ts_ns")},
            "lastQuote": {"p": t.get("bid", 0), "P": t.get("ask", 0)},
            "prevDay": {"c": t.get("prev_close", 9.0)},
        })
    return {"status": "OK", "tickers": ticker_list}


def _ns_from_utc(dt: datetime) -> int:
    """Convert a UTC datetime to Polygon-style nanosecond timestamp."""
    return int(dt.timestamp() * 1_000_000_000)


def _make_adapter() -> PolygonAdapter:
    """Create a PolygonAdapter with a dummy API key (all calls will be mocked)."""
    cfg = PolygonConfig(api_key="test_key_fake")
    return PolygonAdapter(config=cfg)


# =============================================================================
# Test Group 1: _parse_polygon_timestamp
# =============================================================================

class TestParsePolygonTimestamp:
    """Tests for PolygonAdapter._parse_polygon_timestamp static method."""

    def test_valid_nanosecond_timestamp(self):
        """A valid nanosecond timestamp should parse to the correct UTC datetime."""
        # 2024-01-15 10:30:00 UTC
        expected = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        ns = _ns_from_utc(expected)
        result = PolygonAdapter._parse_polygon_timestamp(ns)
        # Allow 1-second tolerance for floating-point conversion
        assert abs((result - expected).total_seconds()) < 1

    def test_none_input_returns_now(self):
        """None input should return datetime.now(UTC) as fallback."""
        before = datetime.now(timezone.utc)
        result = PolygonAdapter._parse_polygon_timestamp(None)
        after = datetime.now(timezone.utc)
        assert before <= result <= after

    def test_zero_input_returns_now(self):
        """Zero input should return datetime.now(UTC) as fallback (falsy)."""
        before = datetime.now(timezone.utc)
        result = PolygonAdapter._parse_polygon_timestamp(0)
        after = datetime.now(timezone.utc)
        assert before <= result <= after

    def test_invalid_string_returns_now(self):
        """Non-numeric string should return datetime.now(UTC) as fallback."""
        before = datetime.now(timezone.utc)
        result = PolygonAdapter._parse_polygon_timestamp("not_a_number")
        after = datetime.now(timezone.utc)
        assert before <= result <= after

    def test_result_is_utc_aware(self):
        """Result should always be UTC-aware."""
        result = PolygonAdapter._parse_polygon_timestamp(None)
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc


# =============================================================================
# Test Group 2: get_quote() Timestamp Propagation
# =============================================================================

class TestGetQuoteTimestampPropagation:
    """Tests for timestamp + quote_age_seconds + price_source in get_quote."""

    def test_fresh_trade_returns_lastTrade_source(self):
        """A recent lastTrade should produce price_source='lastTrade' and low quote_age."""
        adapter = _make_adapter()
        recent_ts = datetime.now(timezone.utc) - timedelta(seconds=2)
        ns = _ns_from_utc(recent_ts)

        snapshot = _make_snapshot_response(
            symbol="AAPL",
            last_trade_price=150.0,
            last_trade_timestamp_ns=ns,
            bid=149.90,
            ask=150.10,
        )

        with patch.object(adapter, "_get", return_value=snapshot):
            with patch("nexus2.utils.time_utils.is_market_hours", return_value=True):
                quote = adapter.get_quote("AAPL")

        assert quote is not None
        assert quote.price_source == "lastTrade"
        assert quote.quote_age_seconds is not None
        assert quote.quote_age_seconds < 10  # Should be ~2s
        assert float(quote.price) == pytest.approx(150.0, abs=0.01)

    def test_stale_trade_outside_market_hours_no_fallback(self):
        """Stale lastTrade outside market hours should NOT trigger midpoint fallback."""
        adapter = _make_adapter()
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=300)
        ns = _ns_from_utc(old_ts)

        snapshot = _make_snapshot_response(
            symbol="ILLIQ",
            last_trade_price=5.0,
            last_trade_timestamp_ns=ns,
            bid=4.90,
            ask=5.10,
        )

        with patch.object(adapter, "_get", return_value=snapshot):
            with patch("nexus2.utils.time_utils.is_market_hours", return_value=False):
                quote = adapter.get_quote("ILLIQ")

        assert quote is not None
        assert quote.price_source == "lastTrade"
        assert float(quote.price) == pytest.approx(5.0, abs=0.01)

    def test_quote_age_seconds_populated(self):
        """quote_age_seconds should reflect the age of the lastTrade timestamp."""
        adapter = _make_adapter()
        age = 60  # 60 seconds old
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=age)
        ns = _ns_from_utc(old_ts)

        snapshot = _make_snapshot_response(
            symbol="TEST",
            last_trade_price=10.0,
            last_trade_timestamp_ns=ns,
        )

        with patch.object(adapter, "_get", return_value=snapshot):
            with patch("nexus2.utils.time_utils.is_market_hours", return_value=False):
                quote = adapter.get_quote("TEST")

        assert quote is not None
        assert quote.quote_age_seconds is not None
        # Allow 5s tolerance for test execution time
        assert abs(quote.quote_age_seconds - age) < 5


# =============================================================================
# Test Group 3: Midpoint Fallback Logic
# =============================================================================

class TestMidpointFallback:
    """Tests for bid/ask midpoint fallback when lastTrade is stale."""

    def test_triggers_fallback_when_stale_during_market_hours(self):
        """Stale trade + market hours + tight spread → use midpoint."""
        adapter = _make_adapter()
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=300)
        ns = _ns_from_utc(old_ts)

        # Price is $1.78, but bid/ask is $2.10/$2.20 (midpoint $2.15)
        # Spread = (2.20 - 2.10) / 2.10 * 100 = 4.76% < 5%
        # Divergence = |2.15 - 1.78| / 1.78 = 0.208 > 0.01
        snapshot = _make_snapshot_response(
            symbol="LRHC",
            last_trade_price=1.78,
            last_trade_timestamp_ns=ns,
            bid=2.10,
            ask=2.20,
        )

        with patch.object(adapter, "_get", return_value=snapshot):
            with patch("nexus2.utils.time_utils.is_market_hours", return_value=True):
                quote = adapter.get_quote("LRHC")

        assert quote is not None
        assert quote.price_source == "midpoint"
        expected_midpoint = (2.10 + 2.20) / 2  # $2.15
        assert float(quote.price) == pytest.approx(expected_midpoint, abs=0.01)

    def test_no_fallback_outside_market_hours(self):
        """Stale trade outside market hours should keep lastTrade price."""
        adapter = _make_adapter()
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=300)
        ns = _ns_from_utc(old_ts)

        snapshot = _make_snapshot_response(
            symbol="LRHC",
            last_trade_price=1.78,
            last_trade_timestamp_ns=ns,
            bid=2.10,
            ask=2.20,
        )

        with patch.object(adapter, "_get", return_value=snapshot):
            with patch("nexus2.utils.time_utils.is_market_hours", return_value=False):
                quote = adapter.get_quote("LRHC")

        assert quote is not None
        assert quote.price_source == "lastTrade"
        assert float(quote.price) == pytest.approx(1.78, abs=0.01)

    def test_no_fallback_spread_too_wide(self):
        """Stale + market hours but spread ≥ 5% → no midpoint fallback."""
        adapter = _make_adapter()
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=300)
        ns = _ns_from_utc(old_ts)

        # Spread = (6.00 - 5.00) / 5.00 * 100 = 20% → too wide
        snapshot = _make_snapshot_response(
            symbol="WIDE",
            last_trade_price=4.50,
            last_trade_timestamp_ns=ns,
            bid=5.00,
            ask=6.00,
        )

        with patch.object(adapter, "_get", return_value=snapshot):
            with patch("nexus2.utils.time_utils.is_market_hours", return_value=True):
                quote = adapter.get_quote("WIDE")

        assert quote is not None
        assert quote.price_source == "lastTrade"
        assert float(quote.price) == pytest.approx(4.50, abs=0.01)

    def test_no_fallback_trade_still_fresh(self):
        """Trade age < threshold → no midpoint fallback even during market hours."""
        adapter = _make_adapter()
        fresh_ts = datetime.now(timezone.utc) - timedelta(seconds=30)
        ns = _ns_from_utc(fresh_ts)

        snapshot = _make_snapshot_response(
            symbol="FRESH",
            last_trade_price=10.0,
            last_trade_timestamp_ns=ns,
            bid=10.50,
            ask=10.60,
        )

        with patch.object(adapter, "_get", return_value=snapshot):
            with patch("nexus2.utils.time_utils.is_market_hours", return_value=True):
                quote = adapter.get_quote("FRESH")

        assert quote is not None
        assert quote.price_source == "lastTrade"
        assert float(quote.price) == pytest.approx(10.0, abs=0.01)

    def test_no_fallback_no_bid_ask(self):
        """Stale trade + market hours but bid=0 → no midpoint fallback."""
        adapter = _make_adapter()
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=300)
        ns = _ns_from_utc(old_ts)

        snapshot = _make_snapshot_response(
            symbol="NOBID",
            last_trade_price=5.0,
            last_trade_timestamp_ns=ns,
            bid=0,
            ask=0,
        )

        with patch.object(adapter, "_get", return_value=snapshot):
            with patch("nexus2.utils.time_utils.is_market_hours", return_value=True):
                quote = adapter.get_quote("NOBID")

        assert quote is not None
        assert quote.price_source == "lastTrade"

    def test_stale_threshold_is_120_seconds(self):
        """Confirm STALE_TRADE_THRESHOLD_SECONDS is 120."""
        assert STALE_TRADE_THRESHOLD_SECONDS == 120


# =============================================================================
# Test Group 4: get_quotes_batch() Same Logic
# =============================================================================

class TestGetQuotesBatch:
    """Tests for timestamp + midpoint logic in get_quotes_batch."""

    def test_batch_populates_age_and_source(self):
        """Batch quotes should have quote_age_seconds and price_source per symbol."""
        adapter = _make_adapter()
        now = datetime.now(timezone.utc)
        fresh_ns = _ns_from_utc(now - timedelta(seconds=5))
        stale_ns = _ns_from_utc(now - timedelta(seconds=300))

        batch_resp = _make_batch_snapshot_response([
            {
                "symbol": "AAPL",
                "last_trade_price": 150.0,
                "ts_ns": fresh_ns,
                "bid": 149.90,
                "ask": 150.10,
                "prev_close": 148.0,
            },
            {
                "symbol": "ILLIQ",
                "last_trade_price": 1.78,
                "ts_ns": stale_ns,
                "bid": 2.10,
                "ask": 2.20,
                "prev_close": 1.50,
            },
        ])

        with patch.object(adapter, "_get", return_value=batch_resp):
            with patch("nexus2.utils.time_utils.is_market_hours", return_value=True):
                quotes = adapter.get_quotes_batch(["AAPL", "ILLIQ"])

        assert "AAPL" in quotes
        assert "ILLIQ" in quotes

        # AAPL: fresh trade → lastTrade
        aapl = quotes["AAPL"]
        assert aapl.quote_age_seconds is not None
        assert aapl.quote_age_seconds < 15
        assert aapl.price_source == "lastTrade"

        # ILLIQ: stale trade → midpoint fallback (spread < 5%)
        illiq = quotes["ILLIQ"]
        assert illiq.quote_age_seconds is not None
        assert illiq.quote_age_seconds > 100
        assert illiq.price_source == "midpoint"
        expected_midpoint = (2.10 + 2.20) / 2
        assert float(illiq.price) == pytest.approx(expected_midpoint, abs=0.01)


# =============================================================================
# Test Group 5: Quote Dataclass Backward Compatibility
# =============================================================================

class TestQuoteBackwardCompat:
    """Tests for Quote dataclass backward compatibility with new optional fields."""

    def test_old_callers_work_without_new_fields(self):
        """Creating a Quote without quote_age_seconds or price_source should work."""
        q = Quote(
            symbol="TEST",
            price=Decimal("10.00"),
            change=Decimal("0.50"),
            change_percent=Decimal("5.26"),
            volume=100_000,
            timestamp=datetime.now(timezone.utc),
        )
        assert q.quote_age_seconds is None
        assert q.price_source is None
        assert q.symbol == "TEST"
        assert q.price == Decimal("10.00")

    def test_new_fields_can_be_set(self):
        """Creating a Quote with the new fields should work."""
        q = Quote(
            symbol="TEST",
            price=Decimal("10.00"),
            change=Decimal("0.50"),
            change_percent=Decimal("5.26"),
            volume=100_000,
            timestamp=datetime.now(timezone.utc),
            quote_age_seconds=45.2,
            price_source="midpoint",
        )
        assert q.quote_age_seconds == 45.2
        assert q.price_source == "midpoint"


# =============================================================================
# Test Group 6: Single-Source Warning in unified.py
# =============================================================================

class TestSingleSourceWarning:
    """Tests for single-source warning logging in UnifiedMarketData.get_quote."""

    def _make_unified_with_polygon_only(self, polygon_quote: Quote):
        """
        Create a UnifiedMarketData where only Polygon returns data.
        All other sources (Alpaca, FMP, Schwab) return None/fail.
        """
        from nexus2.adapters.market_data.unified import UnifiedMarketData

        umd = MagicMock(spec=UnifiedMarketData)
        # Use the real get_quote method
        umd.get_quote = UnifiedMarketData.get_quote.__get__(umd, UnifiedMarketData)

        # Polygon returns our quote
        umd.polygon = MagicMock()
        umd.polygon.get_quote.return_value = polygon_quote

        # Alpaca returns None
        umd.alpaca = MagicMock()
        umd.alpaca.get_quote.return_value = None

        # FMP returns None
        umd.fmp = MagicMock()
        umd.fmp.get_quote.return_value = None

        return umd

    @patch("nexus2.api.routes.warrior_sim_routes.get_warrior_sim_broker", return_value=None)
    @patch("nexus2.domain.audit.symbol_blacklist.get_symbol_blacklist")
    @patch("nexus2.adapters.market_data.schwab_adapter.get_schwab_adapter")
    @patch("nexus2.domain.audit.quote_audit_service.get_quote_audit_service")
    @patch("nexus2.domain.audit.quote_audit_service.determine_time_window", return_value="market_hours")
    @patch("nexus2.utils.time_utils.is_market_hours", return_value=True)
    def test_single_source_logs_warning(
        self, mock_mkt_hrs, mock_tw, mock_audit, mock_schwab, mock_blacklist, mock_sim, caplog
    ):
        """When only 1 provider returns data, a WARNING with 'SINGLE SOURCE' should be logged."""
        # Schwab not authenticated
        schwab_adapter = MagicMock()
        schwab_adapter.is_authenticated.return_value = False
        mock_schwab.return_value = schwab_adapter

        # Blacklist says not blacklisted
        bl = MagicMock()
        bl.is_blacklisted.return_value = False
        mock_blacklist.return_value = bl

        # Audit service
        mock_audit.return_value = MagicMock()

        polygon_quote = Quote(
            symbol="ILLIQ",
            price=Decimal("5.00"),
            change=Decimal("0.50"),
            change_percent=Decimal("10.00"),
            volume=50_000,
            timestamp=datetime.now(timezone.utc),
            quote_age_seconds=30.0,
            price_source="lastTrade",
        )

        umd = self._make_unified_with_polygon_only(polygon_quote)

        with caplog.at_level(logging.WARNING):
            result = umd.get_quote("ILLIQ")

        assert result is not None
        assert any("SINGLE SOURCE" in record.message for record in caplog.records), \
            f"Expected 'SINGLE SOURCE' warning in logs. Got: {[r.message for r in caplog.records]}"

    @patch("nexus2.api.routes.warrior_sim_routes.get_warrior_sim_broker", return_value=None)
    @patch("nexus2.domain.audit.symbol_blacklist.get_symbol_blacklist")
    @patch("nexus2.adapters.market_data.schwab_adapter.get_schwab_adapter")
    @patch("nexus2.domain.audit.quote_audit_service.get_quote_audit_service")
    @patch("nexus2.domain.audit.quote_audit_service.determine_time_window", return_value="market_hours")
    @patch("nexus2.utils.time_utils.is_market_hours", return_value=True)
    def test_stale_polygon_logs_extra_staleness_warning(
        self, mock_mkt_hrs, mock_tw, mock_audit, mock_schwab, mock_blacklist, mock_sim, caplog
    ):
        """Single source + Polygon quote_age_seconds > 120 should also log staleness warning."""
        schwab_adapter = MagicMock()
        schwab_adapter.is_authenticated.return_value = False
        mock_schwab.return_value = schwab_adapter

        bl = MagicMock()
        bl.is_blacklisted.return_value = False
        mock_blacklist.return_value = bl

        mock_audit.return_value = MagicMock()

        stale_polygon_quote = Quote(
            symbol="ILLIQ",
            price=Decimal("1.78"),
            change=Decimal("0.28"),
            change_percent=Decimal("18.67"),
            volume=10_000,
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=300),
            quote_age_seconds=300.0,
            price_source="lastTrade",
        )

        umd = self._make_unified_with_polygon_only(stale_polygon_quote)

        with caplog.at_level(logging.WARNING):
            result = umd.get_quote("ILLIQ")

        assert result is not None

        # Should have SINGLE SOURCE warning
        single_source_logged = any("SINGLE SOURCE" in r.message for r in caplog.records)
        assert single_source_logged, \
            f"Expected 'SINGLE SOURCE' warning. Got: {[r.message for r in caplog.records]}"

        # Should have staleness warning mentioning "stale" or the age
        staleness_logged = any(
            "stale" in r.message.lower() or "300" in r.message
            for r in caplog.records
        )
        assert staleness_logged, \
            f"Expected staleness warning for 300s old quote. Got: {[r.message for r in caplog.records]}"
