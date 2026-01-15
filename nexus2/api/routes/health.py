"""
Health Routes
"""

import os
import psutil
from datetime import datetime
from fastapi import APIRouter

from nexus2.api.schemas import HealthResponse
from nexus2.utils.time_utils import now_et, format_et


router = APIRouter(tags=["health"])

# Track server start time for uptime calculation
_server_start_time = now_et()


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
    
    # Calculate uptime
    uptime_seconds = int((now_et() - _server_start_time).total_seconds())
    
    # Get memory usage (RSS in MB)
    try:
        process = psutil.Process(os.getpid())
        memory_mb = round(process.memory_info().rss / 1024 / 1024, 1)
    except Exception:
        memory_mb = None
    
    return HealthResponse(
        status="healthy",
        version="0.1.15",
        mode=mode,
        timestamp=format_et(),  # Using centralized time utility
        uptime_seconds=uptime_seconds,
        memory_mb=memory_mb,
    )
