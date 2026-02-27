"""
Unit tests for L2SubscriptionManager.

Tests the dynamic subscription rotation logic: ranking by quality_score,
capping at max_symbols, evicting lowest-priority symbols when new
higher-priority candidates arrive, and status reporting.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from nexus2.domain.market_data.l2_subscription_manager import L2SubscriptionManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_watched(quality_score: int) -> MagicMock:
    """Create a mock WatchedCandidate with a given quality_score."""
    watched = MagicMock()
    watched.candidate = MagicMock()
    watched.candidate.quality_score = quality_score
    return watched


def _make_watchlist(symbols_and_scores: list[tuple[str, int]]) -> dict:
    """Build a {symbol: WatchedCandidate} dict from (symbol, score) pairs."""
    return {sym: _make_watched(score) for sym, score in symbols_and_scores}


def _mock_streamer() -> AsyncMock:
    """Create a mock SchwabL2Streamer with async update_subscriptions."""
    streamer = AsyncMock()
    streamer.update_subscriptions = AsyncMock()
    return streamer


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestL2SubscriptionManagerInit:
    """Initialization tests."""

    def test_init_with_default_max_symbols(self):
        streamer = _mock_streamer()
        mgr = L2SubscriptionManager(streamer)
        assert mgr._max_symbols == 5
        assert mgr._active_symbols == []
        assert mgr._update_count == 0

    def test_init_with_custom_max_symbols(self):
        streamer = _mock_streamer()
        mgr = L2SubscriptionManager(streamer, max_symbols=3)
        assert mgr._max_symbols == 3


class TestUpdateWatchlist:
    """Core subscription rotation logic."""

    def test_3_symbols_all_subscribed(self):
        """With 3 symbols and max=5, all 3 should be subscribed."""
        streamer = _mock_streamer()
        mgr = L2SubscriptionManager(streamer, max_symbols=5)

        watchlist = _make_watchlist([("AAPL", 80), ("TSLA", 90), ("MSFT", 70)])
        asyncio.run(mgr.update_watchlist(watchlist))

        # Streamer should be called with symbols ordered by score descending
        streamer.update_subscriptions.assert_called_once()
        subscribed = streamer.update_subscriptions.call_args[0][0]
        assert len(subscribed) == 3
        # Highest score first
        assert subscribed[0] == "TSLA"
        assert subscribed[1] == "AAPL"
        assert subscribed[2] == "MSFT"

    def test_6_symbols_max_5_only_top_5(self):
        """With 6 symbols and max=5, only top 5 by quality_score subscribed."""
        streamer = _mock_streamer()
        mgr = L2SubscriptionManager(streamer, max_symbols=5)

        watchlist = _make_watchlist([
            ("A", 10), ("B", 50), ("C", 30),
            ("D", 90), ("E", 70), ("F", 20),
        ])
        asyncio.run(mgr.update_watchlist(watchlist))

        subscribed = streamer.update_subscriptions.call_args[0][0]
        assert len(subscribed) == 5
        # "A" (score=10) should be excluded — lowest
        assert "A" not in subscribed
        # "D" (score=90) should be first
        assert subscribed[0] == "D"

    def test_higher_priority_evicts_lowest(self):
        """When a new higher-priority symbol appears, lowest gets evicted."""

        async def _run():
            streamer = _mock_streamer()
            mgr = L2SubscriptionManager(streamer, max_symbols=3)

            # Initial: 3 symbols
            wl1 = _make_watchlist([("A", 10), ("B", 50), ("C", 30)])
            await mgr.update_watchlist(wl1)
            assert mgr.get_active_subscriptions() == ["B", "C", "A"]

            # New watchlist adds D (score=90), evicting A (score=10)
            wl2 = _make_watchlist([("A", 10), ("B", 50), ("C", 30), ("D", 90)])
            await mgr.update_watchlist(wl2)

            active = mgr.get_active_subscriptions()
            assert len(active) == 3
            assert "D" in active
            assert "A" not in active

        asyncio.run(_run())

    def test_no_change_skips_update(self):
        """If watchlist hasn't changed, streamer is NOT called again."""

        async def _run():
            streamer = _mock_streamer()
            mgr = L2SubscriptionManager(streamer, max_symbols=5)

            watchlist = _make_watchlist([("AAPL", 80), ("TSLA", 90)])
            await mgr.update_watchlist(watchlist)
            assert streamer.update_subscriptions.call_count == 1

            # Same watchlist again — should skip
            await mgr.update_watchlist(watchlist)
            assert streamer.update_subscriptions.call_count == 1

        asyncio.run(_run())

    def test_empty_watchlist_clears_subscriptions(self):
        """Empty watchlist → all subscriptions cleared."""

        async def _run():
            streamer = _mock_streamer()
            mgr = L2SubscriptionManager(streamer, max_symbols=5)

            # Subscribe first
            watchlist = _make_watchlist([("AAPL", 80)])
            await mgr.update_watchlist(watchlist)
            assert mgr.get_active_subscriptions() == ["AAPL"]

            # Empty watchlist
            await mgr.update_watchlist({})
            assert mgr.get_active_subscriptions() == []
            # Streamer should be called with empty list
            streamer.update_subscriptions.assert_called_with([])

        asyncio.run(_run())

    def test_empty_watchlist_when_already_empty_is_noop(self):
        """Passing empty watchlist when already empty doesn't call streamer."""
        streamer = _mock_streamer()
        mgr = L2SubscriptionManager(streamer, max_symbols=5)

        asyncio.run(mgr.update_watchlist({}))
        assert streamer.update_subscriptions.call_count == 0


