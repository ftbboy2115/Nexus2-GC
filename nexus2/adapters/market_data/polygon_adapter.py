"""
Polygon.io Market Data Adapter

Provides real-time quotes, historical bars, and market snapshots from Polygon.io.
Developer tier ($200/mo) features: real-time streaming, unlimited API calls.
"""

import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional
import httpx
from nexus2.utils.time_utils import now_et

logger = logging.getLogger(__name__)

from nexus2.adapters.market_data.protocol import (
    MarketDataProvider,
    OHLCV,
    Quote,
    StockInfo,
)

from nexus2 import config as app_config


@dataclass
class PolygonConfig:
    """Configuration for Polygon.io API."""
    api_key: str
    base_url: str = "https://api.polygon.io"
    timeout: float = 10.0


# Staleness threshold for lastTrade (seconds) — beyond this, use bid/ask midpoint
STALE_TRADE_THRESHOLD_SECONDS = 120


class PolygonAdapter:
    """
    Polygon.io Market Data Adapter.
    
    Provides:
    - Real-time quotes (last trade, NBBO)
    - Historical bars (intraday and daily)
    - Market snapshots (gainers/losers)
    - Ticker details (shares outstanding, market cap)
    """
    
    def __init__(self, config: Optional[PolygonConfig] = None):
        if config:
            self.config = config
        else:
            api_key = app_config.POLYGON_API_KEY
            if not api_key:
                logger.warning("[Polygon] No API key configured")
            self.config = PolygonConfig(api_key=api_key or "")
        
        self._client = httpx.Client(timeout=self.config.timeout)
        self._shutdown = False
    
    def __del__(self):
        self._shutdown = True
        if hasattr(self, '_client'):
            self._client.close()
    
    def _get(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make GET request to Polygon API."""
        if not self.config.api_key:
            logger.warning("[Polygon] No API key, skipping request")
            return None
        
        url = f"{self.config.base_url}{endpoint}"
        request_params = params or {}
        request_params["apiKey"] = self.config.api_key
        
        try:
            response = self._client.get(url, params=request_params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("[Polygon] Rate limit hit (429)")
            elif e.response.status_code == 404:
                logger.debug(f"[Polygon] 404 Not Found: {endpoint} (ticker may not exist)")
            else:
                logger.error(f"[Polygon] HTTP {e.response.status_code}: {endpoint}")
            return None
        except Exception as e:
            logger.error(f"[Polygon] Request error on {endpoint}: {e}")
            return None
    
    # =========================================================================
    # Quote Methods
    # =========================================================================
    
    @staticmethod
    def _parse_polygon_timestamp(ns_timestamp) -> datetime:
        """Convert Polygon nanosecond Unix timestamp to datetime (UTC).
        
        Polygon API returns timestamps in nanoseconds since epoch.
        Falls back to datetime.now(UTC) if parsing fails.
        """
        if not ns_timestamp:
            return datetime.now(timezone.utc)
        try:
            # Nanoseconds → seconds
            seconds = int(ns_timestamp) / 1_000_000_000
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            return datetime.now(timezone.utc)
    
    def get_quote(self, symbol: str) -> Optional[Quote]:
        """
        Get real-time quote using snapshot endpoint.
        
        Returns latest trade price, NBBO bid/ask, and volume.
        Detects stale lastTrade and falls back to bid/ask midpoint
        during market hours when staleness exceeds threshold.
        """
        data = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
        if not data or data.get("status") != "OK":
            return None
        
        ticker = data.get("ticker", {})
        day = ticker.get("day", {})
        last_trade = ticker.get("lastTrade", {})
        last_quote = ticker.get("lastQuote", {})
        prev_day = ticker.get("prevDay", {})
        
        # Parse real trade timestamp (not datetime.now!)
        trade_timestamp = self._parse_polygon_timestamp(last_trade.get("t"))
        trade_age_seconds = (datetime.now(timezone.utc) - trade_timestamp).total_seconds()
        
        # Primary price: lastTrade, fallback to day close
        price = last_trade.get("p") or day.get("c") or 0
        bid_price = last_quote.get("p", 0) or 0
        ask_price = last_quote.get("P", 0) or 0
        price_source = "lastTrade"
        
        # Midpoint fallback during market hours when lastTrade is stale
        from nexus2.utils.time_utils import is_market_hours
        if (is_market_hours() and
            trade_age_seconds > STALE_TRADE_THRESHOLD_SECONDS and
            bid_price > 0 and ask_price > 0 and float(price) > 0):
            midpoint = (float(bid_price) + float(ask_price)) / 2
            spread_pct = (float(ask_price) - float(bid_price)) / float(bid_price) * 100
            if spread_pct < 5.0 and abs(midpoint - float(price)) / float(price) > 0.01:
                logger.warning(
                    f"[Polygon] {symbol}: lastTrade is {trade_age_seconds:.0f}s old "
                    f"(${price:.2f}), using bid/ask midpoint ${midpoint:.2f} "
                    f"(bid=${bid_price:.2f}, ask=${ask_price:.2f}, spread={spread_pct:.1f}%)"
                )
                price = midpoint
                price_source = "midpoint"
        
        # Calculate change from prev_day
        prev_close = prev_day.get("c", 0) or 0
        change = float(price) - float(prev_close) if prev_close else 0
        change_pct = (change / float(prev_close) * 100) if prev_close else 0
        
        return Quote(
            symbol=symbol,
            price=Decimal(str(price)),
            change=Decimal(str(round(change, 2))),
            change_percent=Decimal(str(round(change_pct, 2))),
            bid=Decimal(str(bid_price)),
            ask=Decimal(str(ask_price)),
            volume=day.get("v", 0),
            timestamp=trade_timestamp,
            quote_age_seconds=trade_age_seconds,
            price_source=price_source,
        )
    
    def get_session_snapshot(self, symbol: str) -> Optional[dict]:
        """
        Get session snapshot data from Polygon (single API call).
        
        Returns raw session OHLV, previous close, and last price — everything
        needed by build_session_snapshot() without any FMP calls.
        """
        data = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
        if not data or data.get("status") != "OK":
            return None
        
        ticker = data.get("ticker", {})
        day = ticker.get("day", {})
        prev_day = ticker.get("prevDay", {})
        last_trade = ticker.get("lastTrade", {})
        
        price = last_trade.get("p") or day.get("c") or 0
        prev_close = prev_day.get("c", 0) or 0
        
        if not price or not prev_close:
            return None
        
        return {
            "session_open": float(day.get("o", 0) or 0),
            "session_high": float(day.get("h", 0) or 0),
            "session_low": float(day.get("l", 0) or 0),
            "session_volume": int(day.get("v", 0) or 0),
            "prev_close": float(prev_close),
            "last_price": float(price),
        }
    
    def get_last_trade(self, symbol: str) -> Optional[Quote]:
        """
        Get last trade price only (faster endpoint).
        """
        data = self._get(f"/v2/last/trade/{symbol}")
        if not data or data.get("status") != "OK":
            return None
        
        result = data.get("results", {})
        price = result.get("p", 0)
        
        trade_timestamp = self._parse_polygon_timestamp(result.get("t"))
        return Quote(
            symbol=symbol,
            price=Decimal(str(price)),
            change=Decimal("0"),
            change_percent=Decimal("0"),
            bid=Decimal("0"),
            ask=Decimal("0"),
            volume=0,
            timestamp=trade_timestamp,
            quote_age_seconds=(datetime.now(timezone.utc) - trade_timestamp).total_seconds(),
            price_source="lastTrade",
        )
    
    def get_quotes_batch(self, symbols: List[str]) -> Dict[str, Quote]:
        """
        Get quotes for multiple symbols using batch snapshot.
        
        Uses the tickers snapshot endpoint with comma-separated symbols.
        """
        if not symbols:
            return {}
        
        # Polygon snapshot supports up to 250 tickers
        symbols_str = ",".join(symbols[:250])
        data = self._get(
            f"/v2/snapshot/locale/us/markets/stocks/tickers",
            params={"tickers": symbols_str}
        )
        
        if not data or data.get("status") != "OK":
            return {}
        
        quotes = {}
        for ticker in data.get("tickers", []):
            sym = ticker.get("ticker")
            if not sym:
                continue
            
            day = ticker.get("day", {})
            last_trade = ticker.get("lastTrade", {})
            last_quote = ticker.get("lastQuote", {})
            
            price = last_trade.get("p") or day.get("c") or 0
            bid_price = last_quote.get("p", 0) or 0
            ask_price = last_quote.get("P", 0) or 0
            
            # Parse real trade timestamp
            trade_timestamp = self._parse_polygon_timestamp(last_trade.get("t"))
            trade_age_seconds = (datetime.now(timezone.utc) - trade_timestamp).total_seconds()
            price_source = "lastTrade"
            
            # Midpoint fallback during market hours when lastTrade is stale
            from nexus2.utils.time_utils import is_market_hours
            if (is_market_hours() and
                trade_age_seconds > STALE_TRADE_THRESHOLD_SECONDS and
                bid_price > 0 and ask_price > 0 and float(price) > 0):
                midpoint = (float(bid_price) + float(ask_price)) / 2
                spread_pct = (float(ask_price) - float(bid_price)) / float(bid_price) * 100
                if spread_pct < 5.0 and abs(midpoint - float(price)) / float(price) > 0.01:
                    logger.warning(
                        f"[Polygon] {sym}: lastTrade is {trade_age_seconds:.0f}s old "
                        f"(${price:.2f}), using bid/ask midpoint ${midpoint:.2f} "
                        f"(bid=${bid_price:.2f}, ask=${ask_price:.2f}, spread={spread_pct:.1f}%)"
                    )
                    price = midpoint
                    price_source = "midpoint"
            
            # Calculate change
            prev_day = ticker.get("prevDay", {})
            prev_close = prev_day.get("c", 0) or 0
            change = float(price) - float(prev_close) if prev_close else 0
            change_pct = (change / float(prev_close) * 100) if prev_close else 0
            
            quotes[sym] = Quote(
                symbol=sym,
                price=Decimal(str(price)),
                change=Decimal(str(round(change, 2))),
                change_percent=Decimal(str(round(change_pct, 2))),
                bid=Decimal(str(bid_price)),
                ask=Decimal(str(ask_price)),
                volume=day.get("v", 0),
                timestamp=trade_timestamp,
                quote_age_seconds=trade_age_seconds,
                price_source=price_source,
            )
        
        return quotes
    
    # =========================================================================
    # Market Movers
    # =========================================================================
    
    def get_gainers(self) -> List[dict]:
        """
        Get top 20 gainers snapshot.
        
        Returns stocks with largest % increase since previous close.
        Note: 10K minimum volume filter applied by Polygon.
        """
        data = self._get("/v2/snapshot/locale/us/markets/stocks/gainers")
        if not data or data.get("status") != "OK":
            return []
        
        gainers = []
        for ticker in data.get("tickers", []):
            day = ticker.get("day", {})
            prev_day = ticker.get("prevDay", {})
            
            gainers.append({
                "symbol": ticker.get("ticker"),
                "price": day.get("c", 0),
                "change_percent": ticker.get("todaysChangePerc", 0),
                "volume": day.get("v", 0),
                "prev_close": prev_day.get("c", 0),
            })
        
        return gainers
    
    def get_losers(self) -> List[dict]:
        """
        Get top 20 losers snapshot.
        """
        data = self._get("/v2/snapshot/locale/us/markets/stocks/losers")
        if not data or data.get("status") != "OK":
            return []
        
        losers = []
        for ticker in data.get("tickers", []):
            day = ticker.get("day", {})
            prev_day = ticker.get("prevDay", {})
            
            losers.append({
                "symbol": ticker.get("ticker"),
                "price": day.get("c", 0),
                "change_percent": ticker.get("todaysChangePerc", 0),
                "volume": day.get("v", 0),
                "prev_close": prev_day.get("c", 0),
            })
        
        return losers
    
    # =========================================================================
    # Ticker Reference Data
    # =========================================================================
    
    def get_ticker_details(self, symbol: str) -> Optional[dict]:
        """
        Get ticker details including shares outstanding, market cap.
        
        Note: Does NOT include float shares (use FMP for that).
        """
        data = self._get(f"/v3/reference/tickers/{symbol}")
        if not data or data.get("status") != "OK":
            return None
        
        results = data.get("results", {})
        return {
            "symbol": results.get("ticker"),
            "name": results.get("name"),
            "market_cap": results.get("market_cap"),
            "shares_outstanding": results.get("share_class_shares_outstanding") or results.get("weighted_shares_outstanding"),
            "primary_exchange": results.get("primary_exchange"),
            "type": results.get("type"),
            "sic_code": results.get("sic_code"),
            "sic_description": results.get("sic_description"),
        }
    
    # =========================================================================
    # Historical Bars
    # =========================================================================
    
    def get_intraday_bars(
        self,
        symbol: str,
        timeframe: str = "1",  # multiplier (minutes or seconds)
        limit: int = 1000,
        from_date: Optional[str] = None,  # YYYY-MM-DD
        to_date: Optional[str] = None,
        unit: str = "minute",  # "minute" or "second"
    ) -> Optional[List[OHLCV]]:
        """
        Get intraday bars.
        
        Args:
            symbol: Stock symbol
            timeframe: Bar size multiplier (1, 5, 15 for minutes; 10, 30 for seconds)
            limit: Max bars to return
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            unit: Time unit - "minute" (default) or "second"
        """
        # Default to today
        if not from_date:
            from_date = now_et().strftime("%Y-%m-%d")
        if not to_date:
            to_date = from_date
        
        # Support sub-minute timeframes (e.g., 10-second bars)
        # Polygon API: /range/{multiplier}/{timespan}/{from}/{to}
        sort_order = "desc" if unit == "minute" else "asc"
        data = self._get(
            f"/v2/aggs/ticker/{symbol}/range/{timeframe}/{unit}/{from_date}/{to_date}",
            params={"limit": limit, "sort": sort_order}
        )
        
        if not data or data.get("status") != "OK":
            return None
        
        bars = []
        for result in data.get("results", []):
            # Convert timestamp from ms to datetime
            ts = result.get("t", 0) / 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            
            bars.append(OHLCV(
                timestamp=dt,
                open=Decimal(str(result.get("o", 0))),
                high=Decimal(str(result.get("h", 0))),
                low=Decimal(str(result.get("l", 0))),
                close=Decimal(str(result.get("c", 0))),
                volume=result.get("v", 0),
            ))
        
        # Reverse to chronological order (oldest first) for indicator calculations
        # We fetch sort=desc to get NEWEST bars within limit, then reverse
        if sort_order == "desc":
            return list(reversed(bars))
        return bars
    
    def get_second_bars(
        self,
        symbol: str,
        seconds: int = 10,  # 10s bars (Ross's typical)
        limit: int = 5000,
        from_date: Optional[str] = None,  # YYYY-MM-DD
        to_date: Optional[str] = None,
    ) -> Optional[List[OHLCV]]:
        """
        Get sub-minute bars (second-level granularity).
        
        Polygon added "second aggregates" in Sept 2023.
        Use this for high-fidelity simulation matching Ross's 10s chart timing.
        
        Args:
            symbol: Stock symbol
            seconds: Bar size in seconds (10, 30, etc.)
            limit: Max bars to return (up to 50,000)
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
        """
        # Default to today
        if not from_date:
            from_date = now_et().strftime("%Y-%m-%d")
        if not to_date:
            to_date = from_date
        
        data = self._get(
            f"/v2/aggs/ticker/{symbol}/range/{seconds}/second/{from_date}/{to_date}",
            params={"limit": limit, "sort": "asc"}
        )
        
        if not data or data.get("status") != "OK":
            logger.warning(f"[Polygon] Failed to get {seconds}s bars for {symbol}")
            return None
        
        bars = []
        for result in data.get("results", []):
            ts = result.get("t", 0) / 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            
            bars.append(OHLCV(
                timestamp=dt,
                open=Decimal(str(result.get("o", 0))),
                high=Decimal(str(result.get("h", 0))),
                low=Decimal(str(result.get("l", 0))),
                close=Decimal(str(result.get("c", 0))),
                volume=result.get("v", 0),
            ))
        
        logger.info(f"[Polygon] Fetched {len(bars)} {seconds}s bars for {symbol}")
        return bars
    
    def get_daily_bars(
        self,
        symbol: str,
        limit: int = 60,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Optional[List[OHLCV]]:
        """
        Get daily OHLCV bars.
        
        Args:
            symbol: Stock symbol
            limit: Max bars to return
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
        """
        # Default date range: calculate from limit (trading days ~= calendar days / 1.4)
        if not to_date:
            to_date = now_et().strftime("%Y-%m-%d")
        if not from_date:
            from datetime import timedelta
            # Need ~1.6 calendar days per trading day to account for weekends/holidays
            calendar_days_needed = int(limit * 1.6) + 30  # Extra buffer for holidays
            from_dt = now_et() - timedelta(days=calendar_days_needed)
            from_date = from_dt.strftime("%Y-%m-%d")
        
        data = self._get(
            f"/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}",
            params={"limit": limit, "sort": "asc"}
        )
        
        if not data or data.get("status") != "OK":
            return None
        
        bars = []
        for result in data.get("results", []):
            ts = result.get("t", 0) / 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            
            bars.append(OHLCV(
                timestamp=dt,
                open=Decimal(str(result.get("o", 0))),
                high=Decimal(str(result.get("h", 0))),
                low=Decimal(str(result.get("l", 0))),
                close=Decimal(str(result.get("c", 0))),
                volume=result.get("v", 0),
            ))
        
        return bars
    
    # =========================================================================
    # News
    # =========================================================================
    
    def get_news(
        self,
        symbol: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict]:
        """
        Get recent news articles.
        
        Args:
            symbol: Filter by ticker (optional)
            limit: Max articles to return
        """
        params = {"limit": limit, "order": "desc"}
        if symbol:
            params["ticker"] = symbol
        
        data = self._get("/v2/reference/news", params=params)
        if not data or data.get("status") != "OK":
            return []
        
        articles = []
        for result in data.get("results", []):
            articles.append({
                "title": result.get("title"),
                "author": result.get("author"),
                "published_utc": result.get("published_utc"),
                "article_url": result.get("article_url"),
                "tickers": result.get("tickers", []),
                "description": result.get("description"),
            })
        
        return articles


# Singleton instance
_polygon_adapter: Optional[PolygonAdapter] = None


def get_polygon_adapter() -> PolygonAdapter:
    """Get or create singleton Polygon adapter."""
    global _polygon_adapter
    if _polygon_adapter is None:
        _polygon_adapter = PolygonAdapter()
    return _polygon_adapter
