"""
Health Routes
"""

import os
import shutil
import subprocess
import psutil
from datetime import datetime
from fastapi import APIRouter

from nexus2.api.schemas import HealthResponse
from nexus2.utils.time_utils import now_et, format_et


router = APIRouter(tags=["health"])

# Track server start time for uptime calculation
_server_start_time = now_et()

# Compute version with git hash and commit date at import time
def _get_version() -> tuple[str, str | None]:
    """Returns (version_string, commit_date_string)."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        # Get commit date in human-readable format
        commit_date = subprocess.check_output(
            ["git", "log", "-1", "--format=%ci"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return f"0.2.0-{commit}", commit_date
    except Exception:
        return "0.2.0-unknown", None

_VERSION, _COMMIT_DATE = _get_version()

# Path to monitor settings file (for sync status check)
_SETTINGS_FILE = os.path.join(os.path.expanduser("~/Nexus2/data"), "warrior_monitor_settings.json")
if not os.path.exists(_SETTINGS_FILE):
    # Fallback for local dev
    _SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "warrior_monitor_settings.json")

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
    
    # Get memory usage (RSS in MB) + total system memory
    try:
        process = psutil.Process(os.getpid())
        memory_mb = round(process.memory_info().rss / 1024 / 1024, 1)
        memory_total_mb = round(psutil.virtual_memory().total / 1024 / 1024, 1)
    except Exception:
        memory_mb = None
        memory_total_mb = None
    
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
    
    # Check if pycache was cleared on last restart (from admin config marker)
    try:
        import json as _json
        admin_config_path = os.path.join(os.path.expanduser("~/Nexus2/data"), "admin_config.json")
        if not os.path.exists(admin_config_path):
            admin_config_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "admin_config.json")
        if os.path.exists(admin_config_path):
            with open(admin_config_path) as f:
                admin_config = _json.load(f)
            pycache_cleared_at = admin_config.get("pycache_cleared_at")
            # Compare with server start time — only counts if cleared BEFORE this boot
            pycache_cleared = pycache_cleared_at is not None
        else:
            pycache_cleared = False
    except Exception:
        pycache_cleared = None
    
    # Settings file last modified time
    try:
        if os.path.exists(_SETTINGS_FILE):
            mtime = os.path.getmtime(_SETTINGS_FILE)
            settings_modified_at = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        else:
            settings_modified_at = "no file"
    except Exception:
        settings_modified_at = None
    
    return HealthResponse(
        status="healthy",
        version=_VERSION,
        mode=mode,
        timestamp=format_et(),  # Using centralized time utility
        uptime_seconds=uptime_seconds,
        started_at=_server_start_time.strftime("%Y-%m-%d %H:%M:%S ET"),
        memory_mb=memory_mb,
        memory_total_mb=memory_total_mb,
        disk_used_gb=disk_used_gb,
        disk_total_gb=disk_total_gb,
        disk_percent=disk_percent,
        commit_date=_COMMIT_DATE,
        pycache_cleared=pycache_cleared,
        settings_modified_at=settings_modified_at,
    )

