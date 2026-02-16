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
from nexus2.utils.time_utils import now_et

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
        elapsed = (now_et() - self._cache_time).total_seconds()
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
                current_et = datetime.now(ET)
                current_time = current_et.time()
                if current_et.weekday() >= 5:
                    reason = "weekend"
                elif next_open:
                    # Check if next_open is NOT today — that means today is a holiday
                    next_open_et = next_open.astimezone(ET)
                    if next_open_et.date() > current_et.date():
                        holiday_name = self._get_holiday_name(current_et.date())
                        if current_time >= time(16, 0):
                            reason = "post_market"
                        elif holiday_name:
                            reason = f"holiday: {holiday_name}"
                        else:
                            reason = "holiday"
                    else:
                        # next_open is today — we're in pre-market or post-market
                        if current_time < time(9, 30):
                            reason = "pre_market"
                        else:
                            reason = "post_market"
                elif current_time >= time(16, 0):
                    reason = "post_market"
                elif current_time < time(9, 30):
                    reason = "pre_market"
                else:
                    reason = "holiday"
            
            status = MarketStatus(
                is_open=is_open,
                next_open=next_open,
                next_close=next_close,
                is_early_close=is_early_close,
                reason=reason,
            )
            
            # Update cache
            self._cache = status
            self._cache_time = now_et()
            
            return status
            
        except Exception as e:
            logger.warning(f"[MarketCalendar] Failed to get Alpaca clock: {e}")
            # Fallback to basic time-based check
            return self._fallback_check()
    
    def _fallback_check(self) -> MarketStatus:
        """Fallback market hours check if API fails."""
        current_et = datetime.now(ET)
        current_time = current_et.time()
        weekday = current_et.weekday()
        
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
    
    @staticmethod
    def _get_holiday_name(d) -> str:
        """Identify US market holiday by date. Returns name or empty string."""
        from datetime import date as date_type, timedelta
        month, day, weekday = d.month, d.day, d.weekday()
        
        # Fixed-date holidays with NYSE observed day rules:
        # If holiday falls on Saturday → observed Friday
        # If holiday falls on Sunday → observed Monday
        def _is_observed(m, dd):
            """Check if date d is the actual or observed date for month m, day dd."""
            actual = date_type(d.year, m, dd)
            wd = actual.weekday()
            if wd == 5:  # Saturday → observed Friday
                return d == actual - timedelta(days=1)
            elif wd == 6:  # Sunday → observed Monday
                return d == actual + timedelta(days=1)
            else:
                return d == actual
        
        if _is_observed(1, 1): return "New Year's Day"
        if _is_observed(6, 19): return "Juneteenth"
        if _is_observed(7, 4): return "Independence Day"
        if _is_observed(12, 25): return "Christmas Day"
        # Monday holidays (observed)
        if weekday == 0:  # Monday
            if month == 1 and 15 <= day <= 21: return "MLK Jr. Day"
            if month == 2 and 15 <= day <= 21: return "Presidents' Day"
            if month == 5 and day >= 25: return "Memorial Day"
            if month == 9 and day <= 7: return "Labor Day"
        # Thanksgiving (4th Thursday of November)
        if month == 11 and weekday == 3 and 22 <= day <= 28:
            return "Thanksgiving Day"
        # Good Friday (2 days before Easter Sunday)
        # Anonymous Gregorian Easter algorithm
        try:
            year = d.year
            a = year % 19
            b, c = divmod(year, 100)
            d2, e = divmod(b, 4)
            f = (b + 8) // 25
            g = (b - f + 1) // 3
            h = (19 * a + b - d2 - g + 15) % 30
            i, k = divmod(c, 4)
            l = (32 + 2 * e + 2 * i - h - k) % 7
            m = (a + 11 * h + 22 * l) // 451
            month_e = (h + l - 7 * m + 114) // 31
            day_e = ((h + l - 7 * m + 114) % 31) + 1
            easter = date_type(year, month_e, day_e)
            good_friday = easter - timedelta(days=2)
            if d == good_friday:
                return "Good Friday"
        except Exception:
            pass
        # Unrecognized holiday — log so we can add it
        logger.warning(f"[MarketCalendar] Market closed on {d} but holiday not recognized — update _get_holiday_name()")
        return ""
    
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
            current_et = datetime.now(ET)
            next_open_et = status.next_open.astimezone(ET)
            return current_et.date() == next_open_et.date()
        
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
        current_et = datetime.now(ET)
        current_time = current_et.time()
        weekday = current_et.weekday()
        
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
            # If market is open, it's a trading day
            if status.is_open:
                return True
            # Check next_open to determine if we're pre-market, post-market, or holiday
            if status.next_open:
                next_open_et = status.next_open.astimezone(ET)
                # Pre-market: next_open is TODAY = trading day, in pre-market window
                if next_open_et.date() == current_et.date():
                    return True  # Pre-market of a trading day
                # Post-market check: need to verify TODAY had a market session
                # On holidays, next_open is tomorrow but there was no trading today
                if next_open_et.date() > current_et.date():
                    # Check if we're actually in post-market (after 4 PM)
                    if current_time >= time(16, 0):  # After regular close
                        # Use the new reason field to distinguish post-market from holiday
                        if status.reason == "post_market":
                            return True  # Post-market of a trading day
                        elif status.reason == "holiday":
                            # Holiday - no post-market because there was no market
                            logger.debug(f"[MarketCalendar] Holiday detected - no extended hours")
                            return False
            # If API says not a trading day (e.g., holiday), trust it
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
