"""
User Preferences API

Endpoints for storing and retrieving user preferences like table layouts.
"""

import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

from nexus2.db import SessionLocal
from nexus2.db.models import UserPreferencesModel

router = APIRouter(prefix="/api", tags=["preferences"])
logger = logging.getLogger(__name__)


class PreferenceValue(BaseModel):
    """Value to store for a preference."""
    value: Any  # Can be any JSON-serializable value (object, array, etc.)


@router.get("/preferences/{key}")
async def get_preference(key: str):
    """
    Get a user preference by key.
    
    Common keys:
    - dashboard_columns: Column layout for Dashboard positions table
    - automation_columns: Column layout for Automation positions table
    """
    db = SessionLocal()
    try:
        pref = db.query(UserPreferencesModel).filter(
            UserPreferencesModel.key == key
        ).first()
        
        if not pref:
            return {"key": key, "value": None}
        
        return pref.to_dict()
    finally:
        db.close()


@router.put("/preferences/{key}")
async def set_preference(key: str, body: PreferenceValue):
    """
    Set a user preference by key.
    
    The value can be any JSON-serializable object (e.g., array of column configs).
    """
    db = SessionLocal()
    try:
        # Check if exists
        pref = db.query(UserPreferencesModel).filter(
            UserPreferencesModel.key == key
        ).first()
        
        value_json = json.dumps(body.value)
        
        if pref:
            # Update existing
            pref.value = value_json
        else:
            # Create new
            pref = UserPreferencesModel(key=key, value=value_json)
            db.add(pref)
        
        db.commit()
        db.refresh(pref)
        
        logger.info(f"[Preferences] Saved {key}")
        return pref.to_dict()
    except Exception as e:
        db.rollback()
        logger.error(f"[Preferences] Error saving {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
