"""
Tests for Trading Notes API Routes (trading_notes_routes.py)

Tests the /trading-notes/* endpoints for the Trading Notes Calendar feature.
Covers CRUD operations: create, read, update, delete, list, and dates-with-entries.
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


@pytest.fixture
def test_date():
    """Test date for isolation."""
    return "2099-12-31"  # Far future date to avoid conflicts


@pytest.fixture
def sample_note():
    """Sample note data for tests."""
    return {
        "ross_trades": 3,
        "ross_pnl": "+$1500",
        "ross_notes": "Great day for momentum plays",
        "warrior_trades": 2,
        "warrior_pnl": "+$800",
        "warrior_notes": "Bot caught PMH breakout",
        "market_context": "SPY gap up, strong momentum",
        "lessons": "Wait for confirmation on extended stocks"
    }


# ============================================================================
# Trading Notes CRUD Tests
# ============================================================================

@pytest.mark.timeout(0)  # Disable timeout - signal incompatible with TestClient
class TestTradingNotesCRUD:
    """Tests for trading notes CRUD operations."""
    
    def test_create_note(self, client, test_date, sample_note):
        """PUT creates new note successfully."""
        # Ensure clean state - delete if exists
        client.delete(f"/trading-notes/{test_date}")
        
        # Create new note
        response = client.put(f"/trading-notes/{test_date}", json=sample_note)
        
        assert response.status_code == 200
        data = response.json()
        assert "note" in data
        assert data["note"]["date"] == test_date
        assert data["note"]["ross_trades"] == sample_note["ross_trades"]
        assert data["note"]["ross_pnl"] == sample_note["ross_pnl"]
        assert data["note"]["warrior_trades"] == sample_note["warrior_trades"]
        assert data["note"]["market_context"] == sample_note["market_context"]
        
        # Cleanup
        client.delete(f"/trading-notes/{test_date}")
    
    def test_get_note(self, client, test_date, sample_note):
        """GET returns existing note."""
        # Create note first
        client.put(f"/trading-notes/{test_date}", json=sample_note)
        
        # Fetch it
        response = client.get(f"/trading-notes/{test_date}")
        
        assert response.status_code == 200
        data = response.json()
        assert "note" in data
        assert data["note"] is not None
        assert data["note"]["date"] == test_date
        assert data["note"]["ross_notes"] == sample_note["ross_notes"]
        
        # Cleanup
        client.delete(f"/trading-notes/{test_date}")
    
    def test_get_note_not_found(self, client):
        """GET non-existent date returns null note (not 404)."""
        # Use a date guaranteed to not exist
        response = client.get("/trading-notes/1900-01-01")
        
        assert response.status_code == 200
        data = response.json()
        assert "note" in data
        assert data["note"] is None
    
    def test_update_note(self, client, test_date, sample_note):
        """PUT updates existing note."""
        # Create initial note
        client.put(f"/trading-notes/{test_date}", json=sample_note)
        
        # Update with new data
        updated_data = {
            "ross_pnl": "+$2500",
            "lessons": "Updated lesson learned"
        }
        response = client.put(f"/trading-notes/{test_date}", json=updated_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["note"]["ross_pnl"] == "+$2500"
        assert data["note"]["lessons"] == "Updated lesson learned"
        # Original fields should persist
        assert data["note"]["ross_trades"] == sample_note["ross_trades"]
        assert data["note"]["market_context"] == sample_note["market_context"]
        
        # Cleanup
        client.delete(f"/trading-notes/{test_date}")
    
    def test_delete_note(self, client, test_date, sample_note):
        """DELETE removes note."""
        # Create note first
        client.put(f"/trading-notes/{test_date}", json=sample_note)
        
        # Delete it
        response = client.delete(f"/trading-notes/{test_date}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["date"] == test_date
        
        # Verify it's gone
        get_response = client.get(f"/trading-notes/{test_date}")
        assert get_response.json()["note"] is None
    
    def test_delete_note_not_found(self, client):
        """DELETE non-existent note returns 404."""
        response = client.delete("/trading-notes/1900-01-01")
        
        assert response.status_code == 404


# ============================================================================
# Trading Notes List Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestTradingNotesList:
    """Tests for trading notes list endpoint."""
    
    def test_list_notes(self, client):
        """GET /trading-notes returns list."""
        response = client.get("/trading-notes")
        
        assert response.status_code == 200
        data = response.json()
        assert "notes" in data
        assert isinstance(data["notes"], list)
    
    def test_list_notes_with_date_filter(self, client, test_date, sample_note):
        """GET /trading-notes supports date range filter."""
        # Create a test note
        client.put(f"/trading-notes/{test_date}", json=sample_note)
        
        # Query with date filter
        response = client.get(f"/trading-notes?start_date={test_date}&end_date={test_date}")
        
        assert response.status_code == 200
        data = response.json()
        assert "notes" in data
        # Should contain our test note
        dates = [n["date"] for n in data["notes"]]
        assert test_date in dates
        
        # Cleanup
        client.delete(f"/trading-notes/{test_date}")
    
    def test_list_notes_with_limit(self, client):
        """GET /trading-notes respects limit parameter."""
        response = client.get("/trading-notes?limit=5")
        
        assert response.status_code == 200
        data = response.json()
        assert "notes" in data
        assert len(data["notes"]) <= 5


# ============================================================================
# Dates With Entries Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestDatesWithEntries:
    """Tests for dates-with-entries endpoint."""
    
    def test_dates_with_entries(self, client, test_date, sample_note):
        """GET /trading-notes/dates-with-entries returns only dates with entries."""
        # Create a test note
        client.put(f"/trading-notes/{test_date}", json=sample_note)
        
        # Get dates with entries
        response = client.get("/trading-notes/dates-with-entries")
        
        assert response.status_code == 200
        data = response.json()
        assert "dates" in data
        assert isinstance(data["dates"], list)
        assert test_date in data["dates"]
        
        # Cleanup
        client.delete(f"/trading-notes/{test_date}")
    
    def test_dates_with_entries_date_filter(self, client, test_date, sample_note):
        """GET /trading-notes/dates-with-entries supports date range filter."""
        # Create a test note
        client.put(f"/trading-notes/{test_date}", json=sample_note)
        
        # Query with date filter that excludes the test date
        response = client.get("/trading-notes/dates-with-entries?start_date=2090-01-01&end_date=2090-12-31")
        
        assert response.status_code == 200
        data = response.json()
        # Test date should not be in results (outside range)
        assert test_date not in data["dates"]
        
        # Cleanup
        client.delete(f"/trading-notes/{test_date}")
