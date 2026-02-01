"""
Technical Indicator Service

Provides VWAP, EMA, and MACD calculations using pandas-ta.
Based on Ross Cameron (Warrior Trading) methodology.
"""

import pandas as pd
import pandas_ta as ta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TechnicalSnapshot:
    """Technical indicator snapshot for a symbol."""
    symbol: str
    vwap: Optional[Decimal] = None
    ema_9: Optional[Decimal] = None
    ema_20: Optional[Decimal] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    macd_crossover: str = "neutral"  # "bullish", "bearish", "neutral"
    current_price: Optional[Decimal] = None
    data_insufficient: bool = False  # True if not enough candles for calculation (AUDIT FLAG)
    
    @property
    def is_above_vwap(self) -> bool:
        """Check if current price is above VWAP."""
        if self.current_price and self.vwap:
            return self.current_price >= self.vwap
        return True  # Default to True if data unavailable
    
    @property
    def is_above_ema9(self) -> bool:
        """Check if current price is above 9 EMA."""
        if self.current_price and self.ema_9:
            return self.current_price >= self.ema_9 * Decimal("0.99")  # 1% tolerance
        return True
    
    @property
    def is_macd_bullish(self) -> bool:
        """Check if MACD is bullish (histogram > 0 or crossover)."""
        return self.macd_crossover == "bullish" or (
            self.macd_histogram is not None and self.macd_histogram > 0
        )


class TechnicalService:
    """
    Calculate technical indicators using pandas-ta.
    
    Provides:
    - VWAP (Volume Weighted Average Price)
    - EMA (9 and 20 period)
    - MACD (12/26/9)
    """
    
    def get_snapshot(
        self,
        symbol: str,
        candles: List[Dict[str, Any]],
        current_price: Optional[Decimal] = None,
    ) -> TechnicalSnapshot:
        """
        Get all technical indicators for a symbol from candle data.
        
        Args:
            symbol: Stock symbol
            candles: List of candle dicts with keys: open, high, low, close, volume
            current_price: Current price for comparison
        
        Returns:
            TechnicalSnapshot with all indicators
        """
        if not candles or len(candles) < 5:
            logger.warning(f"[Technical] {symbol}: INSUFFICIENT DATA - only {len(candles) if candles else 0} candles (need 5+ for indicators)")
            # Return snapshot with explicit flag so callers know data was insufficient
            return TechnicalSnapshot(symbol=symbol, current_price=current_price, data_insufficient=True)
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(candles)
            
            # Ensure required columns exist
            required = ['high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required):
                logger.warning(f"[Technical] {symbol}: Missing required columns")
                return TechnicalSnapshot(symbol=symbol, current_price=current_price)
            
            # Convert to numeric
            for col in required:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Check for 'open' column for proper VWAP (HLCV is bare minimum)
            if 'open' in df.columns:
                df['open'] = pd.to_numeric(df['open'], errors='coerce')
            
            # Set DatetimeIndex for pandas-ta VWAP requirement
            # If candles have timestamp, use it; otherwise create synthetic timestamps
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp')
            else:
                # Create synthetic 5-min intervals for VWAP anchor
                df.index = pd.date_range(
                    start='2026-01-01 09:30:00',
                    periods=len(df),
                    freq='5min'
                )
            
            # Calculate VWAP (now with proper DatetimeIndex)
            vwap = None
            try:
                vwap_series = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
                if vwap_series is not None and not vwap_series.empty:
                    vwap = Decimal(str(vwap_series.iloc[-1]))
            except Exception as e:
                logger.debug(f"[Technical] {symbol}: VWAP calc failed: {e}")
            
            # Calculate EMAs
            ema_9 = None
            ema_20 = None
            try:
                ema_9_series = ta.ema(df['close'], length=9)
                if ema_9_series is not None and not ema_9_series.empty:
                    ema_9 = Decimal(str(ema_9_series.iloc[-1]))
                
                ema_20_series = ta.ema(df['close'], length=20)
                if ema_20_series is not None and not ema_20_series.empty:
                    ema_20 = Decimal(str(ema_20_series.iloc[-1]))
            except Exception as e:
                logger.debug(f"[Technical] {symbol}: EMA calc failed: {e}")
            
            # Calculate MACD
            macd_line = None
            macd_signal_val = None
            macd_hist = None
            crossover = "neutral"
            try:
                macd_df = ta.macd(df['close'], fast=12, slow=26, signal=9)
                if macd_df is not None and not macd_df.empty:
                    # Column names from pandas-ta
                    macd_col = 'MACD_12_26_9'
                    signal_col = 'MACDs_12_26_9'
                    hist_col = 'MACDh_12_26_9'
                    
                    if macd_col in macd_df.columns:
                        macd_line = float(macd_df[macd_col].iloc[-1])
                    if signal_col in macd_df.columns:
                        macd_signal_val = float(macd_df[signal_col].iloc[-1])
                    if hist_col in macd_df.columns:
                        macd_hist = float(macd_df[hist_col].iloc[-1])
                        
                        # Detect crossover
                        if len(macd_df) >= 2:
                            prev_hist = float(macd_df[hist_col].iloc[-2])
                            if prev_hist < 0 and macd_hist > 0:
                                crossover = "bullish"
                            elif prev_hist > 0 and macd_hist < 0:
                                crossover = "bearish"
            except Exception as e:
                logger.debug(f"[Technical] {symbol}: MACD calc failed: {e}")
            
            return TechnicalSnapshot(
                symbol=symbol,
                vwap=vwap,
                ema_9=ema_9,
                ema_20=ema_20,
                macd_line=macd_line,
                macd_signal=macd_signal_val,
                macd_histogram=macd_hist,
                macd_crossover=crossover,
                current_price=current_price,
            )
            
        except Exception as e:
            logger.error(f"[Technical] {symbol}: Snapshot failed: {e}")
            return TechnicalSnapshot(symbol=symbol, current_price=current_price)
    
    def get_swing_low(
        self,
        candles: List[Dict[str, Any]],
        lookback: int = 5,
    ) -> Optional[Decimal]:
        """
        Get swing low (lowest low) from recent candles.
        
        Args:
            candles: List of candle dicts
            lookback: Number of candles to look back
        
        Returns:
            Swing low price or None
        """
        if not candles or len(candles) < 2:
            return None
        
        try:
            df = pd.DataFrame(candles)
            df['low'] = pd.to_numeric(df['low'], errors='coerce')
            swing_low = df['low'].tail(lookback).min()
            return Decimal(str(swing_low)) if pd.notna(swing_low) else None
        except Exception:
            return None


# Singleton instance
_technical_service: Optional[TechnicalService] = None


def get_technical_service() -> TechnicalService:
    """Get or create singleton TechnicalService."""
    global _technical_service
    if _technical_service is None:
        _technical_service = TechnicalService()
    return _technical_service
