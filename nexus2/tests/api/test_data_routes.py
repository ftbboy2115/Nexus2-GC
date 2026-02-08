"""
Tests for Data Explorer API Routes (data_routes.py)

Tests the /data/* endpoints for the Data Explorer UI including
pagination, filtering, sorting, and distinct value endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from nexus2.api.main import create_app


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def client():
    """Test client with fresh app."""
    app = create_app()
    with TestClient(app) as client:
        yield client


# ============================================================================
# Warrior Scan History Tests
# ============================================================================

@pytest.mark.timeout(0)  # Disable timeout - signal incompatible with TestClient
class TestWarriorScanHistory:
    """Tests for /data/warrior-scan-history endpoint."""
    
    def test_warrior_scan_history_returns_200(self, client):
        """Warrior scan history endpoint returns 200."""
        response = client.get("/data/warrior-scan-history")
        
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
    
    def test_warrior_scan_history_pagination(self, client):
        """Warrior scan history supports pagination."""
        response = client.get("/data/warrior-scan-history?limit=10&offset=0")
        
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0
    
    def test_warrior_scan_history_distinct_symbol(self, client):
        """Distinct endpoint returns unique symbols."""
        response = client.get("/data/warrior-scan-history/distinct?column=symbol")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "symbol"
        assert "values" in data
        assert isinstance(data["values"], list)
    
    def test_warrior_scan_history_distinct_result(self, client):
        """Distinct endpoint returns unique results (PASS/FAIL)."""
        response = client.get("/data/warrior-scan-history/distinct?column=result")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "result"
        assert "values" in data


# ============================================================================
# NAC Scan History Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestNACScanHistory:
    """Tests for /data/scan-history endpoint."""
    
    def test_nac_scan_history_returns_200(self, client):
        """NAC scan history endpoint returns 200."""
        response = client.get("/data/scan-history")
        
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data
    
    def test_nac_scan_history_distinct(self, client):
        """Distinct endpoint for NAC scan history works."""
        response = client.get("/data/scan-history/distinct?column=symbol")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "symbol"
        assert "values" in data


# ============================================================================
# Catalyst Audits Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestCatalystAudits:
    """Tests for /data/catalyst-audits endpoint."""
    
    def test_catalyst_audits_returns_200(self, client):
        """Catalyst audits endpoint returns 200."""
        response = client.get("/data/catalyst-audits")
        
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
    
    def test_catalyst_audits_with_filters(self, client):
        """Catalyst audits supports date and time filters."""
        response = client.get(
            "/data/catalyst-audits?date_from=2026-01-01&date_to=2026-12-31"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
    
    def test_catalyst_audits_distinct_symbol(self, client):
        """Distinct endpoint returns unique symbols."""
        response = client.get("/data/catalyst-audits/distinct?column=symbol")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "symbol"
        assert "values" in data
    
    def test_catalyst_audits_distinct_regex_result(self, client):
        """Distinct endpoint returns unique regex results."""
        response = client.get("/data/catalyst-audits/distinct?column=regex_result")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "regex_result"


# ============================================================================
# AI Comparisons Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestAIComparisons:
    """Tests for /data/ai-comparisons endpoint."""
    
    def test_ai_comparisons_returns_200(self, client):
        """AI comparisons endpoint returns 200."""
        response = client.get("/data/ai-comparisons")
        
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
    
    def test_ai_comparisons_sorting(self, client):
        """AI comparisons supports sorting."""
        response = client.get("/data/ai-comparisons?sort_by=timestamp&sort_dir=desc")
        
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
    
    def test_ai_comparisons_distinct_symbol(self, client):
        """Distinct endpoint returns unique symbols."""
        response = client.get("/data/ai-comparisons/distinct?column=symbol")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "symbol"
        assert "values" in data
    
    def test_ai_comparisons_distinct_flash_valid(self, client):
        """Distinct endpoint returns unique flash_valid values."""
        response = client.get("/data/ai-comparisons/distinct?column=flash_valid")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "flash_valid"


# ============================================================================
# Trade Events Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestTradeEvents:
    """Tests for /data/trade-events endpoint."""
    
    def test_trade_events_returns_200(self, client):
        """Trade events endpoint returns 200."""
        response = client.get("/data/trade-events")
        
        assert response.status_code == 200
        data = response.json()
        assert "events" in data  # API returns 'events' not 'entries'
        assert "total" in data
    
    def test_trade_events_distinct(self, client):
        """Distinct endpoint for trade events works."""
        response = client.get("/data/trade-events/distinct?column=symbol")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "symbol"


# ============================================================================
# Warrior Trades Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestWarriorTrades:
    """Tests for /data/warrior-trades endpoint."""
    
    def test_warrior_trades_returns_200(self, client):
        """Warrior trades endpoint returns 200."""
        response = client.get("/data/warrior-trades")
        
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data or "trades" in data
        assert "total" in data
    
    def test_warrior_trades_distinct(self, client):
        """Distinct endpoint for warrior trades works."""
        response = client.get("/data/warrior-trades/distinct?column=symbol")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "symbol"


# ============================================================================
# NAC Trades Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestNACTrades:
    """Tests for /data/nac-trades endpoint."""
    
    def test_nac_trades_returns_200(self, client):
        """NAC trades endpoint returns 200."""
        response = client.get("/data/nac-trades")
        
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
    
    def test_nac_trades_distinct(self, client):
        """Distinct endpoint for NAC trades works."""
        response = client.get("/data/nac-trades/distinct?column=symbol")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "symbol"


# ============================================================================
# Quote Audits Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestQuoteAudits:
    """Tests for /data/quote-audits endpoint."""
    
    def test_quote_audits_returns_200(self, client):
        """Quote audits endpoint returns 200."""
        response = client.get("/data/quote-audits")
        
        assert response.status_code == 200
        data = response.json()
        assert "audits" in data  # API returns 'audits' not 'entries'
        assert "total" in data
    
    def test_quote_audits_distinct(self, client):
        """Distinct endpoint for quote audits works."""
        response = client.get("/data/quote-audits/distinct?column=symbol")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "symbol"


# ============================================================================
# Validation Log Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestValidationLog:
    """Tests for /data/validation-log endpoint."""
    
    def test_validation_log_returns_200(self, client):
        """Validation log endpoint returns 200."""
        response = client.get("/data/validation-log")
        
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data
    
    def test_validation_log_distinct(self, client):
        """Distinct endpoint for validation log works."""
        response = client.get("/data/validation-log/distinct?column=symbol")
        
        assert response.status_code == 200
        data = response.json()
        assert data["column"] == "symbol"


# ============================================================================
# ET→UTC Date Filter Conversion Tests (Wave 2)
# ============================================================================

@pytest.mark.timeout(0)
class TestDateFilterETConversion:
    """Tests for ET→UTC date filter conversion (Wave 1 Item 4).
    
    Verifies that warrior-trades, nac-trades, and quote-audits endpoints
    correctly accept date_from/date_to parameters without errors after
    the ET→UTC conversion fix.
    """
    
    def test_warrior_trades_date_filter_accepts_dates(self, client):
        """Warrior trades endpoint accepts date_from and date_to params."""
        response = client.get("/data/warrior-trades?date_from=2026-02-01&date_to=2026-02-08")
        assert response.status_code == 200
    
    def test_nac_trades_date_filter_accepts_dates(self, client):
        """NAC trades endpoint accepts date_from and date_to params."""
        response = client.get("/data/nac-trades?date_from=2026-02-01&date_to=2026-02-08")
        assert response.status_code == 200
    
    def test_quote_audits_date_filter_accepts_dates(self, client):
        """Quote audits endpoint accepts date_from and date_to params."""
        response = client.get("/data/quote-audits?date_from=2026-02-01&date_to=2026-02-08")
        assert response.status_code == 200
    
    def test_warrior_trades_invalid_date_raises_error(self, client):
        """Invalid date format causes a server error (known bug).
        
        BUG: data_routes.py does not handle malformed date_from/date_to values.
        An invalid date string like 'not-a-date' causes an unhandled ValueError
        in strptime, resulting in a 500. Ideally this should return 400 or skip
        the filter gracefully.
        """
        with pytest.raises(ValueError):
            client.get("/data/warrior-trades?date_from=not-a-date")
    
    def test_warrior_trades_single_date_filter(self, client):
        """Only date_from without date_to works."""
        response = client.get("/data/warrior-trades?date_from=2026-02-08")
        assert response.status_code == 200
    
    def test_nac_trades_single_date_filter(self, client):
        """Only date_to without date_from works for NAC trades."""
        response = client.get("/data/nac-trades?date_to=2026-02-08")
        assert response.status_code == 200
    
    def test_quote_audits_single_date_filter(self, client):
        """Only date_from without date_to works for quote audits."""
        response = client.get("/data/quote-audits?date_from=2026-02-01")
        assert response.status_code == 200
