"""
FMP (Financial Modeling Prep) Market Data Adapter

Provides market data from FMP API.
Ported from: core/scan_ep.py
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

import httpx
import threading

from nexus2.adapters.market_data.protocol import (
    MarketDataProvider,
    OHLCV,
    Quote,
    StockInfo,
)

# Import centralized config (auto-loads .env)
from nexus2 import config as app_config


@dataclass
class FMPConfig:
    """Configuration for FMP API."""
    api_key: str
    base_url: str = "https://financialmodelingprep.com/api/v3"
    timeout: float = 10.0
    rate_limit_per_minute: int = 300  # FMP default is 300/min for paid plans


class RateLimitTracker:
    """Tracks API calls per minute."""
    
    def __init__(self, limit_per_minute: int = 300):
        self.limit_per_minute = limit_per_minute
        self._calls: List[datetime] = []
        self._lock = threading.Lock()  # Thread-safe access to rate limiter
    
    def _prune_old_calls(self):
        """Remove calls older than 60 seconds."""
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - 60
        self._calls = [c for c in self._calls if c.timestamp() > cutoff]
    
    def record_call(self):
        """Record an API call."""
        self._prune_old_calls()
        self._calls.append(datetime.now(timezone.utc))
    
    @property
    def calls_this_minute(self) -> int:
        """Count calls in the last minute."""
        self._prune_old_calls()  # Prune on read too
        return len(self._calls)
    
    @property
    def remaining(self) -> int:
        """Remaining calls before hitting limit."""
        return max(0, self.limit_per_minute - self.calls_this_minute)
    
    @property
    def usage_percent(self) -> float:
        """Usage as percentage."""
        return (self.calls_this_minute / self.limit_per_minute) * 100
    
    def get_stats(self) -> Dict:
        """Get rate limit stats."""
        return {
            "calls_this_minute": self.calls_this_minute,
            "limit_per_minute": self.limit_per_minute,
            "remaining": self.remaining,
            "usage_percent": round(self.usage_percent, 1),
        }
    
    def mark_exhausted(self):
        """Mark rate limit as exhausted (e.g., when we get a 429 from FMP).
        
        This syncs our local counter with FMP's server-side state, which can
        be ahead of ours after a server restart.
        """
        now = datetime.now(timezone.utc)
        # Fill the calls list to capacity to reflect that we're at the limit
        self._calls = [now] * self.limit_per_minute
        print(f"[FMP] Rate limiter synced to exhausted state (429 received)")


class FMPAdapter:
    """
    FMP Market Data Adapter.
    
    Provides:
    - Stock screening
    - Daily OHLCV data
    - Real-time quotes
    - Stock information
    - Rate limit tracking
    """
    
    def __init__(self, config: Optional[FMPConfig] = None):
        if config:
            self.config = config
        else:
            # Load from centralized config (which loads .env)
            self.config = FMPConfig(api_key=app_config.FMP_API_KEY)
        
        self._client = httpx.Client(timeout=self.config.timeout)
        self.rate_limiter = RateLimitTracker(self.config.rate_limit_per_minute)
        self._shutdown = False  # Flag for graceful shutdown
        self._etf_cache: Optional[set] = None  # Session-level cache for ETF symbols
    
    def __del__(self):
        if hasattr(self, '_client'):
            self._client.close()
    
    def get_rate_stats(self) -> Dict:
        """Get current rate limit stats."""
        return self.rate_limiter.get_stats()
    
    def _get(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make GET request to FMP API with rate limiting."""
        import time
        
        try:
            # Acquire lock to prevent race conditions - only one thread can check+call at a time
            with self.rate_limiter._lock:
                # Throttle: wait if approaching limit (< 10 remaining)
                while self.rate_limiter.remaining < 10 and not self._shutdown:
                    wait_time = 5  # Total wait 5 seconds
                    print(f"[FMP] Rate limit approaching ({self.rate_limiter.remaining} remaining), waiting {wait_time}s...")
                    # Release lock while waiting so other threads don't block
                    self.rate_limiter._lock.release()
                    try:
                        for _ in range(10):  # 10 x 0.5s = 5s total
                            if self._shutdown:
                                print("[FMP] Shutdown detected, aborting request")
                                return None
                            time.sleep(0.5)
                    finally:
                        self.rate_limiter._lock.acquire()
                
                # Hard stop if at limit
                if self.rate_limiter.remaining <= 0 and not self._shutdown:
                    print(f"[FMP] Rate limit reached! Waiting 60s...")
                    self.rate_limiter._lock.release()
                    try:
                        for _ in range(120):  # 120 x 0.5s = 60s total
                            if self._shutdown:
                                print("[FMP] Shutdown detected, aborting request")
                                return None
                            time.sleep(0.5)
                    finally:
                        self.rate_limiter._lock.acquire()
                
                if self._shutdown:
                    return None
                
                url = f"{self.config.base_url}/{endpoint}"
                params = params or {}
                params["apikey"] = self.config.api_key
                
                # Record call BEFORE making it (under lock)
                self.rate_limiter.record_call()
            
            # Make the HTTP call OUTSIDE the lock (I/O bound, don't block others)
            response = self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except KeyboardInterrupt:
            print("[FMP] Keyboard interrupt received, aborting")
            self._shutdown = True
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # 429 Too Many Requests - sync our counter with FMP's state
                self.rate_limiter.mark_exhausted()
                print(f"[FMP] 429 received, waiting 60s before retry...")
                # Wait for rate limit to reset
                for _ in range(120):  # 120 x 0.5s = 60s
                    if self._shutdown:
                        return None
                    time.sleep(0.5)
            print(f"[FMP] Request error: {e}")
            return None
        except Exception as e:
            print(f"[FMP] Request error: {e}")
            return None
    
    # =========================================================================
    # MarketDataProvider Implementation
    # =========================================================================
    
    def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get real-time quote for a symbol.
        
        During pre-market/after-hours, uses aftermarket quote endpoint
        which returns actual extended hours prices. During regular market
        hours, skips premarket endpoint to save API calls.
        """
        # Only try premarket endpoint during extended hours (saves ~50% API calls)
        from nexus2.utils.time_utils import is_market_hours
        if not is_market_hours():
            pm_quote = self.get_premarket_quote(symbol)
            if pm_quote:
                return pm_quote
        
        # Fall back to regular quote
        data = self._get(f"quote/{symbol}")
        if not data or len(data) == 0:
            return None
        
        q = data[0]
        return Quote(
            symbol=symbol,
            price=Decimal(str(q.get("price", 0))),
            change=Decimal(str(q.get("change", 0))),
            change_percent=Decimal(str(q.get("changesPercentage", 0))),
            volume=int(q.get("volume", 0)),
            timestamp=datetime.now(timezone.utc),
            day_low=Decimal(str(q.get("dayLow", 0))) if q.get("dayLow") else None,
            day_high=Decimal(str(q.get("dayHigh", 0))) if q.get("dayHigh") else None,
        )
    
    def get_premarket_quote(self, symbol: str) -> Optional[Quote]:
        """Get pre-market/after-hours quote for a symbol.
        
        Uses FMP's aftermarket quote endpoint which has actual extended hours prices.
        Returns None if no pre-market data available.
        """
        data = self._get(f"pre-post-market-trade/{symbol}")
        if not data or len(data) == 0:
            return None
        
        q = data[0]
        price = q.get("price", 0)
        if not price or price == 0:
            return None
        
        return Quote(
            symbol=symbol,
            price=Decimal(str(price)),
            change=Decimal(str(q.get("change", 0))),
            change_percent=Decimal(str(q.get("changesPercentage", 0))),
            volume=int(q.get("volume", 0)),
            timestamp=datetime.now(timezone.utc),
        )
    
    def get_quotes_batch(self, symbols: List[str]) -> Dict[str, Quote]:
        """Get quotes for multiple symbols (max 100 per batch)."""
        quotes = {}
        
        # FMP supports comma-separated symbols
        chunk_size = 100
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i + chunk_size]
            tickers = ",".join(chunk)
            
            data = self._get(f"quote/{tickers}")
            if not data:
                continue
            
            for q in data:
                sym = q.get("symbol")
                if sym:
                    quotes[sym] = Quote(
                        symbol=sym,
                        price=Decimal(str(q.get("price", 0))),
                        change=Decimal(str(q.get("change", 0))),
                        change_percent=Decimal(str(q.get("changesPercentage", 0))),
                        volume=int(q.get("volume", 0)),
                        timestamp=datetime.now(timezone.utc),
                    )
        
        return quotes
    
    def get_daily_bars(
        self, 
        symbol: str, 
        limit: int = 60,
        from_date: Optional[str] = None,  # YYYY-MM-DD format
        to_date: Optional[str] = None,    # YYYY-MM-DD format
    ) -> Optional[List[OHLCV]]:
        """
        Get daily OHLCV bars.
        
        Args:
            symbol: Stock symbol
            limit: Number of bars to return (ignored if from_date/to_date provided)
            from_date: Start date in YYYY-MM-DD format (for historical queries)
            to_date: End date in YYYY-MM-DD format (for historical queries)
        """
        # Build params based on whether date range is provided
        if from_date and to_date:
            params = {"from": from_date, "to": to_date}
        else:
            params = {"timeseries": str(limit)}
        
        data = self._get(
            f"historical-price-full/{symbol}",
            params=params
        )
        
        if not data or "historical" not in data:
            return None
        
        historical = data.get("historical")
        if not historical or not isinstance(historical, list):
            return None
        
        bars = []
        for bar in reversed(historical):  # Oldest first
            try:
                bars.append(OHLCV(
                    timestamp=datetime.strptime(bar["date"], "%Y-%m-%d"),
                    open=Decimal(str(bar.get("open", 0))),
                    high=Decimal(str(bar.get("high", 0))),
                    low=Decimal(str(bar.get("low", 0))),
                    close=Decimal(str(bar.get("close", 0))),
                    volume=int(bar.get("volume", 0)),
                ))
            except (KeyError, ValueError, TypeError):
                continue  # Skip malformed bars
        
        return bars if len(bars) >= 10 else None  # Require minimum bars (lowered for date ranges)
    
    def get_intraday_bars(
        self,
        symbol: str,
        timeframe: str = "5min",
        date: Optional[str] = None,
    ) -> Optional[List[OHLCV]]:
        """
        Get intraday OHLCV bars.
        
        Args:
            symbol: Stock symbol
            timeframe: Bar size - "1min", "5min", "15min", "30min", "1hour"
            date: Date in YYYY-MM-DD format (defaults to today)
            
        Returns:
            List of OHLCV bars (oldest first), or None if unavailable.
            During market hours, returns bars from market open to current time.
        """
        # Default to today's date
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # FMP uses /stable/ endpoint for intraday
        # Note: The endpoint format is historical-chart/{timeframe}
        data = self._get(
            f"historical-chart/{timeframe}/{symbol}",
            params={
                "from": date,
                "to": date,
            }
        )
        
        if not data or not isinstance(data, list):
            return None
        
        if len(data) == 0:
            return None
        
        bars = []
        for bar in reversed(data):  # Oldest first (FMP returns newest first)
            try:
                # Parse datetime from FMP format: "2025-01-01 09:30:00"
                dt_str = bar.get("date", "")
                if dt_str:
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                else:
                    continue
                
                bars.append(OHLCV(
                    timestamp=dt,
                    open=Decimal(str(bar.get("open", 0))),
                    high=Decimal(str(bar.get("high", 0))),
                    low=Decimal(str(bar.get("low", 0))),
                    close=Decimal(str(bar.get("close", 0))),
                    volume=int(bar.get("volume", 0)),
                ))
            except (KeyError, ValueError, TypeError) as e:
                print(f"[FMP] Intraday bar parse error: {e}")
                continue
        
        return bars if bars else None
    
    def get_opening_range(
        self,
        symbol: str,
        timeframe_minutes: int = 5,
        date: Optional[str] = None,
    ) -> Optional[tuple[Decimal, Decimal]]:
        """
        Get the opening range (high, low) for the first N minutes of trading.
        
        This is specifically for EP tactical stop calculation.
        
        Args:
            symbol: Stock symbol
            timeframe_minutes: Opening range timeframe (1, 5, 15, 30)
            date: Date in YYYY-MM-DD format (defaults to today)
            
        Returns:
            (opening_range_high, opening_range_low) or None if unavailable
        """
        # Map minutes to FMP timeframe strings
        tf_map = {
            1: "1min",
            5: "5min",
            15: "15min",
            30: "30min",
        }
        tf = tf_map.get(timeframe_minutes, "5min")
        
        bars = self.get_intraday_bars(symbol, timeframe=tf, date=date)
        
        if not bars or len(bars) == 0:
            return None
        
        # Get the first bar (which covers the opening range)
        first_bar = bars[0]
        
        return (first_bar.high, first_bar.low)
    
    def get_premarket_high(
        self,
        symbol: str,
        date: Optional[str] = None,
    ) -> Optional[Decimal]:
        """
        Get the pre-market high (max high from 4:00 AM - 9:29 AM ET).
        
        This is the TRUE pre-market high for PMH breakout detection.
        Unlike day_high from quotes, this doesn't update during regular session.
        
        Args:
            symbol: Stock symbol
            date: Date in YYYY-MM-DD format (defaults to today)
            
        Returns:
            Pre-market high price, or None if no pre-market data
        """
        from datetime import time as dt_time
        import pytz
        
        # Get 30-min bars for today (less API overhead, still accurate)
        bars = self.get_intraday_bars(symbol, timeframe="30min", date=date)
        
        if not bars or len(bars) == 0:
            return None
        
        # Filter bars to pre-market only (before 9:30 AM ET)
        # FMP timestamps are already in ET
        market_open = dt_time(9, 30)
        
        premarket_highs = []
        for bar in bars:
            bar_time = bar.timestamp.time()
            if bar_time < market_open:
                premarket_highs.append(bar.high)
        
        if not premarket_highs:
            # No pre-market bars - stock might not trade pre-market
            # Fall back to first regular bar's open as approximation
            return bars[0].open if bars else None
        
        # Return max high from pre-market bars
        return max(premarket_highs)

    
    def get_stock_info(self, symbol: str) -> Optional[StockInfo]:
        """Get basic stock information."""
        data = self._get(f"profile/{symbol}")
        if not data or len(data) == 0:
            return None
        
        p = data[0]
        return StockInfo(
            symbol=symbol,
            name=p.get("companyName", ""),
            exchange=p.get("exchangeShortName", ""),
            market_cap=Decimal(str(p.get("mktCap", 0))),
            float_shares=None,  # FMP doesn't provide this directly
            avg_volume_20d=int(p.get("volAvg", 0)),
            sector=p.get("sector"),
            industry=p.get("industry"),
        )
    
    def get_country(self, symbol: str) -> Optional[str]:
        """
        Get the country where a company is headquartered.
        
        Uses FMP's profile endpoint.
        
        Returns:
            Country name (e.g., "CN", "US", "HK") or None if unavailable
        """
        data = self._get(f"profile/{symbol}")
        if not data or len(data) == 0:
            return None
        
        return data[0].get("country")
    
    def get_prev_close(self, symbol: str) -> Optional[Decimal]:
        """Get previous day's closing price."""
        bars = self.get_daily_bars(symbol, limit=5)
        if not bars or len(bars) < 2:
            return None
        return bars[-2].close  # Second to last bar
    
    def get_atr(self, symbol: str, period: int = 14) -> Optional[Decimal]:
        """Calculate Average True Range."""
        bars = self.get_daily_bars(symbol, limit=period + 10)
        if not bars or len(bars) < period + 1:
            return None
        
        tr_values = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i - 1].close
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
        
        # Simple average of last 'period' TR values
        recent_tr = tr_values[-period:]
        return sum(recent_tr) / len(recent_tr)
    
    def get_sma(self, symbol: str, period: int) -> Optional[Decimal]:
        """Get Simple Moving Average."""
        bars = self.get_daily_bars(symbol, limit=period + 5)
        if not bars or len(bars) < period:
            return None
        
        closes = [b.close for b in bars[-period:]]
        return sum(closes) / len(closes)
    
    def get_ema(self, symbol: str, period: int) -> Optional[Decimal]:
        """Get Exponential Moving Average."""
        bars = self.get_daily_bars(symbol, limit=period * 2)
        if not bars or len(bars) < period:
            return None
        
        multiplier = Decimal(2) / (Decimal(period) + 1)
        ema = bars[0].close  # Start with first close
        
        for bar in bars[1:]:
            ema = (bar.close * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    # =========================================================================
    # FMP-Specific Methods
    # =========================================================================
    
    def screen_stocks(
        self,
        min_market_cap: int = 50_000_000,
        min_price: float = 4.0,
        min_volume: int = 50_000,
        exchanges: List[str] = None,
        limit: int = 2000,
    ) -> List[Dict]:
        """
        Screen stocks using FMP screener.
        
        Returns list of candidate dicts with symbol, sector, industry.
        """
        exchanges = exchanges or ["NASDAQ", "NYSE", "AMEX"]
        
        params = {
            "marketCapMoreThan": str(min_market_cap),
            "priceMoreThan": str(min_price),
            "volumeMoreThan": str(min_volume),
            "isEtf": "false",
            "exchange": ",".join(exchanges),
            "limit": str(limit),
        }
        
        data = self._get("stock-screener", params)
        if not data:
            return []
        
        candidates = []
        for item in data:
            candidates.append({
                "symbol": item.get("symbol", "").replace(".", "-"),
                "sector": item.get("sector", "Unknown"),
                "industry": item.get("industry", "Unknown"),
            })
        
        return candidates
    
    def filter_by_change(
        self,
        symbols: List[str],
        min_change_pct: float = 3.0,
    ) -> List[str]:
        """Filter symbols by minimum change percentage."""
        quotes = self.get_quotes_batch(symbols)
        
        passing = []
        for sym, quote in quotes.items():
            if quote.change_percent >= Decimal(str(min_change_pct)):
                passing.append(sym)
        
        return passing
    
    def get_gainers(self) -> List[Dict]:
        """
        Get top gainers for today (real-time, refreshed every ~1 min).
        
        Much better than stock-screener for EP scanning.
        
        Returns list of dicts with:
            symbol, name, change, price, changesPercentage
        """
        data = self._get("stock_market/gainers")
        if not data:
            return []
        
        gainers = []
        for item in data:
            gainers.append({
                "symbol": item.get("symbol", ""),
                "name": item.get("name", ""),
                "price": Decimal(str(item.get("price", 0))),
                "change": Decimal(str(item.get("change", 0))),
                "change_percent": Decimal(str(item.get("changesPercentage", 0))),
            })
        
        return gainers
    
    def get_premarket_gainers(self, min_change_pct: float = 4.0) -> List[Dict]:
        """
        Get pre-market gainers using after-hours trade data.
        
        This works before market open when stock_market/gainers is empty.
        Uses pre_post_market/trade endpoint.
        
        Args:
            min_change_pct: Minimum % change to include
            
        Returns:
            List of gainers sorted by change_percent descending
        """
        # FMP pre/post market quotes endpoint
        data = self._get("pre_post_market/gainers")
        if not data:
            # Fallback: try to get active pre-market movers
            return []
        
        gainers = []
        for item in data:
            change_pct = float(item.get("changesPercentage", 0))
            if change_pct >= min_change_pct:
                gainers.append({
                    "symbol": item.get("symbol", ""),
                    "name": item.get("name", ""),
                    "price": Decimal(str(item.get("price", 0))),
                    "change": Decimal(str(item.get("change", 0))),
                    "change_percent": Decimal(str(item.get("changesPercentage", 0))),
                })
        
        # Sort by change percent descending
        gainers.sort(key=lambda x: x["change_percent"], reverse=True)
        return gainers
    
    def get_actives(self) -> List[Dict]:
        """
        Get most active stocks by volume (real-time).
        
        Returns list of dicts with:
            symbol, name, change, price, changesPercentage
        """
        data = self._get("stock_market/actives")
        if not data:
            return []
        
        actives = []
        for item in data:
            actives.append({
                "symbol": item.get("symbol", ""),
                "name": item.get("name", ""),
                "price": Decimal(str(item.get("price", 0))),
                "change": Decimal(str(item.get("change", 0))),
                "change_percent": Decimal(str(item.get("changesPercentage", 0))),
            })
        
        return actives
    
    def get_etf_symbols(self) -> set:
        """
        Get set of all ETF symbols for filtering.
        
        Cached for the session (one API call per adapter lifetime).
        """
        # Return cached result if available
        if self._etf_cache is not None:
            return self._etf_cache
        
        data = self._get("etf/list")
        if not data:
            return set()
        
        self._etf_cache = {item.get("symbol", "") for item in data if item.get("symbol")}
        return self._etf_cache
    
    def is_etf(self, symbol: str, etf_set: set = None) -> bool:
        """
        Check if symbol is an ETF.
        
        Args:
            symbol: Symbol to check
            etf_set: Pre-fetched ETF set (for efficiency in loops)
        """
        if etf_set is None:
            etf_set = self.get_etf_symbols()
        return symbol in etf_set
    
    def get_earnings_calendar(
        self,
        symbol: str,
        days_back: int = 7,
        days_forward: int = 0,
    ) -> List[Dict]:
        """
        Get earnings calendar for a symbol.
        
        Used for catalyst detection in EP setups.
        
        Args:
            symbol: Stock symbol
            days_back: Days to look back for recent earnings
            days_forward: Days to look ahead for upcoming earnings
            
        Returns:
            List of earnings events with date and EPS info
        """
        from datetime import timedelta
        
        # Calculate date range
        today = datetime.now(timezone.utc).date()
        from_date = (today - timedelta(days=days_back)).isoformat()
        to_date = (today + timedelta(days=days_forward)).isoformat()
        
        # FMP earnings calendar endpoint
        data = self._get(
            "historical/earning_calendar",
            params={
                "from": from_date,
                "to": to_date,
            }
        )
        
        if not data:
            return []
        
        # Filter for the specific symbol
        events = []
        for item in data:
            if item.get("symbol", "").upper() == symbol.upper():
                events.append({
                    "date": item.get("date"),
                    "symbol": item.get("symbol"),
                    "eps": item.get("eps"),
                    "eps_estimated": item.get("epsEstimated"),
                    "revenue": item.get("revenue"),
                    "revenue_estimated": item.get("revenueEstimated"),
                    "fiscal_period": item.get("fiscalDateEnding"),
                })
        
        return events
    
    def has_recent_earnings(self, symbol: str, days: int = 5) -> tuple[bool, Optional[str]]:
        """
        Check if symbol has recent PAST earnings (catalyst check).
        
        Args:
            symbol: Stock symbol
            days: Number of days to look back
            
        Returns:
            (has_earnings, earnings_date)
        """
        events = self.get_earnings_calendar(symbol, days_back=days, days_forward=0)
        if events:
            return True, events[0].get("date")
        return False, None
    
    def has_upcoming_earnings(self, symbol: str, days: int = 5) -> tuple[bool, Optional[str]]:
        """
        Check if symbol has UPCOMING earnings (risk check).
        
        KK Rule: Don't trade stocks with earnings in the next 5 days.
        
        Args:
            symbol: Stock symbol
            days: Number of days to look ahead
            
        Returns:
            (has_upcoming, earnings_date)
        """
        events = self.get_earnings_calendar(symbol, days_back=0, days_forward=days)
        if events:
            return True, events[0].get("date")
        return False, None
    
    def get_stock_news(
        self,
        symbol: str,
        limit: int = 10,
    ) -> List[Dict]:
        """
        Get recent news headlines for a symbol.
        
        Used for catalyst detection via headline classification.
        
        Args:
            symbol: Stock symbol
            limit: Max headlines to return
            
        Returns:
            List of news items with title, date, site, url
        """
        data = self._get(
            f"stock_news",
            params={
                "tickers": symbol,
                "limit": str(limit),
            }
        )
        
        if not data:
            return []
        
        news = []
        for item in data:
            news.append({
                "title": item.get("title", ""),
                "date": item.get("publishedDate", ""),
                "site": item.get("site", ""),
                "url": item.get("url", ""),
                "symbol": item.get("symbol", symbol),
            })
        
        return news
    
    def get_recent_headlines(self, symbol: str, days: int = 5) -> List[str]:
        """
        Get just the headlines for a symbol (for regex classification).
        
        Args:
            symbol: Stock symbol
            days: Days to look back
            
        Returns:
            List of headline strings
        """
        from datetime import timedelta
        
        news = self.get_stock_news(symbol, limit=20)
        
        if not news:
            return []
        
        today = datetime.now(timezone.utc).date()
        cutoff = today - timedelta(days=days)
        
        headlines = []
        for item in news:
            try:
                # Parse date
                pub_date_str = item.get("date", "")
                if pub_date_str:
                    pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00")).date()
                    if pub_date >= cutoff:
                        headlines.append(item.get("title", ""))
            except (ValueError, TypeError):
                # If date parsing fails, include anyway
                headlines.append(item.get("title", ""))
        
        return headlines
    
    def has_recent_catalyst(
        self,
        symbol: str,
        days: int = 5,  # KK: 5 days minimum for earnings plays
    ) -> tuple[bool, str, str]:
        """
        Check if symbol has a recent catalyst (earnings or material news).
        
        This is the primary method for EP catalyst verification.
        
        IMPORTANT: Only looks at PAST earnings/news (days_back), NOT upcoming.
        We don't want to trade before earnings - we want the post-earnings move.
        
        Args:
            symbol: Stock symbol
            days: Days to look back (NOT forward) - default 5 per KK methodology
            
        Returns:
            (has_catalyst, catalyst_type, catalyst_description)
            - catalyst_type: "earnings", "news", or "none"
            - catalyst_description: Brief description of the catalyst
        """
        import re
        
        # 1. Check for recent PAST earnings (strongest catalyst)
        # days_forward=0 ensures we only find earnings that already happened
        has_earnings, earnings_date = self.has_recent_earnings(symbol, days=days)
        if has_earnings:
            return (True, "earnings", f"Earnings reported {earnings_date}")
        
        # 2. Check news headlines for material events
        headlines = self.get_recent_headlines(symbol, days=days)
        if not headlines:
            return (False, "none", "No recent news found")
        
        # Define patterns that indicate material events (EP catalysts)
        # These are events that can cause legitimate episodic pivots
        catalyst_patterns = [
            # Earnings-related (backup to earnings calendar)
            r'earnings|quarterly results|quarterly report|q[1-4].*results|beat.*estimates|missed.*estimates',
            r'revenue.*[0-9]|profit.*[0-9]|loss.*[0-9]|eps.*[0-9]',
            
            # Major business events
            r'fda.*approv|drug.*approv|clinical.*trial|phase.*[123]|breakthrough',
            r'contract.*\$|\$.*contract|deal.*\$|\$.*deal|partnership|acquisition|merger|buyout',
            r'guidance.*raise|guidance.*up|upgrade|raised.*target|price.*target',
            r'announces.*guidance|financial.*guidance|fy.*guidance|[0-9]{4}.*guidance',
            r'dividend.*increase|special.*dividend|buyback|repurchase',
            
            # Analyst/Rating actions
            r'analyst.*upgrade|upgraded|initiated.*buy|initiated.*outperform',
            r'buy.*rating|overweight|strong.*buy',
            
            # Growth catalysts
            r'revenue.*growth|sales.*growth|beat.*expectations|surpass|exceeded',
            r'new.*product|launch|expansion|entered.*market',
            
            # Investor/Healthcare conferences (ERAS fix - JP Morgan, Evercore, etc)
            r'j\.?p\.?\s*morgan.*healthcare|j\.?p\.?\s*morgan.*conference',
            r'healthcare.*conference|investor.*conference|evercore.*conference',
            r'present.*at.*conference|presenting.*at',
            
            # Biotech/Pharma positive catalysts (NCEL fix - positive study results)
            # Only match inherently POSITIVE terms to avoid catching bad trial results
            r'positive.*results|positive.*data|positive.*outcome',
            r'fda.*clearance|fda.*breakthrough|accelerated.*approval',
            r'successful.*trial|met.*primary.*endpoint|exceeded.*endpoint',
            r'patent.*grant|ip.*protection',
        ]
        
        # Patterns that indicate NON-catalysts (noise)
        noise_patterns = [
            r'market.*wrap|stock.*move|why.*moving|what.*know',
            r'dividend.*ex-date|ex-dividend',  # Just tracking dates, not actual news
            r'watch.*list|stocks.*to.*watch|top.*picks',
            r'technical.*analysis|chart.*pattern',
        ]
        
        # Check each headline
        for headline in headlines:
            headline_lower = headline.lower()
            
            # Skip noise headlines
            is_noise = any(re.search(pattern, headline_lower) for pattern in noise_patterns)
            if is_noise:
                continue
            
            # Check for catalyst patterns
            for pattern in catalyst_patterns:
                if re.search(pattern, headline_lower):
                    # Found a material catalyst
                    short_headline = headline[:80] + "..." if len(headline) > 80 else headline
                    return (True, "news", short_headline)
        
        # No catalyst found in headlines
        return (False, "none", f"No material catalyst in {len(headlines)} headlines")


# Global singleton for shared rate limiting
_fmp_singleton: Optional[FMPAdapter] = None


def get_fmp_adapter() -> FMPAdapter:
    """Get singleton FMP adapter - ensures all services share the same rate limiter."""
    global _fmp_singleton
    if _fmp_singleton is None:
        _fmp_singleton = FMPAdapter()
        print("[FMP] Created new singleton adapter")
    return _fmp_singleton


def set_fmp_adapter(adapter: FMPAdapter) -> None:
    """Set the singleton FMP adapter. Call this at startup to share rate limiting."""
    global _fmp_singleton
    _fmp_singleton = adapter
    print("[FMP] Singleton adapter set from external source")
