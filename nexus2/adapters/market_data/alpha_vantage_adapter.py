"""
Alpha Vantage Market Data Adapter

Provides market data from Alpha Vantage API as a 4th validation source.
Disabled by default until ALPHA_VANTAGE_API_KEY is configured.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List

import httpx

from nexus2.adapters.market_data.protocol import (
    MarketDataProvider,
    Quote,
)

# Import centralized config (auto-loads .env)
from nexus2 import config as app_config


@dataclass
class AlphaVantageConfig:
    """Configuration for Alpha Vantage API."""
    api_key: str
    base_url: str = "https://www.alphavantage.co"
    timeout: float = 10.0
    rate_limit_per_minute: int = 150  # Premium tier


class AlphaVantageAdapter(MarketDataProvider):
    """
    Alpha Vantage Market Data Adapter.
    
    Used as a 4th validation source for quotes when Alpaca/FMP/Schwab disagree.
    Disabled until ALPHA_VANTAGE_API_KEY is set in environment.
    
    API Docs: https://www.alphavantage.co/documentation/
    """
    
    def __init__(self, config: Optional[AlphaVantageConfig] = None):
        # Get API key from config or environment
        api_key = None
        if config:
            api_key = config.api_key
        else:
            api_key = getattr(app_config, 'ALPHA_VANTAGE_API_KEY', None) or os.getenv('ALPHA_VANTAGE_API_KEY')
        
        if not api_key:
            self._enabled = False
            self._client = None
            print("[Alpha Vantage] Disabled - no API key configured")
            return
        
        self._enabled = True
        self.config = config or AlphaVantageConfig(api_key=api_key)
        self._client = httpx.Client(timeout=self.config.timeout)
        
        # Rate limiting
        self._calls: List[datetime] = []
        
        print(f"[Alpha Vantage] Enabled with {self.config.rate_limit_per_minute} req/min limit")
    
    def __del__(self):
        if self._client:
            self._client.close()
    
    @property
    def is_enabled(self) -> bool:
        """Check if adapter is enabled (has API key)."""
        return self._enabled
    
    def _record_call(self):
        """Record an API call for rate limiting."""
        now = datetime.now(timezone.utc)
        # Prune calls older than 60 seconds
        self._calls = [t for t in self._calls if (now - t).total_seconds() < 60]
        self._calls.append(now)
    
    def _get_remaining_calls(self) -> int:
        """Get remaining API calls this minute."""
        now = datetime.now(timezone.utc)
        self._calls = [t for t in self._calls if (now - t).total_seconds() < 60]
        return self.config.rate_limit_per_minute - len(self._calls)
    
    def _get(self, params: dict) -> Optional[dict]:
        """Make GET request to Alpha Vantage API."""
        if not self._enabled:
            return None
        
        if self._get_remaining_calls() <= 0:
            print("[Alpha Vantage] Rate limit reached, skipping request")
            return None
        
        params["apikey"] = self.config.api_key
        
        try:
            self._record_call()
            url = f"{self.config.base_url}/query"
            response = self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[Alpha Vantage] Request error: {e}")
            return None
    
    def get_quote(self, symbol: str) -> Optional[Quote]:
        """
        Get real-time quote for a symbol.
        
        Uses GLOBAL_QUOTE endpoint which includes pre-market data.
        
        Returns:
            Quote object or None if unavailable
        """
        if not self._enabled:
            return None
        
        data = self._get({
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
        })
        
        if not data or "Global Quote" not in data:
            # Check for error messages
            if data and "Note" in data:
                print(f"[Alpha Vantage] Rate limit message: {data['Note'][:100]}")
            elif data and "Error Message" in data:
                print(f"[Alpha Vantage] Error: {data['Error Message']}")
            return None
        
        quote_data = data["Global Quote"]
        
        if not quote_data or "05. price" not in quote_data:
            return None
        
        try:
            price = Decimal(quote_data.get("05. price", "0"))
            prev_close = Decimal(quote_data.get("08. previous close", "0"))
            change = Decimal(quote_data.get("09. change", "0"))
            volume = int(quote_data.get("06. volume", "0"))
            day_high = Decimal(quote_data.get("03. high", "0"))
            day_low = Decimal(quote_data.get("04. low", "0"))
            
            # Calculate change_percent
            change_percent = Decimal("0")
            if prev_close and prev_close > 0:
                change_percent = (change / prev_close * 100)
            
            return Quote(
                symbol=symbol,
                price=price,
                change=change,
                change_percent=change_percent,
                volume=volume,
                timestamp=datetime.now(timezone.utc),
                day_high=day_high,
                day_low=day_low,
                bid=None,  # Alpha Vantage GLOBAL_QUOTE doesn't include bid/ask
                ask=None,
            )
        except Exception as e:
            print(f"[Alpha Vantage] Parse error for {symbol}: {e}")
            return None
    
    def get_intraday_quote(self, symbol: str) -> Optional[Quote]:
        """
        Get intraday quote using TIME_SERIES_INTRADAY (more expensive).
        
        Use this if GLOBAL_QUOTE data seems stale.
        """
        if not self._enabled:
            return None
        
        data = self._get({
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": "1min",
            "outputsize": "compact",
        })
        
        if not data or "Time Series (1min)" not in data:
            return None
        
        time_series = data["Time Series (1min)"]
        if not time_series:
            return None
        
        # Get most recent bar
        latest_time = max(time_series.keys())
        bar = time_series[latest_time]
        
        try:
            price = Decimal(bar["4. close"])
            volume = int(bar["5. volume"])
            
            return Quote(
                symbol=symbol,
                price=price,
                bid=None,
                ask=None,
                volume=volume,
                timestamp=datetime.now(timezone.utc),
                day_high=Decimal(bar["2. high"]),
                day_low=Decimal(bar["3. low"]),
                open=Decimal(bar["1. open"]),
                prev_close=None,
                change=None,
                change_percent=None,
            )
        except Exception as e:
            print(f"[Alpha Vantage] Intraday parse error for {symbol}: {e}")
            return None
    
    def get_rate_stats(self) -> dict:
        """Get rate limit statistics."""
        return {
            "enabled": self._enabled,
            "calls_this_minute": len(self._calls),
            "remaining": self._get_remaining_calls() if self._enabled else 0,
            "limit_per_minute": self.config.rate_limit_per_minute if self._enabled else 0,
        }


# =============================================================================
# SINGLETON
# =============================================================================

_alpha_vantage_adapter: Optional[AlphaVantageAdapter] = None


def get_alpha_vantage_adapter() -> Optional[AlphaVantageAdapter]:
    """Get singleton Alpha Vantage adapter."""
    global _alpha_vantage_adapter
    if _alpha_vantage_adapter is None:
        _alpha_vantage_adapter = AlphaVantageAdapter()
    return _alpha_vantage_adapter if _alpha_vantage_adapter.is_enabled else None


def is_alpha_vantage_enabled() -> bool:
    """Check if Alpha Vantage is enabled without creating adapter."""
    api_key = getattr(app_config, 'ALPHA_VANTAGE_API_KEY', None) or os.getenv('ALPHA_VANTAGE_API_KEY')
    return bool(api_key)
