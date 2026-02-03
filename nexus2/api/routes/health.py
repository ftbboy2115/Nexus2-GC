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


@router.get("/debug/loggers")
async def debug_loggers():
    """Debug endpoint to inspect logger handlers."""
    import logging
    
    root = logging.getLogger()
    root_handlers = [
        {"type": type(h).__name__, "level": h.level, "stream": str(getattr(h, 'stream', 'N/A'))}
        for h in root.handlers
    ]
    
    # Check warrior entry logger
    entry_logger = logging.getLogger("nexus2.domain.automation.warrior_engine_entry")
    entry_handlers = [
        {"type": type(h).__name__, "level": h.level}
        for h in entry_logger.handlers
    ]
    
    return {
        "root_logger": {
            "level": root.level,
            "handler_count": len(root.handlers),
            "handlers": root_handlers,
        },
        "entry_logger": {
            "level": entry_logger.level,
            "propagate": entry_logger.propagate,
            "handler_count": len(entry_logger.handlers),
            "handlers": entry_handlers,
        }
    }
