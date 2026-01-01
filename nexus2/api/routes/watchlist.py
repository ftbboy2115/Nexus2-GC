"""
Watchlist Routes

API for managing scanner watchlist candidates.
"""

from typing import List, Optional
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from nexus2.db import SessionLocal, WatchlistRepository


router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Request/Response models
class WatchlistCandidate(BaseModel):
    id: str
    symbol: str
    name: Optional[str]
    source: str
    tier: str
    price: Optional[str]
    change_pct: Optional[str]
    quality_score: Optional[int]
    rs_percentile: Optional[int]
    adr_percent: Optional[str]
    status: str
    notes: Optional[str]
    scanned_at: Optional[str]
    updated_at: Optional[str]


class AddCandidateRequest(BaseModel):
    symbol: str
    name: Optional[str] = None
    source: str = "manual"
    tier: str = "WIDE"
    price: Optional[str] = None
    change_pct: Optional[str] = None
    quality_score: Optional[int] = None
    rs_percentile: Optional[int] = None
    adr_percent: Optional[str] = None


class UpdateStatusRequest(BaseModel):
    status: str  # new, watching, traded, dismissed
    notes: Optional[str] = None


class WatchlistResponse(BaseModel):
    candidates: List[WatchlistCandidate]
    total: int
    filters: dict


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(
    tier: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    Get watchlist candidates with optional filters.
    
    Filters:
    - tier: FOCUS, WIDE, UNIVERSE
    - source: gainers, actives, screener, manual
    - status: new, watching, traded, dismissed
    """
    repo = WatchlistRepository(db)
    candidates = repo.get_all(tier=tier, source=source, status=status, limit=limit)
    
    return WatchlistResponse(
        candidates=[WatchlistCandidate(**c.to_dict()) for c in candidates],
        total=len(candidates),
        filters={"tier": tier, "source": source, "status": status},
    )


@router.get("/today", response_model=WatchlistResponse)
async def get_today_candidates(db: Session = Depends(get_db)):
    """Get candidates scanned today."""
    repo = WatchlistRepository(db)
    candidates = repo.get_today()
    
    return WatchlistResponse(
        candidates=[WatchlistCandidate(**c.to_dict()) for c in candidates],
        total=len(candidates),
        filters={"date": "today"},
    )


@router.post("/add", response_model=WatchlistCandidate)
async def add_candidate(
    request: AddCandidateRequest,
    db: Session = Depends(get_db),
):
    """Add or update a watchlist candidate."""
    repo = WatchlistRepository(db)
    
    candidate_data = {
        "id": str(uuid4()),
        "symbol": request.symbol.upper(),
        "name": request.name,
        "source": request.source,
        "tier": request.tier,
        "price": request.price,
        "change_pct": request.change_pct,
        "quality_score": request.quality_score,
        "rs_percentile": request.rs_percentile,
        "adr_percent": request.adr_percent,
        "status": "new",
        "scanned_at": datetime.utcnow(),
    }
    
    candidate = repo.upsert(candidate_data)
    return WatchlistCandidate(**candidate.to_dict())


@router.put("/{symbol}/status", response_model=WatchlistCandidate)
async def update_candidate_status(
    symbol: str,
    request: UpdateStatusRequest,
    db: Session = Depends(get_db),
):
    """Update candidate status (watching, traded, dismissed)."""
    repo = WatchlistRepository(db)
    candidate = repo.update_status(symbol.upper(), request.status, request.notes)
    
    if not candidate:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Candidate {symbol} not found")
    
    return WatchlistCandidate(**candidate.to_dict())


@router.delete("/{symbol}")
async def delete_candidate(symbol: str, db: Session = Depends(get_db)):
    """Remove a candidate from watchlist."""
    repo = WatchlistRepository(db)
    deleted = repo.delete(symbol.upper())
    
    return {"deleted": deleted, "symbol": symbol.upper()}


@router.delete("/clear/all")
async def clear_all_candidates(db: Session = Depends(get_db)):
    """Clear all watchlist candidates."""
    repo = WatchlistRepository(db)
    count = repo.clear_all()
    
    return {"cleared": count}
