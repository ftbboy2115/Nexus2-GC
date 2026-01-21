"""
Historical Data Loader - Load historical market data for backtesting.

Provides:
- Gapper universe (stocks that gapped 5%+ on a given day)
- Intraday bars (1-min or 5-min candles)
- Local caching to reduce API calls
"""

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Optional, Any

from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter


logger = logging.getLogger(__name__)

# Cache directory for historical data
CACHE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "backtest_cache"


class HistoricalLoader:
    """Loads historical market data for backtesting."""
    
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.fmp = get_fmp_adapter()
    
    def get_gapper_universe(
        self,
        target_date: date,
        min_gap_percent: float = 5.0,
        min_price: float = 2.0,
        min_volume: int = 500_000,
    ) -> List[Dict[str, Any]]:
        """Get stocks that gapped up on a specific date.
        
        Args:
            target_date: The trading date to check
            min_gap_percent: Minimum gap % to qualify
            min_price: Minimum stock price
            min_volume: Minimum average volume
            
        Returns:
            List of dicts with symbol, gap_percent, price, volume
        """
        cache_key = f"gappers_{target_date.isoformat()}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached
        
        try:
            # Use FMP's stock screener or gainers endpoint
            # For backtesting, we'll use the gainers endpoint filtered by date
            # Note: FMP's historical gainers may not be available, 
            # so we may need to calculate from daily bars
            
            # Alternative approach: Get a broad universe and filter
            # This is a simplified version - production would need more sophisticated logic
            gainers = []
            
            # Try to get gainers for the date
            # FMP doesn't have historical gainers, so we simulate with current patterns
            logger.info(f"[HistoricalLoader] Getting gapper universe for {target_date}")
            
            # For now, return empty and cache it
            # In production, this would calculate gaps from daily bars
            self._save_cache(cache_key, gainers)
            return gainers
            
        except Exception as e:
            logger.error(f"[HistoricalLoader] Failed to get gapper universe: {e}")
            return []
    
    def get_daily_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """Get daily OHLCV bars for a symbol.
        
        Args:
            symbol: Stock symbol
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of bar dicts with date, open, high, low, close, volume
        """
        cache_key = f"daily_{symbol}_{start_date.isoformat()}_{end_date.isoformat()}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached
        
        try:
            # Calculate limit from date range
            days = (end_date - start_date).days + 1
            limit = min(days * 2, 500)  # Extra days for weekends/holidays
            
            bars = self.fmp.get_daily_bars(symbol, limit=limit)
            if not bars:
                return []
            
            # Filter to date range and convert to dicts
            result = []
            for bar in bars:
                bar_date = bar.timestamp.date() if hasattr(bar.timestamp, 'date') else bar.timestamp
                if isinstance(bar_date, str):
                    bar_date = datetime.fromisoformat(bar_date).date()
                
                if start_date <= bar_date <= end_date:
                    result.append({
                        "date": bar_date.isoformat(),
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                    })
            
            # Sort by date ascending
            result.sort(key=lambda x: x["date"])
            
            self._save_cache(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"[HistoricalLoader] Failed to get daily bars for {symbol}: {e}")
            return []
    
    def get_intraday_bars(
        self,
        symbol: str,
        target_date: date,
        interval: str = "5min",
    ) -> List[Dict[str, Any]]:
        """Get intraday bars for a symbol on a specific date.
        
        Args:
            symbol: Stock symbol
            target_date: The trading date
            interval: Bar interval (1min, 5min)
            
        Returns:
            List of bar dicts with timestamp, open, high, low, close, volume
        """
        cache_key = f"intraday_{symbol}_{target_date.isoformat()}_{interval}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached
        
        try:
            # FMP intraday endpoint
            bars = self.fmp.get_intraday_bars(symbol, interval=interval, limit=500)
            if not bars:
                return []
            
            # Filter to target date
            result = []
            for bar in bars:
                bar_dt = bar.timestamp if isinstance(bar.timestamp, datetime) else datetime.fromisoformat(str(bar.timestamp))
                
                if bar_dt.date() == target_date:
                    result.append({
                        "timestamp": bar_dt.isoformat(),
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                    })
            
            # Sort by timestamp ascending
            result.sort(key=lambda x: x["timestamp"])
            
            self._save_cache(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"[HistoricalLoader] Failed to get intraday bars for {symbol}: {e}")
            return []
    
    def _load_cache(self, key: str) -> Optional[Any]:
        """Load data from cache."""
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[HistoricalLoader] Cache load failed for {key}: {e}")
        return None
    
    def _save_cache(self, key: str, data: Any) -> None:
        """Save data to cache."""
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"[HistoricalLoader] Cache save failed for {key}: {e}")
    
    def clear_cache(self) -> int:
        """Clear all cached data. Returns number of files deleted."""
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except Exception:
                pass
        return count


# Singleton
_loader: Optional[HistoricalLoader] = None


def get_historical_loader() -> HistoricalLoader:
    """Get the singleton historical loader."""
    global _loader
    if _loader is None:
        _loader = HistoricalLoader()
    return _loader
