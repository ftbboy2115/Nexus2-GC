"""
Mock Market Data Provider

Provides historical data for simulation/backtesting.
Replays historical bars as "current" data based on simulation clock.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class OHLCV:
    """OHLCV bar data."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    
    @property
    def typical_price(self) -> float:
        """Typical price: (H+L+C)/3."""
        return (self.high + self.low + self.close) / 3
    
    @property
    def adr(self) -> float:
        """Average daily range for this bar."""
        return self.high - self.low


class MockMarketData:
    """
    Provides simulated market data from historical bars.
    
    Features:
    - Load historical data from dict or file
    - Get current price based on simulation clock time
    - Get historical bars up to simulation time
    - Support for multiple symbols
    """
    
    def __init__(self):
        """Initialize mock market data provider."""
        # Historical data: symbol -> list of OHLCV (oldest first)
        self._data: Dict[str, List[OHLCV]] = {}
        
        # Current prices (can be updated during simulation)
        self._current_prices: Dict[str, float] = {}
        
        # Simulation clock reference (optional)
        self._sim_clock = None
    
    def set_clock(self, clock):
        """Set simulation clock reference."""
        self._sim_clock = clock
    
    def load_data(self, symbol: str, bars: List[Dict]) -> int:
        """
        Load historical bars for a symbol.
        
        Args:
            symbol: Stock symbol
            bars: List of bar dicts with date, open, high, low, close, volume
        
        Returns:
            Number of bars loaded
        """
        ohlcv_bars = []
        for bar in bars:
            ohlcv_bars.append(OHLCV(
                date=bar.get("date", ""),
                open=float(bar.get("open", 0)),
                high=float(bar.get("high", 0)),
                low=float(bar.get("low", 0)),
                close=float(bar.get("close", 0)),
                volume=int(bar.get("volume", 0)),
            ))
        
        # Sort by date (oldest first)
        ohlcv_bars.sort(key=lambda x: x.date)
        self._data[symbol] = ohlcv_bars
        
        # Set current price to latest close
        if ohlcv_bars:
            self._current_prices[symbol] = ohlcv_bars[-1].close
        
        logger.info(f"[MockMarketData] Loaded {len(ohlcv_bars)} bars for {symbol}")
        return len(ohlcv_bars)
    
    def load_synthetic_data(self, symbol: str, start_price: float = 100.0, 
                           days: int = 60, volatility: float = 0.02,
                           trend: float = 0.001) -> int:
        """
        Generate synthetic historical data for testing.
        
        Args:
            symbol: Stock symbol
            start_price: Starting price
            days: Number of days to generate
            volatility: Daily volatility (as decimal)
            trend: Daily trend (as decimal, positive = up)
        
        Returns:
            Number of bars generated
        """
        import random
        from datetime import date
        
        bars = []
        price = start_price
        current_date = date.today() - timedelta(days=days)
        
        for i in range(days):
            # Skip weekends
            while current_date.weekday() >= 5:
                current_date += timedelta(days=1)
            
            # Generate OHLC
            daily_change = (random.random() - 0.5) * 2 * volatility + trend
            open_price = price
            close_price = price * (1 + daily_change)
            
            # High/low with some intraday volatility
            intraday_vol = volatility * 0.5
            high_price = max(open_price, close_price) * (1 + random.random() * intraday_vol)
            low_price = min(open_price, close_price) * (1 - random.random() * intraday_vol)
            
            volume = int(1_000_000 * (0.8 + random.random() * 0.4))
            
            bars.append({
                "date": current_date.isoformat(),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": volume,
            })
            
            price = close_price
            current_date += timedelta(days=1)
        
        return self.load_data(symbol, bars)
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for symbol.
        
        If simulation clock is set, returns price at sim time.
        Otherwise returns latest loaded price.
        """
        if self._sim_clock and symbol in self._data:
            # Get bar for sim date
            sim_date = self._sim_clock.get_trading_day()
            for bar in reversed(self._data[symbol]):
                if bar.date <= sim_date:
                    return bar.close
        
        return self._current_prices.get(symbol)
    
    def get_quote(self, symbol: str) -> Optional[Dict]:
        """
        Get quote (bid/ask/last) for symbol.
        
        Returns:
            Dict with price info, or None if no data
        """
        price = self.get_current_price(symbol)
        if price is None:
            return None
        
        # Simulate small spread
        spread = price * 0.001  # 0.1% spread
        
        return {
            "symbol": symbol,
            "last": price,
            "bid": round(price - spread/2, 2),
            "ask": round(price + spread/2, 2),
            "volume": 0,  # Would need intraday tracking
        }
    
    def get_daily_bars(self, symbol: str, days: int = 60) -> List[OHLCV]:
        """
        Get historical daily bars.
        
        Args:
            symbol: Stock symbol
            days: Number of days to return
        
        Returns:
            List of OHLCV bars (most recent first)
        """
        if symbol not in self._data:
            return []
        
        bars = self._data[symbol]
        
        # If sim clock, filter to bars before sim date
        if self._sim_clock:
            sim_date = self._sim_clock.get_trading_day()
            bars = [b for b in bars if b.date <= sim_date]
        
        # Return most recent 'days' bars
        return list(reversed(bars[-days:]))
    
    def get_bar_for_date(self, symbol: str, date_str: str) -> Optional[OHLCV]:
        """
        Get bar for specific date.
        
        Args:
            symbol: Stock symbol
            date_str: Date in YYYY-MM-DD format
        
        Returns:
            OHLCV bar or None
        """
        if symbol not in self._data:
            return None
        
        for bar in self._data[symbol]:
            if bar.date == date_str:
                return bar
        
        return None
    
    def advance_day(self) -> Dict[str, float]:
        """
        Advance to next day and update current prices.
        
        Should be called when sim clock advances a day.
        
        Returns:
            Dict of symbol -> new price
        """
        if not self._sim_clock:
            return {}
        
        sim_date = self._sim_clock.get_trading_day()
        new_prices = {}
        
        for symbol, bars in self._data.items():
            for bar in bars:
                if bar.date == sim_date:
                    self._current_prices[symbol] = bar.close
                    new_prices[symbol] = bar.close
                    break
        
        return new_prices
    
    def get_symbols(self) -> List[str]:
        """Get list of symbols with loaded data."""
        return list(self._data.keys())
    
    def to_dict(self) -> Dict:
        """Convert to dict for debugging."""
        # Get first/last bar dates for debugging
        date_ranges = {}
        for symbol, bars in self._data.items():
            if bars:
                date_ranges[symbol] = {
                    "first": bars[0].date,
                    "last": bars[-1].date,
                    "count": len(bars)
                }
        
        return {
            "symbols": self.get_symbols(),
            "bar_counts": {s: len(bars) for s, bars in self._data.items()},
            "current_prices": self._current_prices.copy(),
            "date_ranges": date_ranges,  # DEBUG: Show bar date ranges
        }
    
    # ==========================================================================
    # SCANNER SUPPORT METHODS
    # These methods are required for EP scanner compatibility
    # ==========================================================================
    
    def get_gainers(self) -> List[Dict]:
        """
        Get top gainers (simulated from loaded data).
        
        Returns loaded symbols with their current day's change as gainers.
        This allows the EP scanner to find candidates in simulation mode.
        """
        gainers = []
        
        if not self._sim_clock:
            return gainers
        
        sim_date = self._sim_clock.get_trading_day()
        
        for symbol, bars in self._data.items():
            # Find today's bar and yesterday's bar
            today_bar = None
            yesterday_bar = None
            
            for i, bar in enumerate(bars):
                if bar.date == sim_date:
                    today_bar = bar
                    if i > 0:
                        yesterday_bar = bars[i - 1]
                    break
                elif bar.date < sim_date:
                    yesterday_bar = bar
            
            if today_bar and yesterday_bar:
                # Calculate change
                change = today_bar.close - yesterday_bar.close
                change_pct = (change / yesterday_bar.close) * 100 if yesterday_bar.close > 0 else 0
                
                if change_pct > 0:  # Only include positive changers
                    gainers.append({
                        "symbol": symbol,
                        "name": symbol,
                        "price": today_bar.close,
                        "change": change,
                        "change_percent": change_pct,
                    })
        
        # Sort by change percent descending
        gainers.sort(key=lambda x: x["change_percent"], reverse=True)
        
        return gainers
    
    def get_actives(self) -> List[Dict]:
        """
        Get most active stocks (simulated from loaded data).
        
        Returns loaded symbols sorted by volume.
        """
        actives = []
        
        if not self._sim_clock:
            return actives
        
        sim_date = self._sim_clock.get_trading_day()
        
        for symbol, bars in self._data.items():
            for bar in bars:
                if bar.date == sim_date:
                    actives.append({
                        "symbol": symbol,
                        "name": symbol,
                        "price": bar.close,
                        "volume": bar.volume,
                        "change": 0,
                        "change_percent": 0,
                    })
                    break
        
        # Sort by volume descending
        actives.sort(key=lambda x: x["volume"], reverse=True)
        
        return actives
    
    def has_recent_catalyst(self, symbol: str, days: int = 5) -> tuple:
        """
        Simulate catalyst check for EP scanner.
        
        In simulation mode, we assume all loaded stocks have a catalyst
        (since we explicitly loaded them for testing).
        
        Returns:
            (has_catalyst, catalyst_type, description)
        """
        # In simulation, assume loaded data has a catalyst
        return (True, "earnings", f"Simulated catalyst for {symbol}")
    
    def has_upcoming_earnings(self, symbol: str, days: int = 3) -> tuple:
        """
        Check for upcoming earnings (simulated).
        
        Returns:
            (has_upcoming, earnings_date)
        """
        # In simulation, no upcoming earnings risk
        return (False, None)
    
    def has_recent_earnings(self, symbol: str, days: int = 5) -> tuple:
        """
        Check for recent past earnings (simulated).
        
        Returns:
            (has_earnings, earnings_date)
        """
        # In simulation, assume recent earnings
        sim_date = self._sim_clock.get_trading_day() if self._sim_clock else None
        return (True, sim_date)
    
    def build_ep_session_snapshot(self, symbol: str) -> Optional[Dict]:
        """
        Build EP session snapshot for scanner.
        
        This provides the data structure expected by EPScannerService.
        """
        if symbol not in self._data:
            return None
        
        bars = self._data[symbol]
        if not bars:
            return None
        
        # Get bar for sim date
        sim_date = self._sim_clock.get_trading_day() if self._sim_clock else None
        today_bar = None
        yesterday_bar = None
        
        for i, bar in enumerate(bars):
            if sim_date and bar.date == sim_date:
                today_bar = bar
                if i > 0:
                    yesterday_bar = bars[i - 1]
                break
            elif not sim_date or bar.date <= sim_date:
                yesterday_bar = today_bar
                today_bar = bar
        
        if not today_bar:
            today_bar = bars[-1]
        if not yesterday_bar and len(bars) > 1:
            yesterday_bar = bars[-2]
        
        if not yesterday_bar:
            return None
        
        # Calculate average volume
        recent_bars = bars[-20:] if len(bars) >= 20 else bars
        avg_volume = sum(b.volume for b in recent_bars) / len(recent_bars) if recent_bars else 0
        
        return {
            "symbol": symbol,
            "yesterday_close": yesterday_bar.close,
            "session_open": today_bar.open,
            "session_high": today_bar.high,
            "session_low": today_bar.low,
            "last_price": today_bar.close,
            "session_volume": today_bar.volume,
            "avg_daily_volume": avg_volume,
        }
    
    def get_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        """
        Calculate ATR for symbol.
        """
        bars = self.get_daily_bars(symbol, days=period + 5)
        if not bars or len(bars) < period:
            return None
        
        tr_values = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i - 1].close
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
        
        if not tr_values:
            return None
        
        return sum(tr_values[-period:]) / min(period, len(tr_values))
    
    def get_adr_percent(self, symbol: str, period: int = 14) -> Optional[float]:
        """
        Calculate average daily range as percentage.
        """
        bars = self.get_daily_bars(symbol, days=period + 5)
        if not bars or len(bars) < period:
            return None
        
        adr_values = []
        for bar in bars[-period:]:
            if bar.close > 0:
                adr_pct = ((bar.high - bar.low) / bar.close) * 100
                adr_values.append(adr_pct)
        
        if not adr_values:
            return None
        
        return sum(adr_values) / len(adr_values)
    
    def get_opening_range(self, symbol: str, timeframe_minutes: int = 5) -> Optional[tuple]:
        """
        Get opening range (simulated from daily bar).
        
        In simulation, we use the daily open +/- small range.
        Returns: (high, low)
        """
        bars = self.get_daily_bars(symbol, days=1)
        if not bars:
            return None
        
        bar = bars[0]
        # Simulate opening range as small % of day's range
        day_range = bar.high - bar.low
        or_range = day_range * 0.2  # 20% of day's range
        
        or_high = bar.open + or_range / 2
        or_low = bar.open - or_range / 2
        
        return (or_high, or_low)
    
    @property
    def fmp(self):
        """
        Return self as FMP adapter proxy for EP scanner compatibility.
        
        The EP scanner calls self.market_data.fmp.get_etf_symbols().
        """
        return self
    
    def get_etf_symbols(self) -> set:
        """Return empty set (no ETFs to filter in simulation)."""
        return set()
    
    def screen_stocks(self, threshold: float = 0.0, **kwargs) -> List[Dict]:
        """
        Screen stocks for breakout scanner compatibility.
        
        Returns loaded symbols with basic screening info.
        In simulation, returns all loaded symbols as candidates.
        
        Args:
            threshold: Minimum change threshold (ignored in sim)
            **kwargs: Additional filters (min_price, min_market_cap, etc.) - ignored in sim
        """
        results = []
        for symbol in self._data.keys():
            bars = self.get_daily_bars(symbol, days=20)
            if not bars:
                continue
            
            # Calculate basic metrics
            latest_bar = bars[0]
            avg_volume = sum(b.volume for b in bars) / len(bars) if bars else 0
            
            results.append({
                "symbol": symbol,
                "price": latest_bar.close,
                "volume": latest_bar.volume,
                "avg_volume": avg_volume,
                "change_percent": 0,  # Would need yesterday's close
            })
        
        return results


# Global instance
_mock_market_data: Optional[MockMarketData] = None


def get_mock_market_data() -> MockMarketData:
    """Get or create global mock market data provider."""
    global _mock_market_data
    if _mock_market_data is None:
        _mock_market_data = MockMarketData()
    return _mock_market_data


def reset_mock_market_data() -> MockMarketData:
    """Reset global mock market data provider."""
    global _mock_market_data
    _mock_market_data = MockMarketData()
    return _mock_market_data
