"""
Alpaca Market Data Adapter

Provides real-time and historical market data from Alpaca.
Ported from: core/scan_ep.py
"""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import httpx

from nexus2.adapters.market_data.protocol import (
    MarketDataProvider,
    OHLCV,
    Quote,
    StockInfo,
)

# Import centralized config (auto-loads .env)
from nexus2 import config as app_config


@dataclass
class AlpacaConfig:
    """Configuration for Alpaca API."""
    api_key: str
    api_secret: str
    base_url: str = "https://data.alpaca.markets"
    timeout: float = 10.0


class AlpacaAdapter:
    """
    Alpaca Market Data Adapter.
    
    Provides:
    - Real-time quotes
    - Daily OHLCV data (fallback)
    - Intraday OHLCV data (primary for EP)
    - Extended hours support
    """
    
    def __init__(self, config: Optional[AlpacaConfig] = None):
        if config:
            self.config = config
        else:
            # Load from centralized config (which loads .env)
            self.config = AlpacaConfig(
                api_key=app_config.ALPACA_KEY,
                api_secret=app_config.ALPACA_SECRET,
            )
        
        self._client = httpx.Client(
            timeout=self.config.timeout,
            headers={
                "APCA-API-KEY-ID": self.config.api_key,
                "APCA-API-SECRET-KEY": self.config.api_secret,
            }
        )
        
        # Quote cache with 2-second TTL to reduce rate limits
        # Format: {symbol: (quote, timestamp)}
        self._quote_cache: Dict[str, Tuple[Quote, float]] = {}
        self._quote_ttl = 2.0  # 2 seconds - short enough for trading, long enough to reduce calls
    
    def __del__(self):
        if hasattr(self, '_client'):
            self._client.close()
    
    def _get(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make GET request to Alpaca API."""
        url = f"{self.config.base_url}/{endpoint}"
        
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[Alpaca] Request error: {e}")
            return None
    
    # =========================================================================
    # MarketDataProvider Implementation
    # =========================================================================
    
    def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get latest quote for a symbol. Cached for 2 seconds to reduce rate limits."""
        # Check cache first
        now = time.time()
        if symbol in self._quote_cache:
            cached_quote, cached_time = self._quote_cache[symbol]
            if now - cached_time < self._quote_ttl:
                return cached_quote
        
        data = self._get(f"v2/stocks/{symbol}/quotes/latest")
        if not data or "quote" not in data:
            return None
        
        q = data["quote"]
        
        # Parse timestamp and check for stale data
        quote_timestamp = None
        if q.get("t"):
            try:
                quote_timestamp = datetime.fromisoformat(q["t"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        
        # Reject stale quotes (older than 1 hour or from previous day)
        if quote_timestamp:
            now_utc = datetime.now(timezone.utc)
            age_seconds = (now_utc - quote_timestamp).total_seconds()
            quote_date = quote_timestamp.date()
            today = now_utc.date()
            
            # If quote is from a previous day or >1 hour old, it's stale
            if quote_date < today or age_seconds > 3600:
                # Only log during live mode - sim mode has expected stale quotes
                try:
                    from nexus2.api.routes.warrior_sim_routes import get_warrior_sim_broker
                    if get_warrior_sim_broker() is None:
                        print(f"[Alpaca] {symbol}: Rejecting stale quote (age={age_seconds/3600:.1f}h, date={quote_date})")
                except Exception:
                    print(f"[Alpaca] {symbol}: Rejecting stale quote (age={age_seconds/3600:.1f}h, date={quote_date})")
                return None
        
        # Alpaca quote has bid/ask, use midpoint for price
        bid = Decimal(str(q.get("bp", 0)))
        ask = Decimal(str(q.get("ap", 0)))
        
        # Reject suspicious spreads (ask > 5x bid indicates phantom data)
        if bid > 0 and ask > 0 and ask > bid * 5:
            print(f"[Alpaca] {symbol}: Rejecting suspicious spread (bid=${bid}, ask=${ask})")
            return None
        
        price = (bid + ask) / 2 if bid and ask else bid or ask
        
        quote = Quote(
            symbol=symbol,
            price=price,
            change=Decimal("0"),  # Would need prev close to calculate
            change_percent=Decimal("0"),
            volume=0,  # Quote doesn't include volume
            timestamp=quote_timestamp or datetime.now(timezone.utc),
        )
        
        # Cache the result
        self._quote_cache[symbol] = (quote, now)
        return quote
    
    def get_quotes_batch(self, symbols: List[str]) -> Dict[str, Quote]:
        """Get quotes for multiple symbols."""
        quotes = {}
        
        # Alpaca supports comma-separated symbols
        tickers = ",".join(symbols)
        data = self._get(f"v2/stocks/quotes/latest", params={"symbols": tickers})
        
        if not data or "quotes" not in data:
            return quotes
        
        for sym, q in data["quotes"].items():
            bid = Decimal(str(q.get("bp", 0)))
            ask = Decimal(str(q.get("ap", 0)))
            price = (bid + ask) / 2 if bid and ask else bid or ask
            
            quotes[sym] = Quote(
                symbol=sym,
                price=price,
                change=Decimal("0"),
                change_percent=Decimal("0"),
                volume=0,
                timestamp=datetime.fromisoformat(q.get("t", "").replace("Z", "+00:00")),
                bid=bid if bid else None,
                ask=ask if ask else None,
            )
        
        return quotes
    
    def get_daily_bars(
        self, 
        symbol: str, 
        limit: int = 60
    ) -> Optional[List[OHLCV]]:
        """Get daily OHLCV bars."""
        data = self._get(
            f"v2/stocks/{symbol}/bars",
            params={
                "timeframe": "1Day",
                "limit": str(limit),
                "adjustment": "raw",
            }
        )
        
        if not data or "bars" not in data:
            return None
        
        bars_data = data.get("bars")
        if not bars_data or not isinstance(bars_data, list):
            return None
        
        bars = []
        for bar in bars_data:
            try:
                bars.append(OHLCV(
                    timestamp=datetime.fromisoformat(bar["t"].replace("Z", "+00:00")),
                    open=Decimal(str(bar["o"])),
                    high=Decimal(str(bar["h"])),
                    low=Decimal(str(bar["l"])),
                    close=Decimal(str(bar["c"])),
                    volume=int(bar["v"]),
                ))
            except (KeyError, ValueError, TypeError):
                continue
        
        return sorted(bars, key=lambda b: b.timestamp) if bars else None
    
    def get_intraday_bars(
        self, 
        symbol: str, 
        timeframe: str = "1Min",
        limit: int = 1000
    ) -> Optional[List[OHLCV]]:
        """
        Get intraday OHLCV bars.
        
        Args:
            symbol: Stock symbol
            timeframe: "1Min", "5Min", "15Min", "1Hour"
            limit: Max bars to return
        
        Note: Returns today's bars in chronological order (oldest first).
        Without start parameter, Alpaca returns OLD historical bars, not today's.
        """
        from datetime import timezone, timedelta
        
        # Start from today 4 AM ET (extended hours start) to get today's bars
        # This ensures we get the current session, not old historical data
        now_utc = datetime.now(timezone.utc)
        # ET is UTC-5 (EST) or UTC-4 (EDT) - use -5 as safe default
        today_4am_et = now_utc.replace(hour=9, minute=0, second=0, microsecond=0)  # 4 AM ET = 9 AM UTC
        
        data = self._get(
            f"v2/stocks/{symbol}/bars",
            params={
                "timeframe": timeframe,
                "limit": str(limit),
                "adjustment": "raw",
                "start": today_4am_et.isoformat(),
                "sort": "asc",  # Chronological order (oldest first, newest last)
            }
        )
        
        if not data or "bars" not in data:
            return None
        
        bars_data = data.get("bars")
        if not bars_data or not isinstance(bars_data, list):
            return None
        
        bars = []
        for bar in bars_data:
            try:
                bars.append(OHLCV(
                    timestamp=datetime.fromisoformat(bar["t"].replace("Z", "+00:00")),
                    open=Decimal(str(bar["o"])),
                    high=Decimal(str(bar["h"])),
                    low=Decimal(str(bar["l"])),
                    close=Decimal(str(bar["c"])),
                    volume=int(bar["v"]),
                ))
            except (KeyError, ValueError, TypeError):
                continue
        
        return sorted(bars, key=lambda b: b.timestamp) if bars else None
    
    def get_stock_info(self, symbol: str) -> Optional[StockInfo]:
        """Get basic stock information (limited in Alpaca)."""
        # Alpaca doesn't provide fundamental data
        # Return minimal info from quote
        quote = self.get_quote(symbol)
        if not quote:
            return None
        
        return StockInfo(
            symbol=symbol,
            name="",  # Not available
            exchange="",  # Not available
            market_cap=Decimal("0"),
            float_shares=None,
            avg_volume_20d=0,
            sector=None,
            industry=None,
        )
    
    def get_prev_close(self, symbol: str) -> Optional[Decimal]:
        """Get previous day's closing price."""
        bars = self.get_daily_bars(symbol, limit=5)
        if not bars or len(bars) < 2:
            return None
        return bars[-2].close
    
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
        ema = bars[0].close
        
        for bar in bars[1:]:
            ema = (bar.close * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    # =========================================================================
    # Alpaca-Specific Methods
    # =========================================================================
    
    def get_today_intraday(
        self,
        symbol: str,
        timeframe: str = "1Min",
    ) -> Optional[List[OHLCV]]:
        """
        Get today's intraday bars only.
        
        Extended-hours aware.
        """
        bars = self.get_intraday_bars(symbol, timeframe, limit=1000)
        if not bars:
            return None
        
        # Filter to today (UTC)
        today_utc = datetime.now(timezone.utc).date()
        today_bars = [b for b in bars if b.timestamp.date() == today_utc]
        
        return today_bars if today_bars else None
    
    def get_session_snapshot(self, symbol: str) -> Optional[Dict]:
        """
        Build EP session snapshot from today's intraday data.
        
        Returns:
            {
                "session_open": Decimal,
                "session_high": Decimal,
                "session_low": Decimal,
                "last_price": Decimal,
                "session_volume": int,
            }
        """
        bars = self.get_today_intraday(symbol)
        if not bars:
            return None
        
        return {
            "session_open": bars[0].open,
            "session_high": max(b.high for b in bars),
            "session_low": min(b.low for b in bars),
            "last_price": bars[-1].close,
            "session_volume": sum(b.volume for b in bars),
        }
