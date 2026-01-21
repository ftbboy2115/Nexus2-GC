"""
IPO Service

Caching layer for IPO calendar data.
Detects recent IPOs for catalyst scoring per Ross Cameron methodology.

IPO Score Boost (tiered):
- Day 0-1: +3 (highest conviction)
- Day 2-7: +2
- Day 8-14: +1
- Day 15+: +0 (no longer "fresh IPO")
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, List
from threading import Lock

logger = logging.getLogger(__name__)

# Cache file location
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
IPO_CACHE_FILE = DATA_DIR / "ipo_cache.json"


class IPOService:
    """
    IPO detection service with caching.
    
    Maintains a cache of recent IPOs (last 30 days) for quick lookups.
    Cache is refreshed daily and persisted to disk.
    """
    
    def __init__(self):
        self._cache: Dict[str, str] = {}  # symbol -> ipo_date (YYYY-MM-DD)
        self._last_refresh: Optional[datetime] = None
        self._lock = Lock()
        
        # Load from disk on init
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from disk."""
        try:
            if IPO_CACHE_FILE.exists():
                with open(IPO_CACHE_FILE, "r") as f:
                    data = json.load(f)
                    self._cache = data.get("ipos", {})
                    refresh_str = data.get("last_refresh")
                    if refresh_str:
                        self._last_refresh = datetime.fromisoformat(refresh_str)
                    logger.info(f"[IPO] Loaded {len(self._cache)} IPOs from cache")
        except Exception as e:
            logger.error(f"[IPO] Failed to load cache: {e}")
            self._cache = {}
    
    def _save_cache(self):
        """Persist cache to disk."""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            data = {
                "ipos": self._cache,
                "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            }
            with open(IPO_CACHE_FILE, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"[IPO] Saved {len(self._cache)} IPOs to cache")
        except Exception as e:
            logger.error(f"[IPO] Failed to save cache: {e}")
    
    def refresh(self, fmp=None) -> int:
        """
        Refresh IPO cache from FMP API.
        
        Args:
            fmp: FMP adapter instance (uses singleton if not provided)
            
        Returns:
            Number of IPOs loaded
        """
        with self._lock:
            if fmp is None:
                from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
                fmp = get_fmp_adapter()
            
            try:
                # Get IPOs from last 30 days
                today = datetime.now(timezone.utc).date()
                from_date = (today - timedelta(days=30)).isoformat()
                to_date = today.isoformat()
                
                ipos = fmp.get_ipo_calendar(from_date=from_date, to_date=to_date)
                
                # Clear old cache and rebuild
                self._cache = {}
                for ipo in ipos:
                    symbol = ipo.get("symbol", "").strip()
                    ipo_date = ipo.get("date", "")
                    if symbol and ipo_date:
                        self._cache[symbol] = ipo_date
                
                self._last_refresh = datetime.now(timezone.utc)
                self._save_cache()
                
                logger.info(f"[IPO] Refreshed: {len(self._cache)} IPOs from {from_date} to {to_date}")
                return len(self._cache)
            except Exception as e:
                logger.error(f"[IPO] Refresh failed: {e}")
                return 0
    
    def get_days_since_ipo(self, symbol: str) -> Optional[int]:
        """
        Get the number of days since a stock's IPO.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Days since IPO, or None if not a recent IPO
        """
        ipo_date_str = self._cache.get(symbol.upper())
        if not ipo_date_str:
            return None
        
        try:
            ipo_date = datetime.strptime(ipo_date_str, "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            days = (today - ipo_date).days
            return max(0, days)  # No negative values
        except (ValueError, TypeError):
            return None
    
    def is_recent_ipo(self, symbol: str, max_days: int = 14) -> bool:
        """
        Check if symbol is a recent IPO (within max_days).
        
        Args:
            symbol: Stock symbol
            max_days: Maximum days since IPO to consider "recent"
            
        Returns:
            True if recently IPO'd
        """
        days = self.get_days_since_ipo(symbol)
        return days is not None and days <= max_days
    
    def get_ipo_score_boost(self, symbol: str) -> int:
        """
        Get the score boost for IPO status.
        
        Per Ross Cameron methodology:
        - Day 0-1: +3 (highest conviction)
        - Day 2-7: +2
        - Day 8-14: +1
        - Day 15+: +0
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Score boost (0-3)
        """
        days = self.get_days_since_ipo(symbol)
        if days is None:
            return 0
        
        if days <= 1:
            return 3
        elif days <= 7:
            return 2
        elif days <= 14:
            return 1
        else:
            return 0
    
    def get_recent_ipos(self, max_days: int = 14) -> List[Dict]:
        """
        Get all recent IPOs.
        
        Returns:
            List of {symbol, date, days_since} for recent IPOs
        """
        today = datetime.now(timezone.utc).date()
        recent = []
        
        for symbol, date_str in self._cache.items():
            try:
                ipo_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                days = (today - ipo_date).days
                if days <= max_days:
                    recent.append({
                        "symbol": symbol,
                        "date": date_str,
                        "days_since": days,
                        "score_boost": self.get_ipo_score_boost(symbol),
                    })
            except (ValueError, TypeError):
                continue
        
        # Sort by most recent first
        recent.sort(key=lambda x: x["days_since"])
        return recent
    
    def get_status(self) -> Dict:
        """Get service status."""
        return {
            "cache_size": len(self._cache),
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "recent_ipos_14d": len(self.get_recent_ipos(14)),
        }


# Singleton
_ipo_service: Optional[IPOService] = None


def get_ipo_service() -> IPOService:
    """Get singleton IPO service."""
    global _ipo_service
    if _ipo_service is None:
        _ipo_service = IPOService()
    return _ipo_service
