"""
Trading Notes API

CRUD endpoints for daily trading session notes.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

from nexus2.db.database import get_session
from nexus2.db.models import TradingNoteModel

router = APIRouter(tags=["trading-notes"])
logger = logging.getLogger(__name__)


class TradingNoteRequest(BaseModel):
    """Request body for creating/updating a trading note."""
    ross_trades: Optional[int] = None
    ross_pnl: Optional[str] = None
    ross_notes: Optional[str] = None
    warrior_trades: Optional[int] = None
    warrior_pnl: Optional[str] = None
    warrior_notes: Optional[str] = None
    market_context: Optional[str] = None
    lessons: Optional[str] = None


@router.get("/trading-notes/dates-with-entries")
async def get_dates_with_entries(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """
    Get list of dates that have trading notes entries.
    
    Useful for calendar display to show which dates have entries.
    """
    with get_session() as db:
        query = db.query(TradingNoteModel.date)
        
        if start_date:
            query = query.filter(TradingNoteModel.date >= start_date)
        if end_date:
            query = query.filter(TradingNoteModel.date <= end_date)
        
        query = query.order_by(TradingNoteModel.date.desc())
        notes = query.all()
        
        return {"dates": [n.date for n in notes]}


@router.get("/trading-notes")
async def list_trading_notes(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(50, ge=1, le=500)
):
    """
    List trading notes with optional date range filter.
    """
    with get_session() as db:
        query = db.query(TradingNoteModel)
        
        if start_date:
            query = query.filter(TradingNoteModel.date >= start_date)
        if end_date:
            query = query.filter(TradingNoteModel.date <= end_date)
        
        query = query.order_by(TradingNoteModel.date.desc()).limit(limit)
        notes = query.all()
        
        return {"notes": [n.to_dict() for n in notes]}


@router.get("/trading-notes/{date}")
async def get_trading_note(date: str):
    """
    Get trading note for a specific date.
    
    Date format: YYYY-MM-DD
    """
    with get_session() as db:
        note = db.query(TradingNoteModel).filter(
            TradingNoteModel.date == date
        ).first()
        
        if not note:
            return {"note": None}
        
        return {"note": note.to_dict()}


@router.put("/trading-notes/{date}")
async def upsert_trading_note(date: str, body: TradingNoteRequest):
    """
    Create or update a trading note for a specific date.
    
    Date format: YYYY-MM-DD
    """
    with get_session() as db:
        try:
            # Check if exists
            note = db.query(TradingNoteModel).filter(
                TradingNoteModel.date == date
            ).first()
            
            if note:
                # Update existing
                if body.ross_trades is not None:
                    note.ross_trades = body.ross_trades
                if body.ross_pnl is not None:
                    note.ross_pnl = body.ross_pnl
                if body.ross_notes is not None:
                    note.ross_notes = body.ross_notes
                if body.warrior_trades is not None:
                    note.warrior_trades = body.warrior_trades
                if body.warrior_pnl is not None:
                    note.warrior_pnl = body.warrior_pnl
                if body.warrior_notes is not None:
                    note.warrior_notes = body.warrior_notes
                if body.market_context is not None:
                    note.market_context = body.market_context
                if body.lessons is not None:
                    note.lessons = body.lessons
            else:
                # Create new
                note = TradingNoteModel(
                    date=date,
                    ross_trades=body.ross_trades,
                    ross_pnl=body.ross_pnl,
                    ross_notes=body.ross_notes,
                    warrior_trades=body.warrior_trades,
                    warrior_pnl=body.warrior_pnl,
                    warrior_notes=body.warrior_notes,
                    market_context=body.market_context,
                    lessons=body.lessons,
                )
                db.add(note)
            
            db.commit()
            db.refresh(note)
            
            logger.info(f"[TradingNotes] Saved note for {date}")
            return {"note": note.to_dict()}
        except Exception as e:
            db.rollback()
            logger.error(f"[TradingNotes] Error saving note for {date}: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.delete("/trading-notes/{date}")
async def delete_trading_note(date: str):
    """
    Delete a trading note for a specific date.
    
    Date format: YYYY-MM-DD
    """
    with get_session() as db:
        try:
            note = db.query(TradingNoteModel).filter(
                TradingNoteModel.date == date
            ).first()
            
            if not note:
                raise HTTPException(status_code=404, detail=f"Note not found for {date}")
            
            db.delete(note)
            db.commit()
            
            logger.info(f"[TradingNotes] Deleted note for {date}")
            return {"success": True, "date": date}
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"[TradingNotes] Error deleting note for {date}: {e}")
            raise HTTPException(status_code=500, detail=str(e))
