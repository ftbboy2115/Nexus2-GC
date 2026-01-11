"""
Tests for Scanner Engine
"""

import pytest
from decimal import Decimal
from datetime import datetime

from nexus2.domain.scanner.models import (
    Stock,
    StockMetrics,
    Exchange,
    WatchlistTier,
)
from nexus2.domain.scanner.scanner_engine import ScannerEngine
from nexus2.settings.scanner_settings import (
    ScannerSettings,
    DisqualifierSettings,
    QualityScoringSettings,
)


@pytest.fixture
def scanner_settings():
    return ScannerSettings()


@pytest.fixture
def disqualifier_settings():
    return DisqualifierSettings()


@pytest.fixture
def scoring_settings():
    return QualityScoringSettings()


@pytest.fixture
def scanner_engine(scanner_settings, disqualifier_settings, scoring_settings):
    return ScannerEngine(
        settings=scanner_settings,
        disqualifiers=disqualifier_settings,
        scoring=scoring_settings,
    )


@pytest.fixture
def valid_stock():
    return Stock(
        symbol="NVDA",
        name="NVIDIA Corporation",
        exchange=Exchange.NASDAQ,
        price=Decimal("450.00"),
        market_cap=Decimal("1_000_000_000_000"),
        float_shares=2_000_000_000,
        avg_volume_20d=50_000_000,
        dollar_volume=Decimal("22_500_000_000"),
        adr_percent=Decimal("5.0"),
    )


@pytest.fixture
def valid_metrics():
    return StockMetrics(
        symbol="NVDA",
        performance_1m=Decimal("30.0"),
        performance_3m=Decimal("60.0"),
        performance_6m=Decimal("120.0"),
        rs_percentile=95,
        rs_line_52w_high=True,
        price_vs_sma10=Decimal("2.0"),
        price_vs_sma20=Decimal("5.0"),
        price_vs_sma50=Decimal("15.0"),
        price_vs_sma200=Decimal("45.0"),
        price_vs_ema10=Decimal("2.0"),
        price_vs_ema20=Decimal("5.0"),
        price_vs_ema21=Decimal("5.5"),
        ma_stacked=True,
        atr=Decimal("15.0"),
        adr_percent=Decimal("5.0"),
        avg_volume_20d=50_000_000,
        dollar_volume=Decimal("22_500_000_000"),
        volume_contraction=True,
        distance_to_52w_high=Decimal("5.0"),
        quality_score=9,
        updated_at=datetime.now(),
    )


class TestScannerEngine:
    """Tests for ScannerEngine."""
    
    def test_quality_score_high_quality_stock(
        self, scanner_engine, valid_stock, valid_metrics
    ):
        """High quality stock should score 8+."""
        score = scanner_engine.calculate_quality_score(valid_stock, valid_metrics)
        assert score >= 8, f"Expected score >= 8, got {score}"
    
    def test_quality_score_low_price_stock(
        self, scanner_engine, valid_metrics
    ):
        """Low price stock should score lower."""
        low_price_stock = Stock(
            symbol="CHEAP",
            name="Cheap Stock",
            exchange=Exchange.NASDAQ,
            price=Decimal("3.00"),  # Below minimum
            market_cap=Decimal("100_000_000"),
            float_shares=100_000_000,
            avg_volume_20d=100_000,  # Low volume
            dollar_volume=Decimal("300_000"),  # Low dollar volume
            adr_percent=Decimal("3.0"),
        )
        score = scanner_engine.calculate_quality_score(low_price_stock, valid_metrics)
        assert score < 8, f"Expected score < 8 for low quality, got {score}"
    
    def test_disqualifier_otc_exchange(
        self, scanner_engine, valid_metrics
    ):
        """OTC stocks should be disqualified."""
        otc_stock = Stock(
            symbol="OTCPINK",
            name="OTC Stock",
            exchange=Exchange.OTC,
            price=Decimal("10.00"),
            market_cap=Decimal("500_000_000"),
            float_shares=100_000_000,
            avg_volume_20d=500_000,
            dollar_volume=Decimal("5_000_000"),
            adr_percent=Decimal("5.0"),
        )
        errors = scanner_engine.check_disqualifiers(otc_stock, valid_metrics)
        assert any("OTC" in e for e in errors), "OTC should be disqualified"
    
    def test_disqualifier_below_min_price(
        self, scanner_engine, valid_metrics
    ):
        """Stocks below absolute min price should be disqualified."""
        penny_stock = Stock(
            symbol="PENNY",
            name="Penny Stock",
            exchange=Exchange.NASDAQ,
            price=Decimal("1.50"),  # Below $2 absolute min
            market_cap=Decimal("50_000_000"),
            float_shares=100_000_000,
            avg_volume_20d=500_000,
            dollar_volume=Decimal("750_000"),
            adr_percent=Decimal("10.0"),
        )
        errors = scanner_engine.check_disqualifiers(penny_stock, valid_metrics)
        assert any("minimum" in e.lower() for e in errors), "Low price should be disqualified"
    
    def test_evaluate_stock_passes_all(
        self, scanner_engine, valid_stock, valid_metrics
    ):
        """Valid stock should pass all criteria."""
        result = scanner_engine.evaluate_stock(valid_stock, valid_metrics)
        assert result.passes_filter, f"Should pass, but failed: {result.failed_criteria}"
        assert result.quality_score >= 7
        assert result.tier_recommendation in (WatchlistTier.FOCUS, WatchlistTier.WIDE)
    
    def test_tier_recommendation_high_quality(
        self, scanner_engine, valid_stock, valid_metrics
    ):
        """High quality stocks should be recommended for Focus."""
        result = scanner_engine.evaluate_stock(valid_stock, valid_metrics)
        # Score should be high enough for FOCUS or WIDE
        assert result.tier_recommendation != WatchlistTier.UNIVERSE
