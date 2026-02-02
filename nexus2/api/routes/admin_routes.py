"""
Admin routes for server management operations.
"""
import asyncio
import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["admin"])


class RestartRequest(BaseModel):
    """Request to restart the server."""
    confirmation: str
    clear_cache: bool = False


class RestartResponse(BaseModel):
    """Response from restart endpoint."""
    status: str
    message: str
    cache_cleared: bool = False


@router.post("/restart", response_model=RestartResponse)
async def restart_server(request: RestartRequest):
    """
    Trigger graceful server restart.
    
    Requires confirmation="REBOOT" to prevent accidental restarts.
    Server will gracefully shutdown and wrapper script will restart it.
    
    Args:
        confirmation: Must be "REBOOT" to confirm restart
        clear_cache: If True, delete __pycache__ dirs before restart (for code deploys)
    
    Returns:
        Status message with restart countdown
    """
    if request.confirmation != "REBOOT":
        raise HTTPException(
            status_code=400,
            detail="Must provide confirmation='REBOOT' to restart server"
        )
    
    cache_cleared = False
    if request.clear_cache:
        # Clear pycache directories
        try:
            nexus_root = Path(__file__).parent.parent.parent.parent
            count = 0
            for pycache in nexus_root.rglob("__pycache__"):
                if pycache.is_dir():
                    shutil.rmtree(pycache, ignore_errors=True)
                    count += 1
            print(f"[Admin] Cleared {count} __pycache__ directories")
            cache_cleared = True
        except Exception as e:
            print(f"[Admin] Cache clear error (continuing): {e}")
    
    async def delayed_exit():
        await asyncio.sleep(0.5)  # Let response complete
        print("[Admin] Restart requested - triggering graceful shutdown...")
        # Exit code 42 = intentional restart (for logging clarity)
        os._exit(42)
    
    asyncio.create_task(delayed_exit())
    
    msg = "Server will restart in ~3 seconds."
    if cache_cleared:
        msg += " Cache cleared."
    msg += " Refresh page after 5-10 seconds."
    
    return RestartResponse(
        status="restarting",
        message=msg,
        cache_cleared=cache_cleared
    )


@router.get("/status")
async def admin_status():
    """Get basic server process info. Use /health for full stats."""
    from nexus2.utils.time_utils import now_et
    
    return {
        "status": "healthy",
        "timestamp": now_et().isoformat(),
        "pid": os.getpid(),
    }
