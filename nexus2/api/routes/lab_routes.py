"""
Lab API Routes - Strategy management endpoints.

Provides REST API for the R&D Lab:
- List strategies
- Get strategy details
- Create new strategy versions
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nexus2.domain.lab import StrategySpec
from nexus2.domain.lab.strategy_registry import get_registry


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lab", tags=["lab"])


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class StrategyListItem(BaseModel):
    """Summary of a strategy for listing."""
    name: str
    versions: list[str]
    latest: str


class StrategyListResponse(BaseModel):
    """Response for list strategies endpoint."""
    strategies: list[StrategyListItem]
    count: int


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/strategies", response_model=StrategyListResponse)
async def list_strategies():
    """List all available strategies with their versions."""
    registry = get_registry()
    strategies = registry.list_strategies()
    
    return StrategyListResponse(
        strategies=[StrategyListItem(**s) for s in strategies],
        count=len(strategies),
    )


@router.get("/strategies/{name}", response_model=StrategySpec)
async def get_strategy(name: str, version: Optional[str] = None):
    """Get a strategy by name, optionally specifying version.
    
    If no version specified, returns the latest version.
    """
    registry = get_registry()
    strategy = registry.load_strategy(name, version)
    
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy not found: {name}" + (f" v{version}" if version else ""),
        )
    
    return strategy


@router.get("/strategies/{name}/{version}", response_model=StrategySpec)
async def get_strategy_version(name: str, version: str):
    """Get a specific version of a strategy."""
    registry = get_registry()
    strategy = registry.load_strategy(name, version)
    
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy not found: {name} v{version}",
        )
    
    return strategy


@router.post("/strategies", response_model=dict)
async def create_strategy(spec: StrategySpec):
    """Create a new strategy version.
    
    Strategy versions are immutable - once created, they cannot be modified.
    To make changes, create a new version.
    """
    registry = get_registry()
    
    # Check if version already exists
    if registry.strategy_exists(spec.name, spec.version):
        raise HTTPException(
            status_code=409,
            detail=f"Strategy version already exists: {spec.name} v{spec.version}",
        )
    
    # Save the strategy
    success = registry.save_strategy(spec)
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to save strategy",
        )
    
    return {
        "status": "created",
        "name": spec.name,
        "version": spec.version,
        "path": str(registry.get_strategy_path(spec.name, spec.version)),
    }


@router.get("/health")
async def lab_health():
    """Health check for Lab API."""
    registry = get_registry()
    strategies = registry.list_strategies()
    
    return {
        "status": "ok",
        "strategies_count": len(strategies),
        "strategies": [s["name"] for s in strategies],
    }
