"""
Health Routes
"""

from datetime import datetime
from fastapi import APIRouter
import pytz

from nexus2.api.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    # Get actual mode from settings
    try:
        from nexus2.api.routes.settings import get_settings
        settings = get_settings()
        mode = settings.broker_type  # e.g., "alpaca_paper", "alpaca_live", "sim"
    except Exception:
        mode = "unknown"
    
    # Get Eastern Time for debugging
    eastern = pytz.timezone('America/New_York')
    now_et = datetime.now(eastern)
    
    return HealthResponse(
        status="healthy",
        version="0.1.13",
        mode=mode,
        timestamp=datetime.now(),
        eastern_time=now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
    )

