"""
Tests for January 13 Session Features

Tests:
1. CatalystCache - TTL, get/set, stats
2. CatalystClassifier regex patterns - acquisition, clinical data, contracts
3. WarriorCandidate former_runner score boost
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

# =============================================================================
# CATALYST CACHE TESTS
# =============================================================================

class TestCatalystCache:
    """Test the shared catalyst cache functionality."""
    
    def test_cache_set_and_get(self):
        """Test basic cache set and get."""
        from nexus2.domain.automation.ai_catalyst_validator import CatalystCache
        
        cache = CatalystCache(ttl_minutes=5)
        cache.set("XAIR", True, "transformative_ma", "Acquisition of subsidiary")
        
        result = cache.get("XAIR")
        assert result is not None
        assert result.is_valid is True
        assert result.catalyst_type == "transformative_ma"
        assert result.description == "Acquisition of subsidiary"
    
    def test_cache_miss(self):
        """Test cache miss returns None."""
        from nexus2.domain.automation.ai_catalyst_validator import CatalystCache
        
        cache = CatalystCache(ttl_minutes=5)
        result = cache.get("UNKNOWN")
        assert result is None
    
    def test_cache_expiration(self):
        """Test cache entries expire after TTL."""
        from nexus2.domain.automation.ai_catalyst_validator import CatalystCache, CachedCatalyst
        
        cache = CatalystCache(ttl_minutes=1)  # 1 minute TTL
        
        # Manually insert an expired entry
        cache._cache["EXPIRED"] = CachedCatalyst(
            is_valid=True,
            catalyst_type="earnings",
            description="Old news",
            cached_at=datetime.now() - timedelta(minutes=10),  # 10 mins ago (expired)
        )
        
        result = cache.get("EXPIRED")
        assert result is None  # Should be expired
    
    def test_cache_fresh(self):
        """Test fresh cache entries are returned."""
        from nexus2.domain.automation.ai_catalyst_validator import CatalystCache, CachedCatalyst
        
        cache = CatalystCache(ttl_minutes=5)
        
        # Insert a fresh entry
        cache._cache["FRESH"] = CachedCatalyst(
            is_valid=True,
            catalyst_type="fda",
            description="FDA approval",
            cached_at=datetime.now() - timedelta(minutes=2),  # 2 mins ago (fresh)
        )
        
        result = cache.get("FRESH")
        assert result is not None
        assert result.catalyst_type == "fda"
    
    def test_cache_stats(self):
        """Test cache statistics."""
        from nexus2.domain.automation.ai_catalyst_validator import CatalystCache
        
        cache = CatalystCache(ttl_minutes=5)
        cache.set("PASS1", True, "earnings", "Good earnings")
        cache.set("PASS2", True, "fda", "FDA approval")
        cache.set("FAIL1", False, None, "No catalyst")
        
        stats = cache.stats()
        assert stats["size"] == 3
        assert stats["valid_count"] == 2
        assert stats["invalid_count"] == 1
    
    def test_cache_clear(self):
        """Test cache clear."""
        from nexus2.domain.automation.ai_catalyst_validator import CatalystCache
        
        cache = CatalystCache(ttl_minutes=5)
        cache.set("TEST", True, "contract", "Big deal")
        assert cache.get("TEST") is not None
        
        cache.clear()
        assert cache.get("TEST") is None


# =============================================================================
# CATALYST CLASSIFIER REGEX TESTS
# =============================================================================

class TestCatalystClassifierPatterns:
    """Test the expanded regex patterns in CatalystClassifier."""
    
    @pytest.fixture
    def classifier(self):
        from nexus2.domain.automation.catalyst_classifier import CatalystClassifier
        return CatalystClassifier()
    
    # --- Acquisition patterns ---
    def test_acquisition_acquires(self, classifier):
        """Test 'acquires' keyword."""
        result = classifier.classify("XTL Biopharmaceuticals Acquires 85% of NeuroNOS")
        assert result.is_positive is True
        assert result.catalyst_type == "acquisition"
    
    def test_acquisition_merger(self, classifier):
        """Test 'merger' keyword."""
        result = classifier.classify("Company announces merger with competitor")
        assert result.is_positive is True
        assert result.catalyst_type == "acquisition"
    
    def test_acquisition_takeover(self, classifier):
        """Test 'takeover' keyword."""
        result = classifier.classify("Hostile takeover bid announced at 40% premium")
        assert result.is_positive is True
        assert result.catalyst_type == "acquisition"
    
    # --- Clinical data patterns ---
    def test_fda_clinical_data(self, classifier):
        """Test 'clinical data' keyword."""
        result = classifier.classify("Company announces promising early clinical data")
        assert result.is_positive is True
        assert result.catalyst_type == "fda"
    
    def test_fda_clinical_results(self, classifier):
        """Test 'clinical results' keyword."""
        result = classifier.classify("Positive clinical results from Phase 2 trial")
        assert result.is_positive is True
        assert result.catalyst_type == "fda"
    
    def test_fda_complete_resolution(self, classifier):
        """Test 'complete resolution' keyword (BCTX case)."""
        result = classifier.classify("BriaCell Reports Sustained Complete Resolution of Lung Metastasis")
        assert result.is_positive is True
        assert result.catalyst_type == "fda"
    
    def test_fda_promising_clinical(self, classifier):
        """Test 'promising clinical' keyword (ERAS case)."""
        result = classifier.classify("Erasca Announces Promising Early Clinical Data for ERAS-0015")
        assert result.is_positive is True
        assert result.catalyst_type == "fda"
    
    # --- Contract patterns ---
    def test_contract_purchase_orders(self, classifier):
        """Test 'purchase orders' keyword (EVTV case)."""
        result = classifier.classify("AZIO receives $100 Million worth of Government Purchase Orders")
        assert result.is_positive is True
        assert result.catalyst_type == "contract"
    
    def test_contract_receives_million(self, classifier):
        """Test 'receives $X million' pattern."""
        result = classifier.classify("Company receives $50 million contract from DoD")
        assert result.is_positive is True
        assert result.catalyst_type == "contract"
    
    def test_contract_supplies_to(self, classifier):
        """Test 'supplies to' keyword (UAVS case)."""
        result = classifier.classify("EagleNXT Supplies Drones to NATO Forces in Europe")
        assert result.is_positive is True
        assert result.catalyst_type == "contract"
    
    def test_contract_government_order(self, classifier):
        """Test 'government order' keyword."""
        result = classifier.classify("Awarded major government order worth $200M")
        assert result.is_positive is True
        assert result.catalyst_type == "contract"
    
    # --- Earnings patterns ---
    def test_earnings_preliminary_quarter(self, classifier):
        """Test 'preliminary fourth quarter' keyword (BDSX case)."""
        result = classifier.classify("Biodesix Announces Preliminary Fourth Quarter and Full-Year 2025 Results")
        assert result.is_positive is True
        assert result.catalyst_type == "earnings"
    
    def test_earnings_full_year(self, classifier):
        """Test 'full-year results' keyword."""
        result = classifier.classify("Company reports strong full-year results")
        assert result.is_positive is True
        assert result.catalyst_type == "earnings"
    
    # --- Negative cases (should NOT match) ---
    def test_no_catalyst_generic_news(self, classifier):
        """Test generic news doesn't match."""
        result = classifier.classify("Shares Pass Below 200 Day Moving Average")
        assert result.is_positive is False
    
    def test_no_catalyst_product_launch(self, classifier):
        """Test product launch without catalyst keywords."""
        result = classifier.classify("Sleep Number Introduces ComfortMode Mattress")
        # This shouldn't match as a strong catalyst
        # (May have low confidence or no match)
        assert result.confidence < 0.6 or result.catalyst_type is None


