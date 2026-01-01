"""
Market Data Protocol

Defines the interface that all market data adapters must implement.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Protocol


@dataclass
class OHLCV:
    """Single OHLCV bar."""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass
class Quote:
    """Real-time quote data."""
    symbol: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    volume: int
    timestamp: datetime


@dataclass
class StockInfo:
    """Basic stock information."""
    symbol: str
    name: str
    exchange: str
    market_cap: Decimal
    float_shares: Optional[int]
    avg_volume_20d: int
    sector: Optional[str]
    industry: Optional[str]


class MarketDataProvider(Protocol):
    """
    Protocol defining the market data interface.
    
    All market data adapters (FMP, Alpaca, etc.) must implement this.
    """
    
    def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get real-time quote for a symbol."""
        ...
    
    def get_quotes_batch(self, symbols: List[str]) -> dict[str, Quote]:
        """Get quotes for multiple symbols."""
        ...
    
    def get_daily_bars(
        self, 
        symbol: str, 
        limit: int = 60
    ) -> Optional[List[OHLCV]]:
        """Get daily OHLCV bars."""
        ...
    
    def get_intraday_bars(
        self, 
        symbol: str, 
        timeframe: str = "1Min",
        limit: int = 1000
    ) -> Optional[List[OHLCV]]:
        """Get intraday OHLCV bars."""
        ...
    
    def get_stock_info(self, symbol: str) -> Optional[StockInfo]:
        """Get basic stock information."""
        ...
    
    def get_prev_close(self, symbol: str) -> Optional[Decimal]:
        """Get previous day's closing price."""
        ...
    
    def get_atr(self, symbol: str, period: int = 14) -> Optional[Decimal]:
        """Calculate Average True Range."""
        ...
    
    def get_sma(self, symbol: str, period: int) -> Optional[Decimal]:
        """Get Simple Moving Average."""
        ...
    
    def get_ema(self, symbol: str, period: int) -> Optional[Decimal]:
        """Get Exponential Moving Average."""
        ...
