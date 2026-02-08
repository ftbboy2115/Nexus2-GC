"""
Tests for Mock Market Notes Endpoints (Wave 2)

Tests the Warrior Mock Market notes CRUD endpoints:
- PUT /warrior/mock-market/test-case-notes (cliffnotes editing in YAML)
- GET /warrior/mock-market/notes (per-case notes from JSON)
- PUT /warrior/mock-market/notes (save per-case notes to JSON)
"""

import json
import pytest
from pathlib import Path
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


@pytest.fixture(autouse=True)
def cleanup_test_notes():
    """Clean up any test notes created during tests."""
    yield
    # After test: remove test entries from mock_market_notes.json
    notes_path = Path(__file__).parent.parent / "test_cases" / "mock_market_notes.json"
    if notes_path.exists():
        try:
            with open(notes_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Remove test keys
            test_keys = [k for k in data if k.startswith("_test_wave2")]
            for k in test_keys:
                del data[k]
            with open(notes_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


# ============================================================================
# Mock Market Notes Tests
# ============================================================================

@pytest.mark.timeout(0)
class TestMockMarketNotes:
    """Tests for Mock Market notes endpoints (Wave 1 Items 7-8)."""

    def test_get_notes_returns_200(self, client):
        """GET notes for a case_id returns 200 with expected shape."""
        response = client.get("/warrior/mock-market/notes?case_id=test_case_1")
        assert response.status_code == 200
        data = response.json()
        assert "case_id" in data
        assert "notes" in data
        assert data["case_id"] == "test_case_1"

    def test_get_notes_missing_case_returns_empty(self, client):
        """GET notes for a non-existent case_id returns empty string."""
        response = client.get("/warrior/mock-market/notes?case_id=nonexistent_xyz_abc")
        assert response.status_code == 200
        assert response.json()["notes"] == ""

    def test_put_notes_saves_and_retrieves(self, client):
        """PUT notes then GET returns saved content."""
        # Save notes
        put_response = client.put("/warrior/mock-market/notes", json={
            "case_id": "_test_wave2_roundtrip",
            "notes": "Test notes from Wave 2 roundtrip"
        })
        assert put_response.status_code == 200
        assert put_response.json()["status"] == "ok"

        # Retrieve notes
        get_response = client.get("/warrior/mock-market/notes?case_id=_test_wave2_roundtrip")
        assert get_response.status_code == 200
        assert get_response.json()["notes"] == "Test notes from Wave 2 roundtrip"

    def test_put_notes_overwrites_existing(self, client):
        """PUT notes overwrites previous value for same case_id."""
        case_id = "_test_wave2_overwrite"

        # Write initial
        client.put("/warrior/mock-market/notes", json={
            "case_id": case_id,
            "notes": "First version"
        })

        # Overwrite
        client.put("/warrior/mock-market/notes", json={
            "case_id": case_id,
            "notes": "Second version"
        })

        # Verify overwrite
        response = client.get(f"/warrior/mock-market/notes?case_id={case_id}")
        assert response.json()["notes"] == "Second version"

    def test_global_notepad_roundtrip(self, client):
        """Global notepad (_global case_id) saves and retrieves."""
        client.put("/warrior/mock-market/notes", json={
            "case_id": "_global",
            "notes": "Global notes test from Wave 2"
        })
        response = client.get("/warrior/mock-market/notes?case_id=_global")
        assert response.status_code == 200
        assert response.json()["notes"] == "Global notes test from Wave 2"


@pytest.mark.timeout(0)
class TestMockMarketTestCaseNotes:
    """Tests for YAML test-case-notes endpoint (cliffnotes editing)."""

    def test_put_test_case_notes_rejects_invalid_field(self, client):
        """PUT test-case-notes rejects fields other than notes/description."""
        response = client.put("/warrior/mock-market/test-case-notes", json={
            "case_id": "test_1",
            "field": "dangerous_field",
            "value": "hacked"
        })
        assert response.status_code == 400

    def test_put_test_case_notes_rejects_missing_case(self, client):
        """PUT test-case-notes returns 404 for nonexistent case_id."""
        response = client.put("/warrior/mock-market/test-case-notes", json={
            "case_id": "nonexistent_case_xyz_abc_123",
            "field": "notes",
            "value": "test"
        })
        assert response.status_code == 404

    def test_put_test_case_notes_accepts_notes_field(self, client):
        """PUT test-case-notes accepts 'notes' as a valid field name."""
        # This may 404 if no test cases exist, but must NOT 400 for field validation
        response = client.put("/warrior/mock-market/test-case-notes", json={
            "case_id": "some_case",
            "field": "notes",
            "value": "test value"
        })
        # 404 (case not found) is acceptable, 400 (field rejected) is not
        assert response.status_code in (200, 404)

    def test_put_test_case_notes_accepts_description_field(self, client):
        """PUT test-case-notes accepts 'description' as a valid field name."""
        response = client.put("/warrior/mock-market/test-case-notes", json={
            "case_id": "some_case",
            "field": "description",
            "value": "test value"
        })
        # 404 (case not found) is acceptable, 400 (field rejected) is not
        assert response.status_code in (200, 404)
