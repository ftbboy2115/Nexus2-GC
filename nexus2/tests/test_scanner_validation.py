"""
Warrior Scanner Validation Test

Validates that the Warrior scanner's 5 Pillars logic would correctly
identify known Ross Cameron tickers on their trade dates.

Approach:
- Mocks all external API calls (float, volume snapshot, catalyst, 200 EMA, etc.)
- Feeds each test case's premarket data as if it were live market data
- Runs _evaluate_symbol() and verifies PASS/FAIL

Usage:
    cd nexus2
    python -m pytest tests/test_scanner_validation.py -v
    python -m pytest tests/test_scanner_validation.py -v -k "test_known_winners_pass"
"""

import pytest
import os
import yaml
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import pytz

from nexus2.domain.scanner.warrior_scanner_service import (
    WarriorScanSettings,
    WarriorScannerService,
    WarriorCandidate,
    EvaluationContext,
)


# =============================================================================
# FIXTURES
# =============================================================================

YAML_PATH = os.path.join(
    os.path.dirname(__file__), "test_cases", "warrior_setups.yaml"
)


def load_test_cases():
    """Load all test cases from YAML."""
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("test_cases", [])


def get_usable_cases():
    """Get test cases with usable data (USABLE or POLYGON_DATA status)."""
    cases = load_test_cases()
    return [
        tc for tc in cases
        if tc.get("status") in ("USABLE", "POLYGON_DATA")
        and not tc.get("synthetic", False)
    ]


def get_ross_traded_winners():
    """Get cases where Ross traded and won (strongest validation).
    
    IMPORTANT: Only includes setups the gap-up scanner is designed to catch.
    Excludes:
    - vwap_reclaim: Not a gap-up pattern (BNRG had -7% gap, entered on VWAP reclaim)
    - halt_dip: Post-halt dip buy, not scannable pre-entry
    - Sub-threshold gaps (<4%): VHUB had 3.3% gap — Ross took it as an icebreaker
      trade (news + blue sky), but scanner correctly requires ≥4% gap per strategy rules
    """
    # Setup types the gap-up scanner is NOT designed to catch
    NON_GAP_SCANNER_SETUPS = {"vwap_reclaim", "halt_dip"}
    
    return [
        tc for tc in get_usable_cases()
        if tc.get("ross_traded", False)
        and tc.get("outcome") == "winner"
        and tc.get("setup_type") not in NON_GAP_SCANNER_SETUPS
        and tc.get("premarket_data", {}).get("gap_percent", 0) >= 4.0
    ]


def get_known_losers():
    """Get cases where outcome was loser (scanner should still detect them)."""
    return [
        tc for tc in get_usable_cases()
        if tc.get("outcome") == "loser"
    ]


@pytest.fixture
def scanner_service():
    """Create a WarriorScannerService with fully mocked market data."""
    mock_market_data = Mock()
    mock_market_data.fmp = Mock()
    mock_market_data.fmp.get_etf_symbols.return_value = set()
    mock_market_data.polygon = Mock()

    service = WarriorScannerService(market_data=mock_market_data)
    # Prevent DB writes during tests
    service._write_scan_result_to_db = Mock()
    return service