# =============================================================================
# FORMER RUNNER SCORE BOOST TESTS
# =============================================================================

class TestFormerRunnerScoreBoost:
    """Test the former runner score boost in WarriorCandidate."""
    
    def test_score_without_former_runner(self):
        """Test quality score without former runner flag."""
        from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate
        
        candidate = WarriorCandidate(
            symbol="TEST",
            name="Test Stock",
            float_shares=15_000_000,  # +2 (ideal float)
            relative_volume=Decimal("4.0"),  # +1 (good RVOL)
            catalyst_type="earnings",  # +2 (best)
            catalyst_description="Earnings beat",
            price=Decimal("10.00"),  # +1 (sweet spot)
            gap_percent=Decimal("8.0"),  # +1 (good gap)
            is_former_runner=False,  # No boost
        )
        
        # 2 + 1 + 2 + 1 + 1 = 7
        assert candidate.quality_score == 7
    
    def test_score_with_former_runner(self):
        """Test quality score with former runner flag adds +1."""
        from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate
        
        candidate = WarriorCandidate(
            symbol="TEST",
            name="Test Stock",
            float_shares=15_000_000,  # +2 (ideal float)
            relative_volume=Decimal("4.0"),  # +1 (good RVOL)
            catalyst_type="earnings",  # +2 (best)
            catalyst_description="Earnings beat",
            price=Decimal("10.00"),  # +1 (sweet spot)
            gap_percent=Decimal("8.0"),  # +1 (good gap)
            is_former_runner=True,  # +1 boost
        )
        
        # 2 + 1 + 2 + 1 + 1 + 1 = 8
        assert candidate.quality_score == 8
    
    def test_score_max_cap(self):
        """Test quality score is capped at 10."""
        from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate
        
        candidate = WarriorCandidate(
            symbol="PERFECT",
            name="Perfect Stock",
            float_shares=5_000_000,  # +3 (excellent float)
            relative_volume=Decimal("10.0"),  # +2 (excellent RVOL)
            catalyst_type="earnings",  # +2 (best)
            catalyst_description="Beat",
            price=Decimal("8.00"),  # +1 (sweet spot)
            gap_percent=Decimal("15.0"),  # +2 (excellent gap)
            is_former_runner=True,  # +1 boost
        )
        
        # 3 + 2 + 2 + 1 + 2 + 1 = 11, but capped at 10
        assert candidate.quality_score == 10


