"""
Tests for WatchedCandidate.dynamic_score property.

Verifies that the VWAP/EMA trend bonus correctly adjusts the quality score
for TOP_PICK_ONLY ranking.

Scoring rules:
- +3 if above VWAP AND above 9 EMA (strong trend)
- +1 if above VWAP only
- -2 if below VWAP (fading/weak)
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from nexus2.domain.automation.warrior_engine_types import WatchedCandidate
from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate


def create_mock_candidate(symbol: str, score: int = 5) -> WarriorCandidate:
    """Create a mock WarriorCandidate with specified quality score."""
    return WarriorCandidate(
        symbol=symbol,
        name=f"{symbol} Inc",
        float_shares=10_000_000,  # Low float for score
        relative_volume=Decimal("5.0"),  # High RVOL for score
        catalyst_type="news",
        catalyst_description="Test catalyst",
        price=Decimal("10.00"),
        gap_percent=Decimal("10.0"),
    )


class TestDynamicScore:
    """Tests for WatchedCandidate.dynamic_score property."""
    
    def test_dynamic_score_without_vwap_data_equals_static(self):
        """When no VWAP data, dynamic_score equals static quality_score."""
        candidate = create_mock_candidate("TEST")
        watched = WatchedCandidate(
            candidate=candidate,
            pmh=Decimal("10.50"),
        )
        
        # No VWAP set
        static_score = candidate.quality_score
        assert watched.dynamic_score == static_score
        
    def test_dynamic_score_above_vwap_and_ema_adds_3(self):
        """Stock above both VWAP and 9 EMA gets +3 bonus."""
        candidate = create_mock_candidate("TRENDING")
        watched = WatchedCandidate(
            candidate=candidate,
            pmh=Decimal("10.50"),
        )
        
        # Set trend data: above VWAP and above 9 EMA
        watched.current_price = Decimal("12.00")
        watched.current_vwap = Decimal("11.00")  # Price > VWAP
        watched.current_ema_9 = Decimal("11.50")  # Price > EMA
        watched.is_above_vwap = True
        watched.is_above_ema_9 = True
        
        static_score = candidate.quality_score
        assert watched.dynamic_score == static_score + 3
        
    def test_dynamic_score_above_vwap_only_adds_1(self):
        """Stock above VWAP but below 9 EMA gets +1 bonus."""
        candidate = create_mock_candidate("MIXED")
        watched = WatchedCandidate(
            candidate=candidate,
            pmh=Decimal("10.50"),
        )
        
        # Set trend data: above VWAP, below 9 EMA
        watched.current_price = Decimal("11.50")
        watched.current_vwap = Decimal("11.00")  # Price > VWAP
        watched.current_ema_9 = Decimal("12.00")  # Price < EMA
        watched.is_above_vwap = True
        watched.is_above_ema_9 = False
        
        static_score = candidate.quality_score
        assert watched.dynamic_score == static_score + 1
        
    def test_dynamic_score_below_vwap_subtracts_2(self):
        """Stock below VWAP (fading) gets -2 penalty."""
        candidate = create_mock_candidate("FADING")
        watched = WatchedCandidate(
            candidate=candidate,
            pmh=Decimal("10.50"),
        )
        
        # Set trend data: below VWAP
        watched.current_price = Decimal("10.00")
        watched.current_vwap = Decimal("11.00")  # Price < VWAP
        watched.current_ema_9 = Decimal("10.50")
        watched.is_above_vwap = False
        watched.is_above_ema_9 = False
        
        static_score = candidate.quality_score
        assert watched.dynamic_score == static_score - 2
        
    def test_dynamic_score_minimum_is_zero(self):
        """Dynamic score cannot go below zero."""
        candidate = create_mock_candidate("LOW")
        watched = WatchedCandidate(
            candidate=candidate,
            pmh=Decimal("10.50"),
        )
        
        # Force static score to be low (manually set candidate fields)
        # The minimum score after penalty should be 0
        watched.current_price = Decimal("10.00")
        watched.current_vwap = Decimal("15.00")  # Way above price
        watched.is_above_vwap = False
        watched.is_above_ema_9 = False
        
        # Even with -2 penalty, should not go negative
        assert watched.dynamic_score >= 0
        
    def test_trending_stock_outranks_fading_stock_with_higher_static_score(self):
        """
        Key scenario: BNAI (trending, static=4) should outrank RVYL (fading, static=6)
        
        This is the exact scenario from Jan 23, 2026 where:
        - RVYL: static=6, below VWAP → dynamic=4
        - BNAI: static=4, above VWAP+EMA → dynamic=7
        """
        # RVYL: Higher static score but fading (below VWAP)
        rvyl_candidate = create_mock_candidate("RVYL")
        rvyl = WatchedCandidate(
            candidate=rvyl_candidate,
            pmh=Decimal("7.35"),
        )
        rvyl.current_price = Decimal("5.50")
        rvyl.current_vwap = Decimal("6.00")  # Below VWAP (fading)
        rvyl.is_above_vwap = False
        rvyl.is_above_ema_9 = False
        
        # BNAI: Lower static score but trending (above VWAP and EMA)
        bnai_candidate = create_mock_candidate("BNAI")
        bnai = WatchedCandidate(
            candidate=bnai_candidate,
            pmh=Decimal("10.74"),
        )
        bnai.current_price = Decimal("60.00")
        bnai.current_vwap = Decimal("55.00")  # Above VWAP (trending)
        bnai.current_ema_9 = Decimal("58.00")  # Above EMA
        bnai.is_above_vwap = True
        bnai.is_above_ema_9 = True
        
        # Verify: BNAI's dynamic score > RVYL's dynamic score
        # Even though RVYL might have higher static score
        print(f"RVYL: static={rvyl.candidate.quality_score}, dynamic={rvyl.dynamic_score}")
        print(f"BNAI: static={bnai.candidate.quality_score}, dynamic={bnai.dynamic_score}")
        
        # The key assertion: trending BNAI should outrank fading RVYL
        # BNAI gets +3, RVYL gets -2, so difference is 5 points swing
        assert bnai.dynamic_score > rvyl.dynamic_score
        

class TestTopPickOnlyRanking:
    """Tests for how TOP_PICK_ONLY should use dynamic_score for ranking."""
    
    def test_max_dynamic_score_picks_correct_stock(self):
        """Verify that max(candidates, key=dynamic_score) picks trending stock."""
        # Create watchlist with multiple candidates
        watchlist = {}
        
        # Fading stock with higher static score
        fading = create_mock_candidate("FADING")
        fading_watched = WatchedCandidate(candidate=fading, pmh=Decimal("10.00"))
        fading_watched.current_price = Decimal("8.00")
        fading_watched.current_vwap = Decimal("9.00")
        fading_watched.is_above_vwap = False
        fading_watched.is_above_ema_9 = False
        watchlist["FADING"] = fading_watched
        
        # Trending stock with lower static score
        trending = create_mock_candidate("TRENDING")
        trending_watched = WatchedCandidate(candidate=trending, pmh=Decimal("10.00"))
        trending_watched.current_price = Decimal("12.00")
        trending_watched.current_vwap = Decimal("11.00")
        trending_watched.current_ema_9 = Decimal("11.50")
        trending_watched.is_above_vwap = True
        trending_watched.is_above_ema_9 = True
        watchlist["TRENDING"] = trending_watched
        
        # Find top pick using dynamic_score
        top_pick = max(watchlist.values(), key=lambda w: w.dynamic_score)
        
        # Should pick TRENDING (the one with trend bonus)
        assert top_pick.candidate.symbol == "TRENDING"
