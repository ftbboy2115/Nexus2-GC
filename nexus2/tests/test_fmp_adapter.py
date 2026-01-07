"""
Tests for FMP Adapter

Tests the FMP market data adapter with mocked HTTP responses.
"""

import sys
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

# Mock httpx before importing FMPAdapter to avoid slow network initialization
_mock_httpx = MagicMock()
_mock_httpx.Client = MagicMock
sys.modules['httpx'] = _mock_httpx

from nexus2.adapters.market_data.fmp_adapter import FMPAdapter, FMPConfig
from nexus2.adapters.market_data.protocol import Quote, OHLCV, StockInfo


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def fmp_config():
    """FMP configuration."""
    return FMPConfig(
        api_key="test_api_key",
        base_url="https://test.financialmodelingprep.com/api/v3",
    )


@pytest.fixture
def fmp_adapter(fmp_config):
    """FMP adapter with test config."""
    return FMPAdapter(fmp_config)


@pytest.fixture
def mock_quote_response():
    """Mock FMP quote response."""
    return [
        {
            "symbol": "AAPL",
            "price": 150.25,
            "change": 2.50,
            "changesPercentage": 1.69,
            "volume": 75000000,
            "open": 148.00,
            "dayHigh": 151.50,
            "dayLow": 147.80,
        }
    ]


@pytest.fixture
def mock_gainers_response():
    """Mock FMP gainers response."""
    return [
        {"symbol": "AAPL", "name": "Apple Inc", "price": 150.0, "change": 15.0, "changesPercentage": 11.0},
        {"symbol": "MSFT", "name": "Microsoft", "price": 380.0, "change": 30.0, "changesPercentage": 8.5},
        {"symbol": "TSLA", "name": "Tesla", "price": 250.0, "change": 20.0, "changesPercentage": 8.0},
    ]


@pytest.fixture
def mock_etf_list_response():
    """Mock FMP ETF list response."""
    return [
        {"symbol": "SPY", "name": "SPDR S&P 500"},
        {"symbol": "QQQ", "name": "Invesco QQQ"},
        {"symbol": "AGQ", "name": "ProShares Ultra Silver"},
        {"symbol": "IWM", "name": "iShares Russell 2000"},
    ]


@pytest.fixture
def mock_historical_response():
    """Mock FMP historical price response."""
    # Generate valid dates - need 50+ bars
    historical = [
        {"date": "2024-01-05", "open": 148.0, "high": 150.0, "low": 147.0, "close": 149.0, "volume": 50000000},
        {"date": "2024-01-04", "open": 147.0, "high": 149.0, "low": 146.0, "close": 148.0, "volume": 48000000},
        {"date": "2024-01-03", "open": 146.0, "high": 148.0, "low": 145.0, "close": 147.0, "volume": 52000000},
    ]
    # Add December dates (31 days)
    for i in range(1, 32):
        historical.append({
            "date": f"2023-12-{i:02d}", "open": 145.0, "high": 147.0, "low": 144.0, "close": 146.0, "volume": 45000000
        })
    # Add November dates to get 50+
    for i in range(15, 31):
        historical.append({
            "date": f"2023-11-{i:02d}", "open": 144.0, "high": 146.0, "low": 143.0, "close": 145.0, "volume": 44000000
        })
    return {"symbol": "AAPL", "historical": historical}


# ============================================================================
# Test: get_quote
# ============================================================================

class TestGetQuote:
    """Tests for FMPAdapter.get_quote()"""
    
    def test_returns_quote_object(self, fmp_adapter, mock_quote_response):
        """Should return Quote object with correct data."""
        with patch.object(fmp_adapter, '_get', return_value=mock_quote_response):
            quote = fmp_adapter.get_quote("AAPL")
            
            assert quote is not None
            assert quote.symbol == "AAPL"
            assert quote.price == Decimal("150.25")
            assert quote.change == Decimal("2.50")
            assert quote.volume == 75000000
    
    def test_returns_none_on_empty_response(self, fmp_adapter):
        """Should return None if no data returned."""
        with patch.object(fmp_adapter, '_get', return_value=[]):
            quote = fmp_adapter.get_quote("INVALID")
            assert quote is None
    
    def test_returns_none_on_error(self, fmp_adapter):
        """Should return None on API error."""
        with patch.object(fmp_adapter, '_get', return_value=None):
            quote = fmp_adapter.get_quote("AAPL")
            assert quote is None


# ============================================================================
# Test: get_gainers
# ============================================================================

class TestGetGainers:
    """Tests for FMPAdapter.get_gainers()"""
    
    def test_returns_list_of_gainers(self, fmp_adapter, mock_gainers_response):
        """Should return list of gainer dicts."""
        with patch.object(fmp_adapter, '_get', return_value=mock_gainers_response):
            gainers = fmp_adapter.get_gainers()
            
            assert len(gainers) == 3
            assert gainers[0]["symbol"] == "AAPL"
            assert gainers[0]["price"] == Decimal("150.0")
            assert gainers[0]["change_percent"] == Decimal("11.0")
    
    def test_returns_empty_on_error(self, fmp_adapter):
        """Should return empty list on API error."""
        with patch.object(fmp_adapter, '_get', return_value=None):
            gainers = fmp_adapter.get_gainers()
            assert gainers == []


