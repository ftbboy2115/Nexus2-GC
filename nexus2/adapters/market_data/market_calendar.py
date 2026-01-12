"""
Market Calendar Service

Uses Alpaca's clock API to determine market status, holidays, and early closes.
"""

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional
import logging

import httpx
import pytz

from nexus2 import config as app_config

logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")


@dataclass
class MarketStatus:
    """Current market status."""
    is_open: bool
    next_open: Optional[datetime] = None
    next_close: Optional[datetime] = None
    is_early_close: bool = False
    reason: str = ""  # "holiday", "early_close", "weekend", etc.


class MarketCalendar:
    """
    Market calendar service using Alpaca's clock API.
    
    Provides accurate market status including:
    - Regular hours (9:30 AM - 4:00 PM ET)
    - Holidays (New Year's, MLK, etc.)
    - Early closes (Black Friday, Christmas Eve, etc.)
    - Unscheduled closures
    """
    
    PAPER_URL = "https://paper-api.alpaca.markets"
    LIVE_URL = "https://api.alpaca.markets"
    
    def __init__(self, paper: bool = True):
        self.paper = paper
        self.base_url = self.PAPER_URL if paper else self.LIVE_URL
        
        # Load API credentials from config
        self.api_key = app_config.ALPACA_KEY or ""
        self.api_secret = app_config.ALPACA_SECRET or ""
        
        # Cache to avoid excessive API calls
        self._cache: Optional[MarketStatus] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 60  # Cache for 1 minute
        
        self._client = httpx.Client(timeout=10.0)
    
    def __del__(self):
        self._client.close()
    
    def _get_headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        }
    
    def _is_cache_valid(self) -> bool:
        if not self._cache or not self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl_seconds
    
    def get_market_status(self, force_refresh: bool = False) -> MarketStatus:
        """
        Get current market status from Alpaca.
        
        Returns cached result if available and not expired.
        """
        if not force_refresh and self._is_cache_valid():
            return self._cache
        
        try:
            response = self._client.get(
                f"{self.base_url}/v2/clock",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            data = response.json()
            
            is_open = data.get("is_open", False)
            next_open = data.get("next_open")
            next_close = data.get("next_close")
            
            # Parse timestamps
            if next_open:
                next_open = datetime.fromisoformat(next_open.replace("Z", "+00:00"))
            if next_close:
                next_close = datetime.fromisoformat(next_close.replace("Z", "+00:00"))
            
            # Detect early close (closes before 4:00 PM ET)
            is_early_close = False
            reason = ""
            
            if is_open and next_close:
                close_et = next_close.astimezone(ET)
                normal_close = time(16, 0)  # 4:00 PM
                if close_et.time() < normal_close:
                    is_early_close = True
                    reason = "early_close"
            
            if not is_open:
                now_et = datetime.now(ET)
                if now_et.weekday() >= 5:
                    reason = "weekend"
                else:
                    reason = "holiday_or_closed"
            
            status = MarketStatus(
                is_open=is_open,
                next_open=next_open,
                next_close=next_close,
                is_early_close=is_early_close,
                reason=reason,
            )
            
            # Update cache
            self._cache = status
            self._cache_time = datetime.now()
            
            return status
            
        except Exception as e:
            logger.warning(f"[MarketCalendar] Failed to get Alpaca clock: {e}")
            # Fallback to basic time-based check
            return self._fallback_check()
    
    def _fallback_check(self) -> MarketStatus:
        """Fallback market hours check if API fails."""
        now_et = datetime.now(ET)
        current_time = now_et.time()
        weekday = now_et.weekday()
        
        # Weekends
        if weekday >= 5:
            return MarketStatus(is_open=False, reason="weekend")
        
        # Check time (9:30 AM - 4:00 PM ET)
        market_open = time(9, 30)
        market_close = time(16, 0)
        
        is_open = market_open <= current_time <= market_close
        
        return MarketStatus(
            is_open=is_open,
            reason="api_fallback" if not is_open else "",
        )
    
    def is_market_open(self) -> bool:
        """Simple check: is the market currently open?"""
        return self.get_market_status().is_open
    
    def get_next_close(self) -> Optional[datetime]:
        """Get next market close time."""
        return self.get_market_status().next_close
    
    def get_next_open(self) -> Optional[datetime]:
        """Get next market open time."""
        return self.get_market_status().next_open
    
    def is_trading_day(self) -> bool:
        """
        Check if today is a trading day (even if market is currently closed).
        
        Returns True if market will open at some point today.
        """
        status = self.get_market_status()
        
        if status.is_open:
            return True
        
        # Check if next_open is today
        if status.next_open:
            now_et = datetime.now(ET)
            next_open_et = status.next_open.astimezone(ET)
            return now_et.date() == next_open_et.date()
        
        return False
    
    def is_extended_hours_active(self) -> bool:
        """
        Check if within extended trading hours (4 AM - 8 PM ET on market days).
        
        Used by Warrior Trading strategy which can trade pre-market and post-market:
        - Pre-market: 4:00 AM - 9:30 AM (gap scanning, early entries)
        - Regular: 9:30 AM - 4:00 PM
        - Post-market: 4:00 PM - 8:00 PM (position management, exits)
        
        Returns False on weekends/holidays.
        """
        now_et = datetime.now(ET)
        current_time = now_et.time()
        weekday = now_et.weekday()
        
        # No trading on weekends
        if weekday >= 5:
            return False
        
        # Check time first (4:00 AM - 8:00 PM ET)
        extended_open = time(4, 0)   # 4:00 AM
        extended_close = time(20, 0)  # 8:00 PM
        
        if not (extended_open <= current_time <= extended_close):
            return False
        
        # During extended hours on a weekday - check if it's a trading day
        # (handles holidays where market is closed entirely)
        try:
            status = self.get_market_status()
            # If market is open or was open today, it's a trading day
            if status.is_open:
                return True
            # If next_open is tomorrow or later, today WAS a trading day (post-market)
            if status.next_open:
                next_open_et = status.next_open.astimezone(ET)
                if next_open_et.date() != now_et.date():
                    return True  # Post-market of a trading day
            # If API says not a trading day, trust it (holiday)
            return False
        except Exception:
            # Fallback: assume weekdays are trading days
            return True


# Singleton instance
_market_calendar: Optional[MarketCalendar] = None


def get_market_calendar(paper: bool = True) -> MarketCalendar:
    """Get singleton market calendar instance."""
    global _market_calendar
    if _market_calendar is None:
        _market_calendar = MarketCalendar(paper=paper)
    return _market_calendar