class TestGetActiveSubscriptions:
    """Tests for get_active_subscriptions."""

    def test_returns_copy_not_reference(self):
        """get_active_subscriptions returns a copy, not the internal list."""

        async def _run():
            streamer = _mock_streamer()
            mgr = L2SubscriptionManager(streamer, max_symbols=5)

            watchlist = _make_watchlist([("AAPL", 80)])
            await mgr.update_watchlist(watchlist)

            result = mgr.get_active_subscriptions()
            result.append("FAKE")
            # Internal state should not be affected
            assert "FAKE" not in mgr.get_active_subscriptions()

        asyncio.run(_run())

    def test_empty_initially(self):
        """Before any updates, active subscriptions is empty."""
        streamer = _mock_streamer()
        mgr = L2SubscriptionManager(streamer)
        assert mgr.get_active_subscriptions() == []


class TestGetStatus:
    """Tests for get_status."""

    def test_initial_status(self):
        streamer = _mock_streamer()
        mgr = L2SubscriptionManager(streamer, max_symbols=3)
        status = mgr.get_status()
        assert status == {
            "active_symbols": [],
            "max_symbols": 3,
            "update_count": 0,
        }

    def test_status_after_updates(self):

        async def _run():
            streamer = _mock_streamer()
            mgr = L2SubscriptionManager(streamer, max_symbols=5)

            await mgr.update_watchlist(
                _make_watchlist([("AAPL", 80), ("TSLA", 90)])
            )
            status = mgr.get_status()

            assert status["active_symbols"] == ["TSLA", "AAPL"]
            assert status["max_symbols"] == 5
            assert status["update_count"] == 1

        asyncio.run(_run())

    def test_update_count_increments(self):
        """Each actual subscription change increments update_count."""

        async def _run():
            streamer = _mock_streamer()
            mgr = L2SubscriptionManager(streamer, max_symbols=5)

            await mgr.update_watchlist(_make_watchlist([("AAPL", 80)]))
            assert mgr.get_status()["update_count"] == 1

            # Change watchlist
            await mgr.update_watchlist(
                _make_watchlist([("AAPL", 80), ("TSLA", 90)])
            )
            assert mgr.get_status()["update_count"] == 2

            # Same watchlist — no increment
            await mgr.update_watchlist(
                _make_watchlist([("AAPL", 80), ("TSLA", 90)])
            )
            assert mgr.get_status()["update_count"] == 2

        asyncio.run(_run())


class TestQualityScoreExtraction:
    """Tests for _get_quality_score static method."""

    def test_normal_score(self):
        watched = _make_watched(75)
        assert L2SubscriptionManager._get_quality_score(watched) == 75

    def test_zero_score(self):
        watched = _make_watched(0)
        assert L2SubscriptionManager._get_quality_score(watched) == 0

    def test_missing_quality_score_defaults_to_zero(self):
        """If candidate has no quality_score attr, default to 0."""
        watched = MagicMock()
        watched.candidate = MagicMock(spec=[])  # empty spec — no attributes
        assert L2SubscriptionManager._get_quality_score(watched) == 0

    def test_none_quality_score_defaults_to_zero(self):
        """If quality_score is None, treat as 0."""
        watched = MagicMock()
        watched.candidate = MagicMock()
        watched.candidate.quality_score = None
        assert L2SubscriptionManager._get_quality_score(watched) == 0