# =============================================================================
# SLIPPAGE CALCULATION TESTS
# =============================================================================

class TestSlippageCalculation:
    """Test slippage calculation logic."""
    
    def test_slippage_cents_positive(self):
        """Test positive slippage (fill higher than intended)."""
        entry_price = Decimal("10.00")
        fill_price = Decimal("10.05")
        slippage_cents = (fill_price - entry_price) * 100
        
        assert slippage_cents == Decimal("5.0")
    
    def test_slippage_cents_negative(self):
        """Test negative slippage (fill lower than intended - good!)."""
        entry_price = Decimal("10.00")
        fill_price = Decimal("9.95")
        slippage_cents = (fill_price - entry_price) * 100
        
        assert slippage_cents == Decimal("-5.0")
    
    def test_slippage_bps(self):
        """Test slippage in basis points."""
        entry_price = Decimal("10.00")
        fill_price = Decimal("10.05")
        slippage_bps = (fill_price / entry_price - 1) * 10000
        
        assert slippage_bps == Decimal("50")  # 50 bps = 0.5%
    
    def test_slippage_zero(self):
        """Test zero slippage (perfect fill)."""
        entry_price = Decimal("10.00")
        fill_price = Decimal("10.00")
        slippage_cents = (fill_price - entry_price) * 100
        
        assert slippage_cents == Decimal("0")


# =============================================================================
# PSM INTEGRATION TESTS
# =============================================================================

class TestWarriorPSMIntegration:
    """Test Position State Machine integration with Warrior."""
    
    def test_warrior_db_uses_psm_import(self):
        """Test warrior_db imports PositionStatus."""
        from nexus2.db.warrior_db import PositionStatus
        assert hasattr(PositionStatus, 'OPEN')
        assert hasattr(PositionStatus, 'CLOSED')
        assert hasattr(PositionStatus, 'PENDING_EXIT')
        assert hasattr(PositionStatus, 'PENDING_FILL')
    
    def test_update_warrior_status_function_exists(self):
        """Test update_warrior_status function is available."""
        from nexus2.db.warrior_db import update_warrior_status
        assert callable(update_warrior_status)
    
    def test_get_warrior_trades_by_status_function_exists(self):
        """Test get_warrior_trades_by_status function is available."""
        from nexus2.db.warrior_db import get_warrior_trades_by_status
        assert callable(get_warrior_trades_by_status)
    
    def test_position_status_values(self):
        """Test PSM status values are strings."""
        from nexus2.domain.positions.position_state_machine import PositionStatus
        
        assert PositionStatus.OPEN.value == "open"
        assert PositionStatus.CLOSED.value == "closed"
        assert PositionStatus.PENDING_FILL.value == "pending_fill"
        assert PositionStatus.PENDING_EXIT.value == "pending_exit"
        assert PositionStatus.PARTIAL.value == "partial"
        assert PositionStatus.SCALING.value == "scaling"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
