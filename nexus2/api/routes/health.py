"""
Health Routes
"""

from datetime import datetime
from fastapi import APIRouter

from nexus2.api.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        mode="sim",  # Always SIM for now
        timestamp=datetime.now(),
    )
