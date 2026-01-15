"""
Health Routes
"""

import os
import psutil
from datetime import datetime
from fastapi import APIRouter
import pytz

from nexus2.api.schemas import HealthResponse


router = APIRouter(tags=["health"])

# Track server start time for uptime calculation
_server_start_time = datetime.now()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with memory and uptime stats."""
    # Get actual mode from settings
    try:
        from nexus2.api.routes.settings import get_settings
        settings = get_settings()
        mode = settings.broker_type  # e.g., "alpaca_paper", "alpaca_live", "sim"
    except Exception:
        mode = "unknown"
    
    # Get Eastern Time (consistent timezone)
    eastern = pytz.timezone('America/New_York')
    now_et = datetime.now(eastern)
    
    # Calculate uptime
    uptime_seconds = int((datetime.now() - _server_start_time).total_seconds())
    
    # Get memory usage (RSS in MB)
    try:
        process = psutil.Process(os.getpid())
        memory_mb = round(process.memory_info().rss / 1024 / 1024, 1)
    except Exception:
        memory_mb = None
    
    return HealthResponse(
        status="healthy",
        version="0.1.14",
        mode=mode,
        timestamp=now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
        uptime_seconds=uptime_seconds,
        memory_mb=memory_mb,
    )

