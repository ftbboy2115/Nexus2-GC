"""
Relative Strength Percentile Service

Calculates true RS percentile by ranking stock performance
against a universe of all tradeable stocks.

Per KK methodology:
- Focus on 1-month performance (emerging leaders)
- Top percentiles (97-99) indicate strongest stocks
- Cache results daily to avoid repeated API calls
- Persist cache to file for fast startup after server restart
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class RSData:
    """RS data for a single symbol."""
    symbol: str
    perf_1m: float  # 1-month % change
    perf_3m: float  # 3-month % change
    percentile: int  # 0-100 percentile ranking
    calculated_at: datetime = field(default_factory=datetime.now)


class RSService:
    """
    Relative Strength Percentile Service.
    
    Calculates true percentile rankings by comparing
    stock performance against a universe of stocks.
    
    Uses IBD-style weighting:
    - 40% 1-month performance (most recent)
    - 20% 2-month performance
    - 20% 3-month performance
    - 20% 6-month performance
    
    But simplified here to 1-month for speed, with 3-month as fallback.
    """
    
    # Cache duration - 24 hours to cover full trading day
    # (RS uses EOD data which only updates after market close)
    CACHE_HOURS = 24
    
    # Weighting (simplified: 60% 1M, 40% 3M)
    WEIGHT_1M = 0.60
    WEIGHT_3M = 0.40
    
    # File cache path (in domain/logs directory)
    CACHE_FILE = Path(__file__).parent.parent / "logs" / "rs_cache.json"
    
    def __init__(self):
        self._universe: Dict[str, RSData] = {}
        self._last_refresh: Optional[datetime] = None
        self._fmp = None  # Lazy load
        
        # Try to load from file cache on startup
        self._load_cache()
    
    @property
    def fmp(self):
        """Lazy load FMP adapter."""
        if self._fmp is None:
            from nexus2.adapters.market_data.fmp_adapter import FMPAdapter
            self._fmp = FMPAdapter()
        return self._fmp
    
    def _save_cache(self) -> None:
        """Save RS universe to file cache."""
        try:
            # Ensure directory exists
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            cache_data = {
                "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
                "universe": {
                    symbol: {
                        "symbol": data.symbol,
                        "perf_1m": data.perf_1m,
                        "perf_3m": data.perf_3m,
                        "percentile": data.percentile,
                        "calculated_at": data.calculated_at.isoformat(),
                    }
                    for symbol, data in self._universe.items()
                }
            }
            
            with open(self.CACHE_FILE, "w") as f:
                json.dump(cache_data, f)
            
            logger.info(f"[RS] Saved cache: {len(self._universe)} stocks to {self.CACHE_FILE}")
        except Exception as e:
            logger.warning(f"[RS] Failed to save cache: {e}")
    
    def _load_cache(self) -> bool:
        """Load RS universe from file cache. Returns True if loaded successfully."""
        try:
            if not self.CACHE_FILE.exists():
                logger.info("[RS] No cache file found")
                return False
            
            with open(self.CACHE_FILE, "r") as f:
                cache_data = json.load(f)
            
            # Parse last_refresh
            if cache_data.get("last_refresh"):
                self._last_refresh = datetime.fromisoformat(cache_data["last_refresh"])
                
                # Check if cache is still valid
                if datetime.now() - self._last_refresh > timedelta(hours=self.CACHE_HOURS):
                    logger.info("[RS] Cache file expired, will refresh")
                    return False
            else:
                return False
            
            # Load universe
            universe_data = cache_data.get("universe", {})
            self._universe = {}
            
            for symbol, data in universe_data.items():
                self._universe[symbol] = RSData(
                    symbol=data["symbol"],
                    perf_1m=data["perf_1m"],
                    perf_3m=data["perf_3m"],
                    percentile=data["percentile"],
                    calculated_at=datetime.fromisoformat(data["calculated_at"]),
                )
            
            logger.info(f"[RS] Loaded cache: {len(self._universe)} stocks from {self.CACHE_FILE}")
            return True
            
        except Exception as e:
            logger.warning(f"[RS] Failed to load cache: {e}")
            return False
    
    def get_rs_percentile(self, symbol: str) -> int:
        """
        Get RS percentile for a symbol (1-99).
        
        Returns cached value if available, otherwise calculates
        individual RS based on available data.
        """
        # Check if we need to refresh universe
        self._maybe_refresh_universe()
        
        # Check cache first
        symbol = symbol.upper()
        if symbol in self._universe:
            return self._universe[symbol].percentile
        
        # Symbol not in universe - calculate individual RS
        return self._calculate_individual_rs(symbol)
    
    def get_rs_data(self, symbol: str) -> Optional[RSData]:
        """Get full RS data for a symbol."""
        self._maybe_refresh_universe()
        return self._universe.get(symbol.upper())
    
    def refresh_universe(self, verbose: bool = False) -> int:
        """
        Refresh the RS universe.
        
        Fetches ~2000 tradeable stocks, calculates performance,
        and assigns percentile rankings.
        
        Returns number of stocks processed.
        """
        if verbose:
            logger.info("[RS] Starting universe refresh...")
        
        # Get universe of tradeable stocks
        stocks = self._get_stock_universe()
        
        if verbose:
            logger.info(f"[RS] Got {len(stocks)} stocks in universe")
        
        if not stocks:
            logger.warning("[RS] No stocks returned from universe query")
            return 0
        
        # Calculate performance for each stock (batch quotes for efficiency)
        performance_data: List[Tuple[str, float, float]] = []  # (symbol, perf_1m, perf_3m)
        
        # Process in batches of 100 (FMP batch limit)
        batch_size = 100
        for i in range(0, len(stocks), batch_size):
            batch = stocks[i:i + batch_size]
            symbols = [s["symbol"] for s in batch]
            
            # Get performance for batch
            batch_perf = self._get_batch_performance(symbols)
            performance_data.extend(batch_perf)
            
            if verbose and (i + batch_size) % 500 == 0:
                logger.info(f"[RS] Processed {min(i + batch_size, len(stocks))}/{len(stocks)}")
        
        if not performance_data:
            logger.warning("[RS] No performance data calculated")
            return 0
        
        # Calculate composite score (weighted 1M + 3M)
        scored_data = []
        for symbol, perf_1m, perf_3m in performance_data:
            if perf_1m is not None:
                composite = (perf_1m * self.WEIGHT_1M) + (perf_3m * self.WEIGHT_3M)
                scored_data.append((symbol, perf_1m, perf_3m, composite))
        
        # Sort by composite score (descending)
        scored_data.sort(key=lambda x: x[3], reverse=True)
        
        # Assign percentiles
        total = len(scored_data)
        self._universe.clear()
        
        for rank, (symbol, perf_1m, perf_3m, _) in enumerate(scored_data, 1):
            # Percentile: 99 = best, 1 = worst
            percentile = max(1, min(99, int(100 - (rank / total * 100))))
            
            self._universe[symbol] = RSData(
                symbol=symbol,
                perf_1m=perf_1m,
                perf_3m=perf_3m,
                percentile=percentile,
            )
        
        self._last_refresh = datetime.now()
        
        # Save to file cache for persistence across restarts
        self._save_cache()
        
        if verbose:
            logger.info(f"[RS] Universe refresh complete: {len(self._universe)} stocks ranked")
        
        return len(self._universe)
    
    def _maybe_refresh_universe(self) -> None:
        """Refresh universe if cache is stale."""
        if self._last_refresh is None:
            # First call - try a quick refresh
            try:
                self.refresh_universe()
            except Exception as e:
                logger.warning(f"[RS] Universe refresh failed: {e}")
        elif datetime.now() - self._last_refresh > timedelta(hours=self.CACHE_HOURS):
            # Cache expired
            try:
                self.refresh_universe()
            except Exception as e:
                logger.warning(f"[RS] Universe refresh failed, using stale cache: {e}")
    
    def _get_stock_universe(self) -> List[Dict]:
        """Get universe of tradeable stocks."""
        try:
            # Use FMP screener to get liquid stocks
            return self.fmp.screen_stocks(
                min_market_cap=100_000_000,  # $100M+ (smaller to catch biotechs)
                min_price=2.0,  # $2+ (include low-priced runners)
                min_volume=100_000,  # 100k+ daily volume
                limit=2000,  # Top 2000 stocks
            )
        except Exception as e:
            logger.error(f"[RS] Failed to get stock universe: {e}")
            return []
    
    def _get_batch_performance(self, symbols: List[str]) -> List[Tuple[str, float, float]]:
        """
        Get 1-month and 3-month performance for a batch of symbols.
        
        Returns list of (symbol, perf_1m, perf_3m) tuples.
        """
        result = []
        
        for symbol in symbols:
            try:
                bars = self.fmp.get_daily_bars(symbol, limit=63)  # ~3 months
                if not bars or len(bars) < 21:
                    continue
                
                current = float(bars[0].close)
                
                # 1-month (21 trading days)
                price_1m = float(bars[min(20, len(bars)-1)].close)
                perf_1m = ((current - price_1m) / price_1m) * 100 if price_1m > 0 else 0
                
                # 3-month (63 trading days)
                if len(bars) >= 63:
                    price_3m = float(bars[62].close)
                    perf_3m = ((current - price_3m) / price_3m) * 100 if price_3m > 0 else 0
                else:
                    perf_3m = perf_1m  # Use 1M if 3M not available
                
                result.append((symbol, perf_1m, perf_3m))
                
            except Exception as e:
                # Skip symbols that fail
                continue
        
        return result
    
    def _calculate_individual_rs(self, symbol: str) -> int:
        """
        Calculate RS percentile for a single symbol not in universe.
        
        Uses approximate ranking based on performance.
        """
        try:
            bars = self.fmp.get_daily_bars(symbol, limit=63)
            if not bars or len(bars) < 21:
                return 50  # Default if insufficient data
            
            current = float(bars[0].close)
            price_1m = float(bars[min(20, len(bars)-1)].close)
            perf_1m = ((current - price_1m) / price_1m) * 100 if price_1m > 0 else 0
            
            # Approximate percentile based on performance
            # Assume normal distribution: +20% = ~90th, +10% = ~75th, 0% = ~50th
            if perf_1m >= 30:
                return 98
            elif perf_1m >= 20:
                return 90
            elif perf_1m >= 10:
                return 75
            elif perf_1m >= 5:
                return 65
            elif perf_1m >= 0:
                return 50
            elif perf_1m >= -5:
                return 35
            elif perf_1m >= -10:
                return 25
            else:
                return 10
                
        except Exception as e:
            logger.warning(f"[RS] Failed to calculate individual RS for {symbol}: {e}")
            return 50  # Default


# Singleton instance
_rs_service: Optional[RSService] = None


def get_rs_service() -> RSService:
    """Get singleton RS service."""
    global _rs_service
    if _rs_service is None:
        _rs_service = RSService()
    return _rs_service
