"""
Unified Market Data Provider

Combines FMP (primary) and Alpaca (intraday/fallback) into a single interface.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from nexus2.adapters.market_data.protocol import (
    OHLCV,
    Quote,
    StockInfo,
)
from nexus2.adapters.market_data.fmp_adapter import FMPAdapter, FMPConfig, get_fmp_adapter
from nexus2.adapters.market_data.alpaca_adapter import AlpacaAdapter, AlpacaConfig


@dataclass
class UnifiedConfig:
    """Configuration for unified market data."""
    fmp_config: Optional[FMPConfig] = None
    alpaca_config: Optional[AlpacaConfig] = None
    use_fmp_singleton: bool = True  # Use shared FMP for rate limiting


class UnifiedMarketData:
    """
    Unified Market Data Provider.
    
    Strategy:
    - FMP for screening, fundamentals, daily data
    - Alpaca for intraday data and real-time quotes
    - Automatic fallback between providers
    """
    
    def __init__(self, config: Optional[UnifiedConfig] = None):
        config = config or UnifiedConfig()
        
        # Use singleton FMP adapter to share rate limiting across all services
        if config.use_fmp_singleton:
            self.fmp = get_fmp_adapter()
        else:
            self.fmp = FMPAdapter(config.fmp_config)
        
        self.alpaca = AlpacaAdapter(config.alpaca_config)
    
    # =========================================================================
    # Combined Methods
    # =========================================================================
    
    def get_quote(self, symbol: str) -> Optional[Quote]:
        """
        Get quote, preferring FMP for full data.
        """
        quote = self.fmp.get_quote(symbol)
        if quote:
            return quote
        return self.alpaca.get_quote(symbol)
    
    def get_quotes_batch(self, symbols: List[str]) -> Dict[str, Quote]:
        """Get quotes for multiple symbols via FMP."""
        return self.fmp.get_quotes_batch(symbols)
    
    def get_daily_bars(
        self, 
        symbol: str, 
        limit: int = 60
    ) -> Optional[List[OHLCV]]:
        """
        Get daily bars, FMP primary, Alpaca fallback.
        """
        bars = self.fmp.get_daily_bars(symbol, limit)
        # Accept FMP data if we got at least 10 bars or half the requested limit
        min_bars = min(10, limit // 2) if limit > 0 else 10
        if bars and len(bars) >= min_bars:
            return bars
        return self.alpaca.get_daily_bars(symbol, limit)
    
    def get_intraday_bars(
        self, 
        symbol: str, 
        timeframe: str = "1Min",
        limit: int = 1000
    ) -> Optional[List[OHLCV]]:
        """Get intraday bars from Alpaca."""
        return self.alpaca.get_intraday_bars(symbol, timeframe, limit)
    
    def get_stock_info(self, symbol: str) -> Optional[StockInfo]:
        """Get stock info from FMP."""
        return self.fmp.get_stock_info(symbol)
    
    def get_prev_close(self, symbol: str) -> Optional[Decimal]:
        """Get previous close, FMP primary."""
        close = self.fmp.get_prev_close(symbol)
        if close:
            return close
        return self.alpaca.get_prev_close(symbol)
    
    def get_atr(self, symbol: str, period: int = 14) -> Optional[Decimal]:
        """Calculate ATR, FMP primary."""
        atr = self.fmp.get_atr(symbol, period)
        if atr:
            return atr
        return self.alpaca.get_atr(symbol, period)
    
    def get_sma(self, symbol: str, period: int) -> Optional[Decimal]:
        """Get SMA, FMP primary."""
        sma = self.fmp.get_sma(symbol, period)
        if sma:
            return sma
        return self.alpaca.get_sma(symbol, period)
    
    def get_ema(self, symbol: str, period: int) -> Optional[Decimal]:
        """Get EMA, FMP primary."""
        ema = self.fmp.get_ema(symbol, period)
        if ema:
            return ema
        return self.alpaca.get_ema(symbol, period)
    
    def get_adr_percent(self, symbol: str, period: int = 14) -> Optional[Decimal]:
        """
        Calculate Average Daily Range as percentage.
        
        ADR% = (Average of (High - Low)) / Close * 100
        """
        bars = self.get_daily_bars(symbol, limit=period + 5)
        if not bars or len(bars) < period:
            return None
        
        recent_bars = bars[-period:]
        ranges = [(b.high - b.low) for b in recent_bars]
        avg_range = sum(ranges) / len(ranges)
        
        last_close = bars[-1].close
        if last_close > 0:
            return (avg_range / last_close) * 100
        return None
    
    def get_opening_range(
        self,
        symbol: str,
        timeframe_minutes: int = 5,
        date: Optional[str] = None,
    ) -> Optional[tuple[Decimal, Decimal]]:
        """
        Get the opening range (high, low) for the first N minutes of trading.
        
        Used for EP tactical stop calculation.
        
        Args:
            symbol: Stock symbol
            timeframe_minutes: Opening range timeframe (1, 5, 15, 30)
            date: Date in YYYY-MM-DD format (defaults to today)
            
        Returns:
            (opening_range_high, opening_range_low) or None if unavailable
        """
        return self.fmp.get_opening_range(symbol, timeframe_minutes, date)
    
    def get_average_volume(self, symbol: str, period: int = 20) -> Optional[int]:
        """Get average volume over period."""
        bars = self.get_daily_bars(symbol, limit=period + 5)
        if not bars or len(bars) < period:
            return None
        
        recent_bars = bars[-period:]
        volumes = [b.volume for b in recent_bars]
        return int(sum(volumes) / len(volumes))
    
    def get_historical_bars(self, symbol: str, days: int = 60) -> Optional[List[OHLCV]]:
        """
        Get historical daily bars for affinity analysis.
        
        Alias for get_daily_bars, used by MA affinity callback.
        Returns OHLCV objects (not dicts) for backward compatibility.
        
        Args:
            symbol: Stock symbol
            days: Number of days of history
            
        Returns:
            List of OHLCV objects or None
        """
        return self.get_daily_bars(symbol, limit=days + 10)
    
    # =========================================================================
    # EP-Specific Methods
    # =========================================================================
    
    def build_ep_session_snapshot(
        self,
        symbol: str,
        rvol_lookback: int = 50,
    ) -> Optional[Dict]:
        """
        Build EP session snapshot using FMP data only.
        
        Uses FMP quote for today's session data (no Alpaca dependency).
        
        Returns:
            {
                "yesterday_close": Decimal,
                "avg_daily_volume": int,
                "session_open": Decimal,
                "session_high": Decimal,
                "session_low": Decimal,
                "last_price": Decimal,
                "session_volume": int,
            }
        """
        # Get FMP quote for today's session data
        quote = self.fmp.get_quote(symbol)
        if not quote:
            return None
        
        # Get daily history for yesterday close and avg volume
        daily = self.get_daily_bars(symbol, limit=rvol_lookback + 5)
        if not daily or len(daily) < 2:
            return None
        
        yesterday_close = daily[-2].close
        
        # Calculate average volume (excluding most recent bar)
        hist_bars = daily[:-1]  # All but most recent
        if len(hist_bars) < 10:  # Need at least 10 days for meaningful average
            return None
        
        hist_volumes = [b.volume for b in hist_bars[-rvol_lookback:]] if len(hist_bars) >= rvol_lookback else [b.volume for b in hist_bars]
        avg_daily_volume = sum(hist_volumes) // len(hist_volumes) if hist_volumes else 0
        
        if avg_daily_volume <= 0:
            return None
        
        # Get today's session data from FMP quote
        # FMP quote includes: open, dayHigh, dayLow, price, volume
        quote_data = self.fmp._get(f"quote/{symbol}")
        if not quote_data or len(quote_data) == 0:
            return None
        
        q = quote_data[0]
        session_open = Decimal(str(q.get("open", 0)))
        session_high = Decimal(str(q.get("dayHigh", 0)))
        session_low = Decimal(str(q.get("dayLow", 0)))
        last_price = Decimal(str(q.get("price", 0)))
        session_volume = int(q.get("volume", 0))
        
        # Validate we have real data
        if session_open <= 0 or last_price <= 0:
            return None
        
        return {
            "yesterday_close": yesterday_close,
            "avg_daily_volume": avg_daily_volume,
            "session_open": session_open,
            "session_high": session_high,
            "session_low": session_low,
            "last_price": last_price,
            "session_volume": session_volume,
        }
    
    # =========================================================================
    # Screening Methods
    # =========================================================================
    
    def screen_stocks(
        self,
        min_market_cap: int = 50_000_000,
        min_price: float = 4.0,
        min_volume: int = 50_000,
        limit: int = 2000,
    ) -> List[Dict]:
        """Screen stocks using FMP screener."""
        return self.fmp.screen_stocks(
            min_market_cap=min_market_cap,
            min_price=min_price,
            min_volume=min_volume,
            limit=limit,
        )
    
    def filter_movers(
        self,
        symbols: List[str],
        min_change_pct: float = 3.0,
    ) -> List[str]:
        """Filter symbols by change percentage."""
        return self.fmp.filter_by_change(symbols, min_change_pct)
    
    def get_gainers(self) -> List[Dict]:
        """
        Get top gainers for today (real-time, refreshed every ~1 min).
        
        Falls back to pre-market gainers if regular market data is empty.
        """
        gainers = self.fmp.get_gainers()
        if gainers:
            return gainers
        # Fallback to pre-market gainers when market is closed
        return self.fmp.get_premarket_gainers()
    
    def get_actives(self) -> List[Dict]:
        """Get most active stocks by volume (real-time)."""
        return self.fmp.get_actives()
    
    def get_trend_leaders(self, limit: int = 100) -> List[str]:
        """
        Get trend leaders - stocks with strong momentum for HTF scanning.
        
        Uses FMP gainers (current day momentum) as proxy for trend leaders.
        These are stocks likely to have made big moves recently.
        
        Args:
            limit: Maximum number of symbols to return
            
        Returns:
            List of stock symbols
        """
        try:
            gainers = self.fmp.get_gainers()
            symbols = [g.get("symbol", "") for g in gainers if g.get("symbol")]
            return symbols[:limit]
        except Exception:
            # Fallback to basic screen if gainers endpoint fails
            try:
                stocks = self.screen_stocks(
                    min_market_cap=100_000_000,
                    min_price=5.0,
                    min_volume=100_000,
                    limit=limit,
                )
                return [s.get("symbol", "") for s in stocks if s.get("symbol")]
            except Exception:
                return []
    
    def get_company_name(self, symbol: str) -> Optional[str]:
        """
        Get company name for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Company name or None if unavailable
        """
        try:
            info = self.fmp.get_stock_info(symbol)
            if info:
                return info.name
        except Exception:
            pass
        return None
    
    def get_historical_prices(
        self, 
        symbol: str, 
        days: int = 90
    ) -> Optional[List[Dict]]:
        """
        Get historical daily prices as list of dicts.
        
        Format compatible with HTF scanner expectations:
        [{"open": x, "high": x, "low": x, "close": x, "volume": x}, ...]
        
        Args:
            symbol: Stock symbol
            days: Number of days of history
            
        Returns:
            List of price dicts or None
        """
        bars = self.get_daily_bars(symbol, limit=days + 10)
        if not bars:
            return None
        
        # Convert OHLCV objects to dicts
        return [
            {
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": b.volume,
            }
            for b in bars[-days:]
        ]
    
    def has_recent_catalyst(
        self,
        symbol: str,
        days: int = 3,
    ) -> tuple[bool, str, str]:
        """
        Check if symbol has a recent catalyst (earnings or material news).
        
        Used by EP scanner to filter out stocks without legitimate catalysts.
        
        Args:
            symbol: Stock symbol
            days: Days to look back
            
        Returns:
            (has_catalyst, catalyst_type, catalyst_description)
            - catalyst_type: "earnings", "news", or "none"
            - catalyst_description: Brief description of the catalyst
        """
        return self.fmp.has_recent_catalyst(symbol, days=days)
    
    def has_upcoming_earnings(
        self,
        symbol: str,
        days: int = 5,
    ) -> tuple[bool, str]:
        """
        Check if symbol has UPCOMING earnings (risk check).
        
        KK Rule: Don't trade stocks with earnings in the next 5 days.
        
        Args:
            symbol: Stock symbol
            days: Days to look ahead
            
        Returns:
            (has_upcoming, earnings_date)
        """
        return self.fmp.has_upcoming_earnings(symbol, days=days)
