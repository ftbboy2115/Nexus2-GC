"""
API Test Configuration

Disables pytest-timeout for API tests due to signal incompatibility
with FastAPI TestClient on Linux (threading + signals conflict).
"""

import pytest


def pytest_collection_modifyitems(items):
    """Disable timeout for all tests in this folder."""
    for item in items:
        item.add_marker(pytest.mark.timeout(0))
