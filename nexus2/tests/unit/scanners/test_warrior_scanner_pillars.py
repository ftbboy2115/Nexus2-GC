"""
Tests for Warrior Scanner Pillar Logic

Validates each of the 5 Pillars in isolation:
1. Float < 100M (ideal < 20M)
2. RVOL > 2x (ideal 3-5x)
3. Catalyst (tested elsewhere)
4. Price $1.50 - $40
5. Gap > 4% (dual-gate: opening gap OR live gap)

Also tests borrow/float disqualifiers and 200 EMA check.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from nexus2.domain.scanner.warrior_scanner_service import (
    WarriorScanSettings,
    WarriorScannerService,
    EvaluationContext,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def settings():
    """Default scanner settings."""
    return WarriorScanSettings()


@pytest.fixture
def tracker():
    """Mock rejection tracker."""
    mock = Mock()
    mock.record = Mock()
    return mock


@pytest.fixture
def scanner():
    """Scanner service with mocked dependencies."""
    mock_market_data = Mock()
    mock_market_data.fmp = Mock()
    mock_market_data.fmp.get_etf_symbols.return_value = set()
    service = WarriorScannerService(market_data=mock_market_data)
    # Mock _write_scan_result_to_db to avoid DB calls
    service._write_scan_result_to_db = Mock()
    return service


def make_ctx(settings, **overrides):
    """Create an EvaluationContext with sensible defaults."""
    defaults = dict(
        symbol="TEST",
        name="Test Stock",
        price=Decimal("10.00"),
        change_percent=Decimal("8.0"),
        verbose=False,
        settings=settings,
        session_volume=500_000,
        avg_volume=100_000,
        session_high=Decimal("11.00"),
        session_low=Decimal("9.50"),
        session_open=Decimal("10.80"),
        last_price=Decimal("10.50"),
        yesterday_close=Decimal("10.00"),
    )
    defaults.update(overrides)
    return EvaluationContext(**defaults)


# =============================================================================
# GAP PILLAR TESTS (Dual-Gate - Option C)
# =============================================================================

class TestGapPillar:
    """Test _calculate_gap_pillar() dual-gate logic."""

    def test_gap_passes_both_above_threshold(self, scanner, settings, tracker):
        """Both opening gap and live gap above 4% → PASS."""
        ctx = make_ctx(
            settings,
            session_open=Decimal("11.00"),   # 10% opening gap
            last_price=Decimal("10.80"),      # 8% live gap
            yesterday_close=Decimal("10.00"),
        )
        result = scanner._calculate_gap_pillar(ctx, tracker)
        assert result is None  # Pass
        assert ctx.opening_gap_pct == pytest.approx(10.0)
        assert ctx.live_gap_pct == pytest.approx(8.0)

    def test_gap_fails_both_below_threshold(self, scanner, settings, tracker):
        """Both opening gap and live gap below 4% → FAIL."""
        ctx = make_ctx(
            settings,
            session_open=Decimal("10.20"),   # 2% opening gap
            last_price=Decimal("10.10"),      # 1% live gap
            yesterday_close=Decimal("10.00"),
        )
        result = scanner._calculate_gap_pillar(ctx, tracker)
        assert result == "gap_too_low"
        tracker.record.assert_called_once()

    def test_gap_passes_opening_gap_only(self, scanner, settings, tracker):
        """Opening gap 30%, live gap 2% → PASS via dual-gate (faded gapper)."""
        ctx = make_ctx(
            settings,
            session_open=Decimal("13.00"),   # 30% opening gap
            last_price=Decimal("10.20"),      # 2% live gap (stock faded)
            yesterday_close=Decimal("10.00"),
        )
        result = scanner._calculate_gap_pillar(ctx, tracker)
        assert result is None  # Pass - opening gap saves it
        assert ctx.opening_gap_pct == pytest.approx(30.0)
        assert ctx.live_gap_pct == pytest.approx(2.0)
        # gap_pct should use the higher value
        assert float(ctx.gap_pct) == pytest.approx(30.0)

    def test_gap_passes_live_gap_only(self, scanner, settings, tracker):
        """Opening gap 2%, live gap 10% → PASS (stock rallied after weak open)."""
        ctx = make_ctx(
            settings,
            session_open=Decimal("10.20"),   # 2% opening gap
            last_price=Decimal("11.00"),      # 10% live gap
            yesterday_close=Decimal("10.00"),
        )
        result = scanner._calculate_gap_pillar(ctx, tracker)
        assert result is None  # Pass - live gap saves it
        assert ctx.opening_gap_pct == pytest.approx(2.0)
        assert ctx.live_gap_pct == pytest.approx(10.0)
        assert float(ctx.gap_pct) == pytest.approx(10.0)

    def test_gap_uses_change_percent_fallback(self, scanner, settings, tracker):
        """No yesterday_close → falls back to change_percent."""
        ctx = make_ctx(
            settings,
            session_open=None,
            yesterday_close=None,
            change_percent=Decimal("15.0"),
        )
        result = scanner._calculate_gap_pillar(ctx, tracker)
        assert result is None  # 15% > 4%, passes
        assert ctx.opening_gap_pct == pytest.approx(15.0)
        assert ctx.live_gap_pct == pytest.approx(15.0)

    def test_gap_ideal_flag_set(self, scanner, settings, tracker):
        """Gap >= 5% sets is_ideal_gap."""
        ctx = make_ctx(
            settings,
            session_open=Decimal("10.50"),
            last_price=Decimal("10.60"),
            yesterday_close=Decimal("10.00"),
        )
        scanner._calculate_gap_pillar(ctx, tracker)
        assert ctx.is_ideal_gap is True  # 6% > 5%

    def test_gap_ideal_flag_not_set(self, scanner, settings, tracker):
        """Gap between 4-5% does NOT set is_ideal_gap."""
        ctx = make_ctx(
            settings,
            session_open=Decimal("10.45"),   # 4.5% opening gap
            last_price=Decimal("10.40"),      # 4.0% live gap
            yesterday_close=Decimal("10.00"),
        )
        scanner._calculate_gap_pillar(ctx, tracker)
        assert ctx.is_ideal_gap is False  # 4.5% < 5%

    def test_mgrt_scenario(self, scanner, settings, tracker):
        """Reproduce the MGRT 112% gap bug — should now PASS via opening gap."""
        ctx = make_ctx(
            settings,
            symbol="MGRT",
            session_open=Decimal("4.25"),     # 112% opening gap
            last_price=Decimal("2.05"),        # Stock faded to +2% live
            yesterday_close=Decimal("2.00"),
            change_percent=Decimal("112.0"),
        )
        result = scanner._calculate_gap_pillar(ctx, tracker)
        assert result is None  # PASS - opening gap 112.5% saves it
        assert ctx.opening_gap_pct == pytest.approx(112.5)
        assert ctx.live_gap_pct == pytest.approx(2.5)


# =============================================================================
# PRICE PILLAR TESTS
# =============================================================================

class TestPricePillar:
    """Test _check_price_pillar() range check."""

    def test_price_passes_in_range(self, scanner, settings, tracker):
        """$10 is within [$1.50, $40] → PASS."""
        ctx = make_ctx(settings, price=Decimal("10.00"))
        result = scanner._check_price_pillar(ctx, tracker)
        assert result is None

    def test_price_fails_below_min(self, scanner, settings, tracker):
        """$1.00 is below $1.50 min → FAIL."""
        ctx = make_ctx(settings, price=Decimal("1.00"))
        result = scanner._check_price_pillar(ctx, tracker)
        assert result == "price_out_of_range"
        tracker.record.assert_called_once()

    def test_price_fails_above_max(self, scanner, settings, tracker):
        """$50 is above $40 max → FAIL."""
        ctx = make_ctx(settings, price=Decimal("50.00"))
        result = scanner._check_price_pillar(ctx, tracker)
        assert result == "price_out_of_range"

    def test_price_passes_at_min_boundary(self, scanner, settings, tracker):
        """$1.50 exactly → PASS (boundary inclusive)."""
        ctx = make_ctx(settings, price=Decimal("1.50"))
        result = scanner._check_price_pillar(ctx, tracker)
        assert result is None

    def test_price_passes_at_max_boundary(self, scanner, settings, tracker):
        """$40.00 exactly → PASS (boundary inclusive)."""
        ctx = make_ctx(settings, price=Decimal("40.00"))
        result = scanner._check_price_pillar(ctx, tracker)
        assert result is None


# =============================================================================
# FLOAT PILLAR TESTS
# =============================================================================

class TestFloatPillar:
    """Test _check_float_pillar() float size check."""

    def test_float_passes_under_max(self, scanner, settings, tracker):
        """50M float passes < 100M max."""
        scanner._cached = Mock(return_value=50_000_000)
        ctx = make_ctx(settings)
        result = scanner._check_float_pillar(ctx, tracker)
        assert result is None
        assert ctx.float_shares == 50_000_000

    def test_float_fails_over_max(self, scanner, settings, tracker):
        """150M float fails > 100M max."""
        scanner._cached = Mock(return_value=150_000_000)
        ctx = make_ctx(settings)
        result = scanner._check_float_pillar(ctx, tracker)
        assert result == "float_too_high"
        tracker.record.assert_called_once()

    def test_float_none_passes(self, scanner, settings, tracker):
        """None float (data unavailable) → skip check, pass."""
        scanner._cached = Mock(return_value=None)
        ctx = make_ctx(settings)
        result = scanner._check_float_pillar(ctx, tracker)
        assert result is None
        assert ctx.float_shares is None

    def test_float_ideal_flag_under_20m(self, scanner, settings, tracker):
        """Float < 20M sets is_ideal_float."""
        scanner._cached = Mock(return_value=10_000_000)
        ctx = make_ctx(settings)
        scanner._check_float_pillar(ctx, tracker)
        assert ctx.is_ideal_float is True

    def test_float_ideal_flag_over_20m(self, scanner, settings, tracker):
        """Float > 20M does NOT set is_ideal_float."""
        scanner._cached = Mock(return_value=50_000_000)
        ctx = make_ctx(settings)
        scanner._check_float_pillar(ctx, tracker)
        assert ctx.is_ideal_float is False


# =============================================================================
# BORROW / FLOAT DISQUALIFIER TESTS
# =============================================================================

class TestBorrowDisqualifiers:
    """Test _check_borrow_and_float_disqualifiers()."""

    def test_high_float_rejected(self, scanner, settings, tracker):
        """Float > 100M → rejected regardless of borrow status."""
        scanner.alpaca_broker = None  # Skip broker check
        ctx = make_ctx(settings)
        ctx.float_shares = 150_000_000
        result = scanner._check_borrow_and_float_disqualifiers(ctx, tracker)
        assert result == "high_float"

    def test_etb_high_float_rejected(self, scanner, settings, tracker):
        """ETB + float > 35M → rejected."""
        scanner.alpaca_broker = None
        ctx = make_ctx(settings)
        ctx.float_shares = 40_000_000
        ctx.easy_to_borrow = True
        result = scanner._check_borrow_and_float_disqualifiers(ctx, tracker)
        assert result == "etb_high_float"

    def test_htb_high_float_passes(self, scanner, settings, tracker):
        """HTB + float 40M → NOT rejected (ETB check doesn't apply)."""
        scanner.alpaca_broker = None
        ctx = make_ctx(settings)
        ctx.float_shares = 40_000_000
        ctx.easy_to_borrow = False
        ctx.hard_to_borrow = True
        result = scanner._check_borrow_and_float_disqualifiers(ctx, tracker)
        assert result is None  # Not rejected - HTB stocks get a pass on medium float

    def test_normal_float_passes(self, scanner, settings, tracker):
        """Float 20M → passes regardless of borrow status."""
        scanner.alpaca_broker = None
        ctx = make_ctx(settings)
        ctx.float_shares = 20_000_000
        ctx.easy_to_borrow = True
        result = scanner._check_borrow_and_float_disqualifiers(ctx, tracker)
        assert result is None
