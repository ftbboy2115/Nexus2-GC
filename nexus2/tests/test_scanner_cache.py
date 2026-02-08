"""
Tests for Scanner Caching (Wave 2)

Tests the WarriorScannerService._cached() method for correct
TTL-based caching behavior. Uses mocking to avoid real market data deps.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


# ============================================================================
# Scanner Cache Tests
# ============================================================================

class TestScannerCache:
    """Tests for scanner _cached() method (Wave 1 Item 12)."""

    def _make_scanner(self):
        """Create a minimal WarriorScannerService with mocked dependencies."""
        from nexus2.domain.scanner.warrior_scanner_service import (
            WarriorScannerService,
            WarriorScanSettings,
        )

        mock_market_data = MagicMock()
        scanner = WarriorScannerService(
            settings=WarriorScanSettings(),
            market_data=mock_market_data,
        )
        return scanner

    def test_cached_returns_fresh_value(self):
        """_cached returns fetched value on cache miss."""
        scanner = self._make_scanner()

        fetch_fn = MagicMock(return_value=42)
        result = scanner._cached("test_key", ttl_seconds=300, fetch_fn=fetch_fn)

        assert result == 42
        fetch_fn.assert_called_once()

    def test_cached_returns_cached_on_second_call(self):
        """_cached returns cached value within TTL (fetch_fn called once)."""
        scanner = self._make_scanner()

        fetch_fn = MagicMock(return_value="cached_value")

        # First call — cache miss
        result1 = scanner._cached("test_key_2", ttl_seconds=300, fetch_fn=fetch_fn)
        # Second call — should be cache hit
        result2 = scanner._cached("test_key_2", ttl_seconds=300, fetch_fn=fetch_fn)

        assert result1 == "cached_value"
        assert result2 == "cached_value"
        assert fetch_fn.call_count == 1  # Only fetched once

    def test_cached_expires_after_ttl(self):
        """_cached re-fetches after TTL expires."""
        scanner = self._make_scanner()

        call_count = 0
        def counting_fetch():
            nonlocal call_count
            call_count += 1
            return f"value_{call_count}"

        # First call — cache miss
        result1 = scanner._cached("test_key_3", ttl_seconds=1, fetch_fn=counting_fetch)
        assert result1 == "value_1"
        assert call_count == 1

        # Manually expire the cache entry by backdating the timestamp
        key_value, cached_at = scanner._cache["test_key_3"]
        scanner._cache["test_key_3"] = (key_value, cached_at - timedelta(seconds=10))

        # Second call — should be cache miss (expired)
        result2 = scanner._cached("test_key_3", ttl_seconds=1, fetch_fn=counting_fetch)
        assert result2 == "value_2"
        assert call_count == 2

    def test_cached_different_keys_independent(self):
        """Different cache keys are independent."""
        scanner = self._make_scanner()

        fetch_a = MagicMock(return_value="A")
        fetch_b = MagicMock(return_value="B")

        result_a = scanner._cached("key_a", ttl_seconds=300, fetch_fn=fetch_a)
        result_b = scanner._cached("key_b", ttl_seconds=300, fetch_fn=fetch_b)

        assert result_a == "A"
        assert result_b == "B"
        fetch_a.assert_called_once()
        fetch_b.assert_called_once()

    def test_cached_stores_none_values(self):
        """_cached stores None return values (doesn't re-fetch)."""
        scanner = self._make_scanner()

        fetch_fn = MagicMock(return_value=None)

        result1 = scanner._cached("none_key", ttl_seconds=300, fetch_fn=fetch_fn)
        result2 = scanner._cached("none_key", ttl_seconds=300, fetch_fn=fetch_fn)

        assert result1 is None
        assert result2 is None
        assert fetch_fn.call_count == 1  # Cached None, didn't re-fetch

    def test_cache_starts_empty(self):
        """New scanner instance has empty cache."""
        scanner = self._make_scanner()
        assert len(scanner._cache) == 0
