"""
Unit tests for CatalystCache - shared catalyst validation cache.
"""

import pytest
from datetime import datetime, timedelta


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
        from nexus2.utils.time_utils import now_et
        
        cache = CatalystCache(ttl_minutes=1)  # 1 minute TTL
        
        # Manually insert an expired entry (use timezone-aware datetime)
        cache._cache["EXPIRED"] = CachedCatalyst(
            is_valid=True,
            catalyst_type="earnings",
            description="Old news",
            cached_at=now_et() - timedelta(minutes=10),  # 10 mins ago (expired)
        )
        
        result = cache.get("EXPIRED")
        assert result is None  # Should be expired
    
    def test_cache_fresh(self):
        """Test fresh cache entries are returned."""
        from nexus2.domain.automation.ai_catalyst_validator import CatalystCache, CachedCatalyst
        from nexus2.utils.time_utils import now_et
        
        cache = CatalystCache(ttl_minutes=5)
        
        # Insert a fresh entry (use timezone-aware datetime)
        cache._cache["FRESH"] = CachedCatalyst(
            is_valid=True,
            catalyst_type="fda",
            description="FDA approval",
            cached_at=now_et() - timedelta(minutes=2),  # 2 mins ago (fresh)
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
