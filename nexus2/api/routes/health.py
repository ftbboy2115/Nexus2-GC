"""
Health Routes
"""

import os
import shutil
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
    """Health check endpoint with memory, uptime, and storage stats."""
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
    
    # Get disk storage
    try:
        # Use data directory as reference (or root on Linux)
        data_dir = os.path.expanduser("~/Nexus2/data")
        if not os.path.exists(data_dir):
            data_dir = "/"
        usage = shutil.disk_usage(data_dir)
        disk_used_gb = round(usage.used / (1024**3), 1)
        disk_total_gb = round(usage.total / (1024**3), 1)
        disk_percent = round((usage.used / usage.total) * 100, 1)
    except Exception:
        disk_used_gb = None
        disk_total_gb = None
        disk_percent = None
    
    return HealthResponse(
        status="healthy",
        version="0.1.15",
        mode=mode,
        timestamp=format_et(),  # Using centralized time utility
        uptime_seconds=uptime_seconds,
        started_at=_server_start_time.strftime("%Y-%m-%d %H:%M:%S ET"),
        memory_mb=memory_mb,
        disk_used_gb=disk_used_gb,
        disk_total_gb=disk_total_gb,
        disk_percent=disk_percent,
    )