def setup_mocks_for_case(scanner: WarriorScannerService, tc: dict):
    """
    Configure all mocks on the scanner to simulate the market conditions
    described in a test case.

    This mocks:
    1. Session snapshot (volume, highs/lows, open, close)
    2. Float shares
    3. Headlines/catalyst
    4. 200 EMA
    5. Country lookup
    6. Borrow status
    7. Former runner check
    8. Reverse split check
    """
    premarket = tc.get("premarket_data", {})
    expected = tc.get("expected", {})
    symbol = tc.get("symbol")

    prev_close = premarket.get("previous_close", 5.0)
    gap_pct = premarket.get("gap_percent", 25.0)
    pmh = premarket.get("premarket_high", prev_close * (1 + gap_pct / 100))
    entry_near = expected.get("entry_near", pmh)
    float_shares = premarket.get("float_shares", 5_000_000)
    catalyst = premarket.get("catalyst", "news")

    # Session open = where the stock actually opened (reflects the gap)
    # This is DIFFERENT from entry_near (Ross often enters on pullbacks below open)
    # e.g., HIND: prev_close=$5.00, gap=8.7%, open=$5.44, but Ross entered at $5.00
    session_open_price = prev_close * (1 + gap_pct / 100)

    # Current/last price: use PMH or session_open (whichever is higher — stock is running)
    # If entry_near > session_open, the stock is above its gap open
    current_price = max(session_open_price, entry_near or session_open_price, pmh or 0)

    # 1. Session snapshot - use per-case volume data when available
    # Ross only trades high volume stocks, so defaults simulate that
    # Use volume from YAML if provided, otherwise scale from gap% (bigger gaps = more volume)
    base_volume = int(premarket.get("volume", 0))
    if base_volume == 0:
        # Simulate realistic volume scaling: bigger gaps attract more volume
        gap_magnitude = max(abs(gap_pct), 10)
        base_volume = int(100_000 * (gap_magnitude / 10))  # 10% gap = 100K, 100% gap = 1M
    session_volume = max(200_000, base_volume)
    avg_volume = max(50_000, int(premarket.get("avg_volume", session_volume // 8)))

    scanner.market_data.build_session_snapshot.return_value = {
        "session_volume": session_volume,
        "avg_daily_volume": avg_volume,
        "session_high": float(pmh) if pmh else float(current_price) * 1.05,
        "session_low": float(prev_close),
        "session_open": float(session_open_price),
        "last_price": float(current_price),
        "yesterday_close": float(prev_close),
    }

    # 2. Float shares - use test case value or default to 5M (low float)
    # Mock _cached to return appropriate values based on key prefix
    original_cached = scanner._cached

    def mock_cached(key, ttl, fetch_fn):
        if key.startswith("float:"):
            return float_shares
        if key.startswith("country:"):
            return "US"
        if key.startswith("runner:"):
            return False
        # For other cache keys, call fetch
        try:
            return fetch_fn()
        except Exception:
            return None

    scanner._cached = mock_cached

    # 3. Headlines/catalyst - always provide a catalyst headline
    catalyst_headline = _generate_catalyst_headline(catalyst, symbol)
    scanner.market_data.get_merged_headlines.return_value = [catalyst_headline]

    # 4. Mock catalyst evaluation to always pass (we're testing the pillars, not AI)
    # The real _evaluate_catalyst_pillar calls AI models which we can't use in tests
    def mock_catalyst_pillar(ctx, tracker, headlines):
        ctx.has_catalyst = True
        ctx.catalyst_type = catalyst
        ctx.catalyst_desc = catalyst_headline
        ctx.catalyst_confidence = 0.9
        ctx.catalyst_date = datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        return None  # Pass

    scanner._evaluate_catalyst_pillar = mock_catalyst_pillar

    # 5. Mock multi-model and legacy AI (these are called AFTER catalyst pillar)
    scanner._run_multi_model_catalyst_validation = Mock()
    scanner._run_legacy_ai_fallback = Mock()

    # 6. 200 EMA - mock to return None (no 200 EMA resistance)
    scanner._get_200_ema = Mock(return_value=None)

    # 7. Borrow status - no alpaca broker in tests
    scanner.alpaca_broker = None

    # 8. Reverse split - mock to do nothing
    scanner._check_reverse_split = Mock()


def _generate_catalyst_headline(catalyst_type: str, symbol: str) -> str:
    """Generate a realistic headline for the catalyst type."""
    headlines = {
        "news": f"{symbol} announces strategic partnership",
        "headline": f"Breaking: {symbol} receives FDA approval",
        "earnings": f"{symbol} beats Q4 earnings estimates",
        "momentum": f"{symbol} surges on high volume momentum",
        "continuation": f"{symbol} continues multi-day squeeze",
        "reverse_split": f"{symbol} completes reverse stock split",
        "biotech_news": f"{symbol} announces positive phase 3 trial results",
        "natural_gas_prices": f"{symbol} surges on natural gas price increase",
        "crypto_treasury": f"{symbol} announces Bitcoin treasury strategy",
        "theme_momentum": f"{symbol} rallies on prediction markets theme",
        "sympathy_momentum": f"{symbol} moves in sympathy with sector leader",
        "overnight_gapper": f"{symbol} gaps up 300%+ overnight",
    }
    return headlines.get(catalyst_type, f"{symbol} - {catalyst_type}")


# =============================================================================
# CORE TESTS
# =============================================================================

class TestScannerPicksUpValidTickers:
    """
    Validate that the Warrior scanner correctly identifies known valid tickers.

    These are stocks that Ross Cameron actually traded and profited from.
    The scanner should pass them through all 5 Pillars when given their
    actual market conditions.
    """

    @pytest.mark.parametrize(
        "tc",
        get_ross_traded_winners(),
        ids=[tc["id"] for tc in get_ross_traded_winners()],
    )
    def test_known_winners_pass(self, scanner_service, tc):
        """
        Ross Cameron winners should PASS the scanner's 5 Pillars.

        These are real trades where Ross entered and made money.
        If our scanner rejects them, we're filtering too aggressively.
        """
        setup_mocks_for_case(scanner_service, tc)

        premarket = tc.get("premarket_data", {})
        prev_close = premarket.get("previous_close", 5.0)
        gap_pct = premarket.get("gap_percent", 25.0)
        expected = tc.get("expected", {})
        entry_near = expected.get("entry_near")
        current_price = entry_near if entry_near else prev_close * (1 + gap_pct / 100)

        with patch("nexus2.domain.scanner.warrior_scanner_service.get_rejection_tracker") as mock_tracker:
            mock_tracker.return_value = Mock()
            mock_tracker.return_value.record = Mock()

            # Use symbol as name (NOT description) to avoid Chinese keyword
            # detection on descriptions like "Chinese IPO Blue Sky Short Squeeze"
            candidate = scanner_service._evaluate_symbol(
                symbol=tc["symbol"],
                name=tc["symbol"],
                price=Decimal(str(round(current_price, 2))),
                change_percent=Decimal(str(gap_pct)),
                verbose=False,  # Avoid Windows cp1252 emoji encoding errors
            )

        assert candidate is not None, (
            f"Scanner REJECTED {tc['symbol']} ({tc['id']}) — "
            f"Ross made ${tc.get('ross_pnl', '?')} on this trade. "
            f"Gap: {gap_pct}%, Price: ${current_price:.2f}"
        )

        print(
            f"✅ {tc['symbol']:6s} | Score: {candidate.quality_score:2d} | "
            f"Gap: {gap_pct:6.1f}% | RVOL: {float(candidate.relative_volume):5.1f}x | "
            f"Ross P&L: ${tc.get('ross_pnl', 0):>10,.2f}"
        )


class TestScannerPillarIsolation:
    """
    Test each pillar in isolation with known-good test case data
    to identify which specific pillar would reject a valid ticker.
    """

    @pytest.mark.parametrize(
        "tc",
        get_usable_cases()[:5],  # Test first 5 usable cases
        ids=[tc["id"] for tc in get_usable_cases()[:5]],
    )
    def test_price_pillar_accepts(self, scanner_service, tc):
        """Price pillar should accept all test case prices ($1.50 - $40)."""
        premarket = tc.get("premarket_data", {})
        expected = tc.get("expected", {})
        prev_close = premarket.get("previous_close", 5.0)
        gap_pct = premarket.get("gap_percent", 25.0)
        entry_near = expected.get("entry_near")
        price = entry_near if entry_near else prev_close * (1 + gap_pct / 100)

        settings = WarriorScanSettings()
        ctx = EvaluationContext(
            symbol=tc["symbol"],
            name=tc["symbol"],
            price=Decimal(str(round(price, 2))),
            change_percent=Decimal(str(gap_pct)),
            verbose=False,
            settings=settings,
        )
        tracker = Mock()
        tracker.record = Mock()

        result = scanner_service._check_price_pillar(ctx, tracker)
        assert result is None, (
            f"Price pillar rejected {tc['symbol']} at ${price:.2f}. "
            f"Range: ${settings.min_price} - ${settings.max_price}"
        )

    @pytest.mark.parametrize(
        "tc",
        get_usable_cases()[:5],
        ids=[tc["id"] for tc in get_usable_cases()[:5]],
    )
    def test_gap_pillar_accepts(self, scanner_service, tc):
        """Gap pillar should accept all test case gap percentages."""
        premarket = tc.get("premarket_data", {})
        expected = tc.get("expected", {})
        gap_pct = premarket.get("gap_percent", 25.0)
        prev_close = premarket.get("previous_close", 5.0)
        entry_near = expected.get("entry_near")
        price = entry_near if entry_near else prev_close * (1 + gap_pct / 100)
        session_open = prev_close * (1 + gap_pct / 100)

        settings = WarriorScanSettings()
        ctx = EvaluationContext(
            symbol=tc["symbol"],
            name=tc["symbol"],
            price=Decimal(str(round(price, 2))),
            change_percent=Decimal(str(gap_pct)),
            verbose=False,
            settings=settings,
            session_open=Decimal(str(round(session_open, 2))),
            last_price=Decimal(str(round(price, 2))),
            yesterday_close=Decimal(str(prev_close)),
        )
        tracker = Mock()
        tracker.record = Mock()

        result = scanner_service._calculate_gap_pillar(ctx, tracker)
        assert result is None, (
            f"Gap pillar rejected {tc['symbol']} with {gap_pct:.1f}% gap. "
            f"Min required: {settings.min_gap}%"
        )

    @pytest.mark.parametrize(
        "tc",
        get_usable_cases()[:5],
        ids=[tc["id"] for tc in get_usable_cases()[:5]],
    )
    def test_float_pillar_accepts(self, scanner_service, tc):
        """Float pillar should accept all test case floats."""
        premarket = tc.get("premarket_data", {})
        float_shares = premarket.get("float_shares", 5_000_000)

        settings = WarriorScanSettings()
        ctx = EvaluationContext(
            symbol=tc["symbol"],
            name=tc["symbol"],
            price=Decimal("10.00"),
            change_percent=Decimal("25.0"),
            verbose=False,
            settings=settings,
        )

        # Mock _cached to return the test case's float
        scanner_service._cached = Mock(return_value=float_shares)
        tracker = Mock()
        tracker.record = Mock()

        result = scanner_service._check_float_pillar(ctx, tracker)
        assert result is None, (
            f"Float pillar rejected {tc['symbol']} with {float_shares:,} float. "
            f"Max allowed: {settings.max_float:,}"
        )


class TestScannerRejectsJunk:
    """Verify the scanner correctly rejects stocks that shouldn't pass."""

    def test_rejects_high_price(self, scanner_service):
        """Stocks above $40 should be rejected."""
        settings = WarriorScanSettings()
        ctx = EvaluationContext(
            symbol="EXPENSIVE",
            name="Expensive Stock",
            price=Decimal("150.00"),
            change_percent=Decimal("10.0"),
            verbose=False,
            settings=settings,
        )
        tracker = Mock()
        tracker.record = Mock()
        result = scanner_service._check_price_pillar(ctx, tracker)
        assert result == "price_out_of_range"

    def test_rejects_low_price(self, scanner_service):
        """Stocks below $1.50 should be rejected."""
        settings = WarriorScanSettings()
        ctx = EvaluationContext(
            symbol="PENNY",
            name="Penny Stock",
            price=Decimal("0.50"),
            change_percent=Decimal("10.0"),
            verbose=False,
            settings=settings,
        )
        tracker = Mock()
        tracker.record = Mock()
        result = scanner_service._check_price_pillar(ctx, tracker)
        assert result == "price_out_of_range"

    def test_rejects_no_gap(self, scanner_service):
        """Stocks with <4% gap should be rejected."""
        settings = WarriorScanSettings()
        ctx = EvaluationContext(
            symbol="FLAT",
            name="Flat Stock",
            price=Decimal("10.00"),
            change_percent=Decimal("2.0"),
            verbose=False,
            settings=settings,
            session_open=Decimal("10.20"),
            last_price=Decimal("10.10"),
            yesterday_close=Decimal("10.00"),
        )
        tracker = Mock()
        tracker.record = Mock()
        result = scanner_service._calculate_gap_pillar(ctx, tracker)
        assert result == "gap_too_low"

    def test_rejects_huge_float(self, scanner_service):
        """Stocks with >100M float should be rejected."""
        settings = WarriorScanSettings()
        ctx = EvaluationContext(
            symbol="BIGCAP",
            name="Big Cap Stock",
            price=Decimal("10.00"),
            change_percent=Decimal("10.0"),
            verbose=False,
            settings=settings,
        )
        scanner_service._cached = Mock(return_value=200_000_000)
        tracker = Mock()
        tracker.record = Mock()
        result = scanner_service._check_float_pillar(ctx, tracker)
        assert result == "float_too_high"


# =============================================================================
# SUMMARY REPORT
# =============================================================================

class TestScannerSummaryReport:
    """Run all usable cases and print a summary report."""

    def test_full_scan_report(self, scanner_service):
        """
        Run ALL usable test cases through the scanner and report results.

        This is a diagnostic test — it prints a detailed report but
        does not fail on individual rejections (the parametrized tests do that).
        """
        cases = get_usable_cases()
        passed = []
        failed = []

        for tc in cases:
            setup_mocks_for_case(scanner_service, tc)

            premarket = tc.get("premarket_data", {})
            expected = tc.get("expected", {})
            prev_close = premarket.get("previous_close", 5.0)
            gap_pct = premarket.get("gap_percent", 25.0)
            entry_near = expected.get("entry_near")
            current_price = entry_near if entry_near else prev_close * (1 + gap_pct / 100)

            with patch("nexus2.domain.scanner.warrior_scanner_service.get_rejection_tracker") as mock_tracker:
                mock_tracker.return_value = Mock()
                mock_tracker.return_value.record = Mock()

                try:
                    candidate = scanner_service._evaluate_symbol(
                        symbol=tc["symbol"],
                        name=tc["symbol"],
                        price=Decimal(str(round(current_price, 2))),
                        change_percent=Decimal(str(gap_pct)),
                        verbose=False,
                    )

                    if candidate:
                        passed.append((tc, candidate))
                    else:
                        failed.append((tc, None))
                except Exception as e:
                    failed.append((tc, str(e)))

        # Print report
        print("\n" + "=" * 80)
        print("WARRIOR SCANNER VALIDATION REPORT")
        print("=" * 80)
        print(f"\nTotal cases: {len(cases)} | Passed: {len(passed)} | Failed: {len(failed)}")
        print(f"Pass rate: {len(passed) / len(cases) * 100:.0f}%")

        if passed:
            print(f"\n{'─' * 80}")
            print("✅ PASSED:")
            print(f"{'─' * 80}")
            for tc, cand in passed:
                ross_note = f" (Ross: ${tc.get('ross_pnl', 0):,.0f})" if tc.get("ross_traded") else ""
                print(
                    f"  {tc['symbol']:6s} | Score: {cand.quality_score:2d} | "
                    f"Gap: {tc['premarket_data'].get('gap_percent', 0):6.1f}% | "
                    f"RVOL: {float(cand.relative_volume):5.1f}x | "
                    f"{tc.get('outcome', '?'):8s}{ross_note}"
                )

        if failed:
            print(f"\n{'─' * 80}")
            print("❌ FAILED:")
            print(f"{'─' * 80}")
            for tc, err in failed:
                ross_note = f" (Ross: ${tc.get('ross_pnl', 0):,.0f})" if tc.get("ross_traded") else ""
                print(
                    f"  {tc['symbol']:6s} | "
                    f"Gap: {tc['premarket_data'].get('gap_percent', 0):6.1f}% | "
                    f"{tc.get('outcome', '?'):8s}{ross_note} | "
                    f"Error: {err if isinstance(err, str) else 'Rejected'}"
                )

        print("=" * 80)

        # The report should show a high pass rate for usable cases
        # We expect >80% since we pre-filter for valid data
        ross_winners = [tc for tc, _ in passed if tc.get("ross_traded") and tc.get("outcome") == "winner"]
        ross_winner_total = len([tc for tc in cases if tc.get("ross_traded") and tc.get("outcome") == "winner"])

        if ross_winner_total > 0:
            print(f"\nRoss Cameron Winners: {len(ross_winners)}/{ross_winner_total} passed")
            assert len(ross_winners) / ross_winner_total >= 0.8, (
                f"Less than 80% of Ross Cameron winners passed the scanner! "
                f"({len(ross_winners)}/{ross_winner_total})"
            )
