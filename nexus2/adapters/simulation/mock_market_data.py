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
        return {
            "symbols": self.get_symbols(),
            "bar_counts": {s: len(bars) for s, bars in self._data.items()},
            "current_prices": self._current_prices.copy(),
        }


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
