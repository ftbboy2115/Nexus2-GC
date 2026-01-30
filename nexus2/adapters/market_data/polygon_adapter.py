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
    
    def get_quote(self, symbol: str) -> Optional[Quote]:
        """
        Get real-time quote using snapshot endpoint.
        
        Returns latest trade price, NBBO bid/ask, and volume.
        """
        data = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
        if not data or data.get("status") != "OK":
            return None
        
        ticker = data.get("ticker", {})
        day = ticker.get("day", {})
        last_trade = ticker.get("lastTrade", {})
        last_quote = ticker.get("lastQuote", {})
        prev_day = ticker.get("prevDay", {})
        
        # Use last trade price, fallback to close
        price = last_trade.get("p") or day.get("c") or 0
        
        # Calculate change from prev_day
        prev_close = prev_day.get("c", 0) or 0
        change = float(price) - float(prev_close) if prev_close else 0
        change_pct = (change / float(prev_close) * 100) if prev_close else 0
        
        return Quote(
            symbol=symbol,
            price=Decimal(str(price)),
            change=Decimal(str(round(change, 2))),
            change_percent=Decimal(str(round(change_pct, 2))),
            bid=Decimal(str(last_quote.get("p", 0) or 0)),  # bid price
            ask=Decimal(str(last_quote.get("P", 0) or 0)),  # ask price
            volume=day.get("v", 0),
            timestamp=datetime.now(timezone.utc),
        )
    
    def get_last_trade(self, symbol: str) -> Optional[Quote]:
        """
        Get last trade price only (faster endpoint).
        """
        data = self._get(f"/v2/last/trade/{symbol}")
        if not data or data.get("status") != "OK":
            return None
        
        result = data.get("results", {})
        price = result.get("p", 0)
        
        return Quote(
            symbol=symbol,
            price=Decimal(str(price)),
            change=Decimal("0"),
            change_percent=Decimal("0"),
            bid=Decimal("0"),
            ask=Decimal("0"),
            volume=0,
            timestamp=datetime.now(timezone.utc),
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
                bid=Decimal(str(last_quote.get("p", 0) or 0)),
                ask=Decimal(str(last_quote.get("P", 0) or 0)),
                volume=day.get("v", 0),
                timestamp=datetime.now(timezone.utc),
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
        timeframe: str = "1",  # minutes
        limit: int = 1000,
        from_date: Optional[str] = None,  # YYYY-MM-DD
        to_date: Optional[str] = None,
    ) -> Optional[List[OHLCV]]:
        """
        Get intraday bars.
        
        Args:
            symbol: Stock symbol
            timeframe: Bar size in minutes (1, 5, 15, 30, 60)
            limit: Max bars to return
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
        """
        # Default to today
        if not from_date:
            from_date = datetime.now().strftime("%Y-%m-%d")
        if not to_date:
            to_date = from_date
        
        data = self._get(
            f"/v2/aggs/ticker/{symbol}/range/{timeframe}/minute/{from_date}/{to_date}",
            params={"limit": limit, "sort": "asc"}
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
        # Default date range: last 90 days
        if not to_date:
            to_date = datetime.now().strftime("%Y-%m-%d")
        if not from_date:
            from datetime import timedelta
            from_dt = datetime.now() - timedelta(days=90)
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
