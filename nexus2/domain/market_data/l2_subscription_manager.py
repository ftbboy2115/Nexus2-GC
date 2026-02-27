"""
L2 Subscription Manager

Dynamically manages L2 (Level 2 / Order Book) streaming subscriptions
based on the Warrior engine's current watchlist. Ranks candidates by
quality_score and subscribes the top N symbols, rotating subscriptions
as the watchlist evolves.

Feature-gated behind L2_ENABLED config flag.
"""

import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from nexus2.adapters.market_data.schwab_l2_streamer import SchwabL2Streamer
    from nexus2.domain.automation.warrior_engine_types import WatchedCandidate

logger = logging.getLogger(__name__)


class L2SubscriptionManager:
    """
    Dynamic L2 subscription manager that rotates symbols based on scanner output.

    Ranks watched candidates by quality_score and subscribes the top N
    (capped by max_symbols) to the L2 streamer. When higher-priority
    candidates appear, it unsubscribes the lowest-priority symbols and
    subscribes the new ones.
    """

    def __init__(
        self,
        streamer: "SchwabL2Streamer",
        max_symbols: int = 5,
    ):
        self._streamer = streamer
        self._max_symbols = max_symbols
        self._active_symbols: List[str] = []  # Ordered by priority (highest first)
        self._update_count = 0

    async def update_watchlist(
        self, watchlist: Dict[str, "WatchedCandidate"]
    ) -> None:
        """
        Update L2 subscriptions based on the current watchlist.

        Called after each scan cycle. Ranks candidates by quality_score,
        selects the top N, and diffs against current subscriptions.

        Args:
            watchlist: Current watchlist dict {symbol: WatchedCandidate}
        """
        if not watchlist:
            # No candidates — unsubscribe all
            if self._active_symbols:
                old = list(self._active_symbols)
                await self._streamer.update_subscriptions([])
                self._active_symbols.clear()
                logger.info(
                    "[L2 Sub Manager] Cleared all subscriptions (watchlist empty): %s",
                    old,
                )
            return

        # Rank candidates by quality_score (descending)
        ranked = sorted(
            watchlist.items(),
            key=lambda item: self._get_quality_score(item[1]),
            reverse=True,
        )

        # Select top N symbols
        desired_symbols = [symbol for symbol, _ in ranked[: self._max_symbols]]

        # Skip if no change
        if desired_symbols == self._active_symbols:
            return

        # Compute diff for logging
        old_set = set(self._active_symbols)
        new_set = set(desired_symbols)
        added = new_set - old_set
        removed = old_set - new_set

        # Update streamer subscriptions (handles diff internally)
        await self._streamer.update_subscriptions(desired_symbols)
        self._active_symbols = desired_symbols
        self._update_count += 1

        if added or removed:
            logger.info(
                "[L2 Sub Manager] Subscriptions updated (#%d): "
                "added=%s, removed=%s, active=%s",
                self._update_count,
                list(added) if added else "[]",
                list(removed) if removed else "[]",
                self._active_symbols,
            )

    def get_active_subscriptions(self) -> List[str]:
        """Return currently subscribed symbols (ordered by priority)."""
        return list(self._active_symbols)

    def get_status(self) -> dict:
        """Status dict for engine status endpoint."""
        return {
            "active_symbols": list(self._active_symbols),
            "max_symbols": self._max_symbols,
            "update_count": self._update_count,
        }

    @staticmethod
    def _get_quality_score(watched: "WatchedCandidate") -> int:
        """Extract quality_score from a WatchedCandidate, defaulting to 0."""
        return getattr(watched.candidate, "quality_score", 0) or 0
