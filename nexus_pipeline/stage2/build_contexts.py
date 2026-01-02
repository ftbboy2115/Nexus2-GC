"""
File: nexus_pipeline/stage2/build_contexts.py
Version: 2.0.0
Author: Clay & Copilot

Title:
    Stage 2 — Context Builder (Adapter-based /core/ Enrichment)

Purpose:
    - Accept a list of symbols from Stage 1.
    - Produce a list of enriched context dictionaries for Stage 3.
    - Enrich each context with:
        * Catalyst metadata (via CatalystAdapter)
        * Relative Strength (RS v2 with v1 fallback, via adapters)
        * Episodic Pivot (EP) metadata (via EPScanner adapter)
        * High-timeframe (HTF) trend (via HTFScanner adapter)
        * Daily trend alignment (via DailyTrendScanner adapter)
        * Market rotation / sector stats (via MarketStatsEngine adapter)

Design (v2.0.0):
    - All direct /core/ dependencies are now accessed via adapters in
      nexus_pipeline.adapters.*.
    - All lazy-init and "_get_*_safe" wrappers removed in favor of
      clean adapter APIs.
    - ContextBuilder is now a thin orchestrator: it calls adapters and
      assembles a unified context per symbol.
"""

from typing import List, Dict, Any, Optional

from nexus_pipeline.adapters.rs_v1_adapter import RSv1Adapter
from nexus_pipeline.adapters.rs_v2_adapter import RSv2Adapter
from nexus_pipeline.adapters.ep_adapter import EPAdapter
from nexus_pipeline.adapters.htf_adapter import HTFAdapter
from nexus_pipeline.adapters.daily_trend_adapter import DailyTrendAdapter
from nexus_pipeline.adapters.market_stats_adapter import MarketStatsAdapter
from nexus_pipeline.adapters.catalyst_adapter import CatalystAdapter


