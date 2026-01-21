"""
Reverse Split Service

Proactive tracking of recent reverse splits per Ross Cameron methodology.
Companies often pump stock after reverse splits before secondary offerings.

Score Boost: +2 for any stock with reverse split in last 45 days.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass
from threading import Lock

logger = logging.getLogger(__name__)

# Cache file location
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RSPLIT_CACHE_FILE = DATA_DIR / "reverse_splits_cache.json"

# ETFs that do frequent splits for share price management (not tradeable pattern)
ETF_BLOCKLIST = {
    # Leveraged/Inverse ETFs
    "SQQQ", "TQQQ", "UVXY", "SPXU", "SRTY", "QLD", "SSO", "DDM", "UDOW",
    "SDS", "REW", "EEV", "FXP", "GLL", "BZQ", "SSG", "YXI", "LTL", "UPW",
    "ETHD", "SETH", "USD", "NVDS", "TSLQ", "GDXD", "TSLZ", "NVDQ",
    # Yield/Income ETFs that do frequent splits
    "MSTY", "TSLY", "CONY", "AIYY", "MRNY", "ULTY", "XYZY", "YBIT", "OARK",
    "DIPS", "CRSH", "FIAT",
    # Sector ETFs
    "XLE", "XLU", "XLB", "XLY", "XLK", "WEAT",
}

# Foreign stock suffixes to exclude
FOREIGN_SUFFIXES = ("F", "Y", "D")


@dataclass
class SplitRecord:
    """Record of a reverse split."""
    symbol: str
    date: str  # YYYY-MM-DD
    ratio: str  # e.g., "1:10"
    numerator: int
    denominator: int


class ReverseSplitService:
    """
    Reverse split detection service with caching.
    
    Maintains a watchlist of recent reverse splits (last 45 days).
    Per Ross Cameron: "Some of the biggest winners in the last six weeks 
    were also stocks that had recently done reverse splits."
    
    Thesis: Companies do reverse splits → pump stock → squeeze → 
    potential secondary offering. Trade the initial squeeze.
    """
    
    LOOKBACK_DAYS = 45
    SCORE_BOOST = 2
    
    def __init__(self):
        self._cache: Dict[str, SplitRecord] = {}  # symbol -> SplitRecord
        self._last_refresh: Optional[datetime] = None
        self._lock = Lock()
        
        # Load from disk on init
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from disk."""
        try:
            if RSPLIT_CACHE_FILE.exists():
                with open(RSPLIT_CACHE_FILE, "r") as f:
                    data = json.load(f)
                    splits = data.get("splits", {})
                    for symbol, info in splits.items():
                        self._cache[symbol] = SplitRecord(
                            symbol=symbol,
                            date=info["date"],
                            ratio=info["ratio"],
                            numerator=info["numerator"],
                            denominator=info["denominator"],
                        )
                    refresh_str = data.get("last_refresh")
                    if refresh_str:
                        self._last_refresh = datetime.fromisoformat(refresh_str)
                    logger.info(f"[RSPLIT] Loaded {len(self._cache)} reverse splits from cache")
        except Exception as e:
            logger.error(f"[RSPLIT] Failed to load cache: {e}")
            self._cache = {}
    
    def _save_cache(self):
        """Persist cache to disk."""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            splits = {}
            for symbol, record in self._cache.items():
                splits[symbol] = {
                    "date": record.date,
                    "ratio": record.ratio,
                    "numerator": record.numerator,
                    "denominator": record.denominator,
                }
            data = {
                "splits": splits,
                "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            }
            with open(RSPLIT_CACHE_FILE, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"[RSPLIT] Saved {len(self._cache)} splits to cache")
        except Exception as e:
            logger.error(f"[RSPLIT] Failed to save cache: {e}")
    
    def _is_valid_symbol(self, symbol: str) -> bool:
        """Filter out ETFs, foreign stocks, and OTC symbols."""
        if not symbol:
            return False
        s = symbol.upper().strip()
        
        # Blocklist check
        if s in ETF_BLOCKLIST:
            return False
        
        # Foreign suffix check (ends with F, Y, or D and length > 4)
        if len(s) > 4 and s[-1] in FOREIGN_SUFFIXES:
            return False
        
        # Very long symbols are often OTC
        if len(s) > 5:
            return False
        
        return True
    
    def refresh(self, fmp=None) -> int:
        """
        Refresh reverse splits cache from FMP API.
        
        Args:
            fmp: FMP adapter instance (uses singleton if not provided)
            
        Returns:
            Number of reverse splits loaded
        """
        with self._lock:
            if fmp is None:
                from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
                fmp = get_fmp_adapter()
            
            try:
                # Get splits calendar (returns ~90 days of data)
                # FMP stable endpoint: https://financialmodelingprep.com/stable/splits-calendar
                # Note: FMP adapter's _get uses /api/v3 base, but splits-calendar is on /stable/
                import httpx
                url = f"https://financialmodelingprep.com/stable/splits-calendar?apikey={fmp.config.api_key}"
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(url)
                    resp.raise_for_status()
                    response = resp.json()
                
                if not response or not isinstance(response, list):
                    logger.warning("[RSPLIT] No data from splits-calendar API")
                    return 0
                
                today = datetime.now(timezone.utc).date()
                cutoff = today - timedelta(days=self.LOOKBACK_DAYS)
                
                # Clear old cache and rebuild
                self._cache = {}
                
                for split in response:
                    symbol = split.get("symbol", "").strip().upper()
                    date_str = split.get("date", "")
                    numerator = split.get("numerator", 1)
                    denominator = split.get("denominator", 1)
                    
                    # Skip if not a reverse split (must be denominator > numerator)
                    if denominator <= numerator:
                        continue
                    
                    # Skip invalid symbols
                    if not self._is_valid_symbol(symbol):
                        continue
                    
                    # Skip if outside lookback window
                    try:
                        split_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                        if split_date < cutoff:
                            continue
                    except (ValueError, TypeError):
                        continue
                    
                    # Store the split
                    ratio = f"{numerator}:{denominator}"
                    self._cache[symbol] = SplitRecord(
                        symbol=symbol,
                        date=date_str,
                        ratio=ratio,
                        numerator=numerator,
                        denominator=denominator,
                    )
                
                self._last_refresh = datetime.now(timezone.utc)
                self._save_cache()
                
                logger.info(f"[RSPLIT] Refreshed: {len(self._cache)} reverse splits in last {self.LOOKBACK_DAYS} days")
                return len(self._cache)
            except Exception as e:
                logger.error(f"[RSPLIT] Refresh failed: {e}")
                return 0
    
    def get_days_since_split(self, symbol: str) -> Optional[int]:
        """
        Get the number of days since a stock's reverse split.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Days since split, or None if not tracked
        """
        record = self._cache.get(symbol.upper())
        if not record:
            return None
        
        try:
            split_date = datetime.strptime(record.date, "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            days = (today - split_date).days
            return max(0, days)
        except (ValueError, TypeError):
            return None
    
    def is_recent_reverse_split(self, symbol: str) -> Optional[SplitRecord]:
        """
        Check if symbol had a recent reverse split.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            SplitRecord if recent split, else None
        """
        return self._cache.get(symbol.upper())
    
    def get_score_boost(self, symbol: str) -> int:
        """
        Get the quality score boost for reverse split status.
        
        Per Ross Cameron methodology:
        - Flat +2 boost for any stock with reverse split in lookback window
        
        This is a "reason to watch" (like Former Runner), not a primary catalyst.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Score boost (0 or 2)
        """
        if self.is_recent_reverse_split(symbol):
            return self.SCORE_BOOST
        return 0
    
    def get_all_tracked(self) -> List[Dict]:
        """
        Get all tracked reverse splits.
        
        Returns:
            List of {symbol, date, ratio, days_since} for all tracked splits
        """
        today = datetime.now(timezone.utc).date()
        result = []
        
        for symbol, record in self._cache.items():
            try:
                split_date = datetime.strptime(record.date, "%Y-%m-%d").date()
                days = (today - split_date).days
                result.append({
                    "symbol": symbol,
                    "date": record.date,
                    "ratio": record.ratio,
                    "days_since": days,
                    "score_boost": self.SCORE_BOOST,
                })
            except (ValueError, TypeError):
                continue
        
        # Sort by most recent first
        result.sort(key=lambda x: x["days_since"])
        return result
    
    def get_status(self) -> Dict:
        """Get service status."""
        return {
            "cache_size": len(self._cache),
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "lookback_days": self.LOOKBACK_DAYS,
            "score_boost": self.SCORE_BOOST,
        }


# Singleton
_rsplit_service: Optional[ReverseSplitService] = None


def get_reverse_split_service() -> ReverseSplitService:
    """Get singleton reverse split service."""
    global _rsplit_service
    if _rsplit_service is None:
        _rsplit_service = ReverseSplitService()
    return _rsplit_service