# ============================================================================
# Test: get_etf_symbols
# ============================================================================

class TestGetETFSymbols:
    """Tests for FMPAdapter.get_etf_symbols()"""
    
    def test_returns_set_of_symbols(self, fmp_adapter, mock_etf_list_response):
        """Should return set of ETF symbols."""
        with patch.object(fmp_adapter, '_get', return_value=mock_etf_list_response):
            etf_set = fmp_adapter.get_etf_symbols()
            
            assert isinstance(etf_set, set)
            assert "SPY" in etf_set
            assert "QQQ" in etf_set
            assert "AGQ" in etf_set
            assert len(etf_set) == 4
    
    def test_returns_empty_set_on_error(self, fmp_adapter):
        """Should return empty set on API error."""
        with patch.object(fmp_adapter, '_get', return_value=None):
            etf_set = fmp_adapter.get_etf_symbols()
            assert etf_set == set()


# ============================================================================
# Test: is_etf
# ============================================================================

class TestIsETF:
    """Tests for FMPAdapter.is_etf()"""
    
    def test_identifies_etf(self, fmp_adapter, mock_etf_list_response):
        """Should correctly identify ETFs."""
        with patch.object(fmp_adapter, '_get', return_value=mock_etf_list_response):
            etf_set = fmp_adapter.get_etf_symbols()
            
            assert fmp_adapter.is_etf("SPY", etf_set) is True
            assert fmp_adapter.is_etf("AGQ", etf_set) is True
    
    def test_identifies_non_etf(self, fmp_adapter, mock_etf_list_response):
        """Should correctly identify non-ETFs."""
        with patch.object(fmp_adapter, '_get', return_value=mock_etf_list_response):
            etf_set = fmp_adapter.get_etf_symbols()
            
            assert fmp_adapter.is_etf("AAPL", etf_set) is False
            assert fmp_adapter.is_etf("TSLA", etf_set) is False


# ============================================================================
# Test: get_daily_bars
# ============================================================================

class TestGetDailyBars:
    """Tests for FMPAdapter.get_daily_bars()"""
    
    def test_returns_ohlcv_list(self, fmp_adapter, mock_historical_response):
        """Should return list of OHLCV objects."""
        with patch.object(fmp_adapter, '_get', return_value=mock_historical_response):
            bars = fmp_adapter.get_daily_bars("AAPL", limit=60)
            
            assert bars is not None
            assert len(bars) >= 50
            assert isinstance(bars[0], OHLCV)
    
    def test_returns_data_even_with_few_bars(self, fmp_adapter):
        """Should return whatever bars are available (consumer decides if enough)."""
        short_response = {
            "symbol": "AAPL",
            "historical": [
                {"date": "2024-01-05", "open": 148.0, "high": 150.0, "low": 147.0, "close": 149.0, "volume": 50000000},
            ] * 10  # Only 10 bars
        }
        with patch.object(fmp_adapter, '_get', return_value=short_response):
            bars = fmp_adapter.get_daily_bars("AAPL", limit=60)
            # Adapter returns bars, consumer decides if sufficient
            assert bars is not None
            assert len(bars) == 10
    
    def test_returns_none_on_missing_historical(self, fmp_adapter):
        """Should return None if historical key missing."""
        with patch.object(fmp_adapter, '_get', return_value={"symbol": "AAPL"}):
            bars = fmp_adapter.get_daily_bars("AAPL", limit=60)
            assert bars is None
    
    def test_handles_none_historical(self, fmp_adapter):
        """Should handle None historical gracefully."""
        with patch.object(fmp_adapter, '_get', return_value={"symbol": "AAPL", "historical": None}):
            bars = fmp_adapter.get_daily_bars("AAPL", limit=60)
            assert bars is None


# ============================================================================
# Test: filter_by_change
# ============================================================================

class TestFilterByChange:
    """Tests for FMPAdapter.filter_by_change()"""
    
    def test_filters_by_change_percent(self, fmp_adapter):
        """Should filter symbols by change percentage."""
        mock_quotes = {
            "AAPL": Quote(symbol="AAPL", price=Decimal("150"), change=Decimal("15"), 
                         change_percent=Decimal("11.0"), volume=1000000, timestamp=datetime.now()),
            "MSFT": Quote(symbol="MSFT", price=Decimal("380"), change=Decimal("5"),
                         change_percent=Decimal("1.3"), volume=500000, timestamp=datetime.now()),
            "TSLA": Quote(symbol="TSLA", price=Decimal("250"), change=Decimal("12"),
                         change_percent=Decimal("5.0"), volume=2000000, timestamp=datetime.now()),
        }
        
        with patch.object(fmp_adapter, 'get_quotes_batch', return_value=mock_quotes):
            passing = fmp_adapter.filter_by_change(["AAPL", "MSFT", "TSLA"], min_change_pct=3.0)
            
            assert "AAPL" in passing  # 11% > 3%
            assert "TSLA" in passing  # 5% > 3%
            assert "MSFT" not in passing  # 1.3% < 3%
