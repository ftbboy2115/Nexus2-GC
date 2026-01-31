"""
Catalyst Search Routes

API endpoints for searching catalyst headlines.
"""

from fastapi import APIRouter, Query
from typing import List, Optional
from pydantic import BaseModel

from nexus2.domain.automation.catalyst_search_service import (
    get_catalyst_search_service,
    CatalystSearchResult,
)

router = APIRouter(prefix="/catalyst", tags=["Catalyst"])


class CatalystSearchResultResponse(BaseModel):
    """API response for a single search result."""
    symbol: str
    headline: str
    source: Optional[str] = None
    timestamp: Optional[str] = None
    catalyst_type: Optional[str] = None
    match_score: float = 0.0


class CatalystSearchResponse(BaseModel):
    """API response for search results."""
    query: str
    count: int
    results: List[CatalystSearchResultResponse]


class CatalystStatsResponse(BaseModel):
    """API response for catalyst stats."""
    total_symbols: int
    total_headlines: int
    catalyst_types: dict
    cache_loaded_at: Optional[str] = None


@router.get("/search", response_model=CatalystSearchResponse)
async def search_catalysts(
    q: str = Query(..., description="Search query", min_length=2),
    symbols: Optional[str] = Query(None, description="Comma-separated symbols to filter"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
):
    """
    Search catalyst headlines by keyword.
    
    Examples:
    - /catalyst/search?q=FDA
    - /catalyst/search?q=earnings&symbols=AAPL,MSFT
    - /catalyst/search?q=partnership&limit=100
    """
    service = get_catalyst_search_service()
    
    # Parse symbols list
    symbol_list = None
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
    
    results = service.search(query=q, symbols=symbol_list, limit=limit)
    
    return CatalystSearchResponse(
        query=q,
        count=len(results),
        results=[
            CatalystSearchResultResponse(
                symbol=r.symbol,
                headline=r.headline,
                source=r.source,
                timestamp=r.timestamp,
                catalyst_type=r.catalyst_type,
                match_score=r.match_score,
            )
            for r in results
        ],
    )


@router.get("/stats", response_model=CatalystStatsResponse)
async def get_catalyst_stats():
    """Get statistics about the catalyst cache."""
    service = get_catalyst_search_service()
    stats = service.get_stats()
    
    return CatalystStatsResponse(**stats)


@router.get("/recent", response_model=CatalystSearchResponse)
async def get_recent_catalysts(
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """Get most recent catalysts."""
    service = get_catalyst_search_service()
    results = service.get_recent_catalysts(limit=limit)
    
    return CatalystSearchResponse(
        query="",
        count=len(results),
        results=[
            CatalystSearchResultResponse(
                symbol=r.symbol,
                headline=r.headline,
                source=r.source,
                timestamp=r.timestamp,
                catalyst_type=r.catalyst_type,
                match_score=r.match_score,
            )
            for r in results
        ],
    )