class ContextBuilder:
    """
    Stage 2 orchestrator.
    Responsible for building context objects for each symbol, using the
    adapter layer in nexus_pipeline.adapters.*.
    """

    def __init__(
        self,
        logger=None,
        catalyst_adapter: Optional[Any] = None,
        rs_engine_v2: Optional[Any] = None,
        rs_engine_v1: Optional[Any] = None,
        ep_scanner: Optional[Any] = None,
        htf_scanner: Optional[Any] = None,
        daily_trend_scanner: Optional[Any] = None,
        market_stats_client: Optional[Any] = None,
    ):
        """
        Initialize the ContextBuilder.

        Parameters:
            logger:
                Optional logger instance. Expected to support .info() and .error().

            catalyst_adapter:
                Optional CatalystAdapter instance.
                Expected API:
                    get_catalyst(symbol: str, **kwargs) -> Dict[str, Any]

            rs_engine_v2:
                Optional RS v2 engine (primary).
                Expected API:
                    get_rs(symbol: str) -> Dict[str, Any]

            rs_engine_v1:
                Optional RS v1 engine (fallback).
                Expected API:
                    get_rs(symbol: str) -> Dict[str, Any]

            ep_scanner:
                Optional Episodic Pivot scanner.
                Expected API:
                    get_episodic_pivot(symbol: str) -> Dict[str, Any]

            htf_scanner:
                Optional high-timeframe scanner.
                Expected API:
                    get_htf_trend(symbol: str) -> Dict[str, Any]

            daily_trend_scanner:
                Optional daily trend scanner.
                Expected API:
                    get_daily_trend(symbol: str) -> Dict[str, Any]

            market_stats_client:
                Optional market stats client.
                Expected API:
                    get_stats(symbol: str) -> Dict[str, Any]
        """
        self.logger = logger

        # Adapters (allow external injection for testing, else default)
        self.catalyst_adapter = catalyst_adapter or CatalystAdapter()
        self.rs_engine_v2 = rs_engine_v2 or RSv2Adapter()
        self.rs_engine_v1 = rs_engine_v1 or RSv1Adapter()
        self.ep_scanner = ep_scanner or EPAdapter()
        self.htf_scanner = htf_scanner or HTFAdapter()
        self.daily_trend_scanner = daily_trend_scanner or DailyTrendAdapter()
        self.market_stats_client = market_stats_client or MarketStatsAdapter()

        if self.logger:
            self.logger.info("[Stage 2] ContextBuilder v2.0.0 initialized with adapters")

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def build(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Build context objects for each symbol.

        Parameters:
            symbols:
                List of ticker symbols from Stage 1.

        Returns:
            List of context dictionaries, each enriched with:
                - Catalyst metadata
                - RS (v2 with v1 fallback)
                - Episodic Pivot (EP) metadata
                - HTF trend
                - Daily trend
                - Market rotation / sector stats
        """
        if self.logger:
            self.logger.info(f"[Stage 2] Building contexts for {len(symbols)} symbols")

        contexts: List[Dict[str, Any]] = []

        for symbol in symbols:
            context = self._build_single_context(symbol)
            contexts.append(context)

        if self.logger:
            self.logger.info(f"[Stage 2] Completed building {len(contexts)} contexts")

        return contexts

    # -------------------------------------------------------------------------
    # Per-symbol context builder (adapter-based)
    # -------------------------------------------------------------------------

    def _build_single_context(self, symbol: str) -> Dict[str, Any]:
        """
        Build a single context dictionary for a given symbol.

        v2.0.0 enriches with:
            - Catalyst metadata (via CatalystAdapter)
            - RS (v2 w/ v1 fallback, via adapters)
            - Episodic Pivot metadata (EP)
            - HTF trend
            - Daily trend
            - Market rotation / sector stats
        """
        context: Dict[str, Any] = {
            "symbol": symbol,
        }

        # ---------------------------------------------------------------------
        # RS enrichment (v2 primary, v1 fallback)
        # ---------------------------------------------------------------------
        rs_value = None
        rs_rank = None
        rs_source = None
        rs_raw = None

        # Try v2
        try:
            if self.rs_engine_v2 is not None:
                if self.logger:
                    self.logger.info(f"[Stage 2] Fetching RS v2 for {symbol}")
                rs_v2 = self.rs_engine_v2.get_rs(symbol) or {}
                if rs_v2.get("rs_rank") is not None:
                    rs_value = rs_v2.get("rs_value")
                    rs_rank = rs_v2.get("rs_rank")
                    rs_source = "v2"
                    rs_raw = rs_v2
        except Exception as e:
            if self.logger:
                self.logger.error(f"[Stage 2] Error fetching RS v2 for {symbol}: {e}")

        # Fallback to v1
        if rs_rank is None and self.rs_engine_v1 is not None:
            try:
                if self.logger:
                    self.logger.info(f"[Stage 2] Fetching RS v1 for {symbol}")
                rs_v1 = self.rs_engine_v1.get_rs(symbol) or {}
                if rs_v1.get("rs_rank") is not None:
                    rs_value = rs_v1.get("rs_value")
                    rs_rank = rs_v1.get("rs_rank")
                    rs_source = "v1"
                    rs_raw = rs_v1
            except Exception as e:
                if self.logger:
                    self.logger.error(f"[Stage 2] Error fetching RS v1 for {symbol}: {e}")

        context.update(
            {
                "rs_value": rs_value,
                "rs_rank": rs_rank,
                "rs_source": rs_source,
                "rs_raw": rs_raw,
            }
        )

        # ---------------------------------------------------------------------
        # Episodic Pivot enrichment
        # ---------------------------------------------------------------------
        ep_pivot_score = None
        ep_pivot_label = None
        ep_pivot_trigger = None
        ep_pivot_raw = None

        try:
            if self.ep_scanner is not None:
                if self.logger:
                    self.logger.info(
                        f"[Stage 2] Fetching EP (Episodic Pivot) data for {symbol}"
                    )
                ep_data = self.ep_scanner.get_episodic_pivot(symbol) or {}
                ep_pivot_score = ep_data.get("ep_pivot_score")
                ep_pivot_label = ep_data.get("ep_pivot_label")
                ep_pivot_trigger = ep_data.get("ep_pivot_trigger")
                ep_pivot_raw = ep_data.get("raw", ep_data)
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[Stage 2] Error fetching EP (Episodic Pivot) data for {symbol}: {e}"
                )

        context.update(
            {
                "ep_pivot_score": ep_pivot_score,
                "ep_pivot_label": ep_pivot_label,
                "ep_pivot_trigger": ep_pivot_trigger,
                "ep_pivot_raw": ep_pivot_raw,
            }
        )

        # ---------------------------------------------------------------------
        # HTF trend enrichment
        # ---------------------------------------------------------------------
        htf_trend = None
        htf_trend_score = None
        htf_raw = None

        try:
            if self.htf_scanner is not None:
                if self.logger:
                    self.logger.info(f"[Stage 2] Fetching HTF trend for {symbol}")
                htf_data = self.htf_scanner.get_htf_trend(symbol) or {}
                # Adapter is expected to already use these names:
                #   "htf_trend", "htf_trend_score", "htf_raw"
                htf_trend = htf_data.get("htf_trend")
                htf_trend_score = htf_data.get("htf_trend_score")
                htf_raw = htf_data.get("htf_raw", htf_data)
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[Stage 2] Error fetching HTF trend for {symbol}: {e}"
                )

        context.update(
            {
                "htf_trend": htf_trend,
                "htf_trend_score": htf_trend_score,
                "htf_raw": htf_raw,
            }
        )

        # ---------------------------------------------------------------------
        # Daily trend enrichment
        # ---------------------------------------------------------------------
        daily_trend = None
        daily_trend_score = None
        daily_trend_raw = None

        try:
            if self.daily_trend_scanner is not None:
                if self.logger:
                    self.logger.info(f"[Stage 2] Fetching daily trend for {symbol}")
                dt_data = self.daily_trend_scanner.get_daily_trend(symbol) or {}
                # Adapter is expected to expose:
                #   "daily_trend", "daily_trend_score", "daily_trend_raw"
                daily_trend = dt_data.get("daily_trend")
                daily_trend_score = dt_data.get("daily_trend_score")
                daily_trend_raw = dt_data.get("daily_trend_raw", dt_data)
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[Stage 2] Error fetching daily trend for {symbol}: {e}"
                )

        context.update(
            {
                "daily_trend": daily_trend,
                "daily_trend_score": daily_trend_score,
                "daily_trend_raw": daily_trend_raw,
            }
        )

        # ---------------------------------------------------------------------
        # Market stats / rotation enrichment
        # ---------------------------------------------------------------------
        market_rotation = None
        market_rotation_strength = None
        market_stats_raw = None

        try:
            if self.market_stats_client is not None:
                if self.logger:
                    self.logger.info(
                        f"[Stage 2] Fetching market stats / rotation for {symbol}"
                    )
                stats_data = self.market_stats_client.get_stats(symbol) or {}
                # Adapter is expected to expose:
                #   "market_rotation", "market_rotation_strength", "raw"
                market_rotation = stats_data.get("market_rotation")
                market_rotation_strength = stats_data.get("market_rotation_strength")
                market_stats_raw = stats_data.get("raw", stats_data)
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[Stage 2] Error fetching market stats for {symbol}: {e}"
                )

        context.update(
            {
                "market_rotation": market_rotation,
                "market_rotation_strength": market_rotation_strength,
                "market_stats_raw": market_stats_raw,
            }
        )

        # ---------------------------------------------------------------------
        # Catalyst enrichment (using adapter and other context hints where useful)
        # ---------------------------------------------------------------------
        catalyst_score = None
        catalyst_strength = None
        catalyst_tags = None
        catalyst_raw = None
        has_catalyst = None  # derived from adapter output if present

        try:
            if self.catalyst_adapter is not None:
                if self.logger:
                    self.logger.info(f"[Stage 2] Fetching catalyst data for {symbol}")

                # Optionally pass some enrichment hints if available
                gap_pct = None
                rvol = None
                rs_rank_for_catalyst = rs_rank

                # If EP raw contains gap/rvol, we could pull from there in the future.
                # For now, keep it simple and just pass rs_rank.
                cat_data = self.catalyst_adapter.get_catalyst(
                    symbol,
                    gap_pct=gap_pct,
                    rvol=rvol,
                    rs_rank=rs_rank_for_catalyst,
                    sector=None,
                ) or {}

                catalyst_score = cat_data.get("catalyst_score")
                catalyst_strength = cat_data.get("catalyst_strength")
                catalyst_tags = cat_data.get("catalyst_tags")
                catalyst_raw = cat_data.get("catalyst_raw", cat_data)

                if isinstance(catalyst_raw, dict):
                    has_catalyst = catalyst_raw.get("has_catalyst")
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[Stage 2] Error fetching catalyst data for {symbol}: {e}"
                )

        context.update(
            {
                "has_catalyst": has_catalyst,
                "catalyst_score": catalyst_score,
                "catalyst_strength": catalyst_strength,
                "catalyst_tags": catalyst_tags,
                "catalyst_raw": catalyst_raw,
            }
        )

        return self._sanitize(context)

    def _sanitize(self, obj):
        if isinstance(obj, dict):
            return {k: self._sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize(v) for v in obj]
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return obj