"""
Repository Layer

Data access layer for orders and positions.
"""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from nexus2.db.models import OrderModel, FillModel, PositionModel, SettingsModel


class OrderRepository:
    """Repository for order operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, order_data: dict) -> OrderModel:
        """Create a new order."""
        order = OrderModel(**order_data)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order
    
    def get_by_id(self, order_id: str) -> Optional[OrderModel]:
        """Get order by ID."""
        return self.db.query(OrderModel).filter(OrderModel.id == order_id).first()
    
    def get_all(self, status: Optional[str] = None, limit: int = 100) -> List[OrderModel]:
        """Get all orders, optionally filtered by status."""
        query = self.db.query(OrderModel)
        if status:
            query = query.filter(OrderModel.status == status)
        return query.order_by(OrderModel.created_at.desc()).limit(limit).all()
    
    def get_by_symbol(self, symbol: str) -> List[OrderModel]:
        """Get orders by symbol."""
        return self.db.query(OrderModel).filter(OrderModel.symbol == symbol).all()
    
    def update(self, order_id: str, updates: dict) -> Optional[OrderModel]:
        """Update an order."""
        order = self.get_by_id(order_id)
        if order:
            for key, value in updates.items():
                if hasattr(order, key):
                    setattr(order, key, value)
            self.db.commit()
            self.db.refresh(order)
        return order
    
    def delete(self, order_id: str) -> bool:
        """Delete an order."""
        order = self.get_by_id(order_id)
        if order:
            self.db.delete(order)
            self.db.commit()
            return True
        return False
    
    def add_fill(self, order_id: str, fill_data: dict) -> Optional[FillModel]:
        """Add a fill to an order."""
        order = self.get_by_id(order_id)
        if not order:
            return None
        
        fill = FillModel(order_id=order_id, **fill_data)
        self.db.add(fill)
        self.db.commit()
        self.db.refresh(fill)
        return fill


class PositionRepository:
    """Repository for position operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, position_data: dict) -> PositionModel:
        """Create a new position."""
        position = PositionModel(**position_data)
        self.db.add(position)
        self.db.commit()
        self.db.refresh(position)
        return position
    
    def get_by_id(self, position_id: str) -> Optional[PositionModel]:
        """Get position by ID."""
        return self.db.query(PositionModel).filter(PositionModel.id == position_id).first()
    
    def get_all(self, status: Optional[str] = None, limit: int = 100) -> List[PositionModel]:
        """Get all positions, optionally filtered by status."""
        query = self.db.query(PositionModel)
        if status:
            query = query.filter(PositionModel.status == status)
        return query.order_by(PositionModel.opened_at.desc()).limit(limit).all()
    
    def get_open(self) -> List[PositionModel]:
        """Get all open positions."""
        return self.get_all(status="open")
    
    def get_by_symbol(self, symbol: str) -> List[PositionModel]:
        """Get positions by symbol."""
        return self.db.query(PositionModel).filter(PositionModel.symbol == symbol).all()
    
    def update(self, position_id: str, updates: dict) -> Optional[PositionModel]:
        """Update a position."""
        position = self.get_by_id(position_id)
        if position:
            for key, value in updates.items():
                if hasattr(position, key):
                    setattr(position, key, value)
            self.db.commit()
            self.db.refresh(position)
        return position
    
    def close(self, position_id: str, realized_pnl: str) -> Optional[PositionModel]:
        """Close a position."""
        return self.update(position_id, {
            "status": "closed",
            "remaining_shares": 0,
            "realized_pnl": realized_pnl,
            "closed_at": datetime.utcnow(),
        })
    
    def get_by_source(self, source: Optional[str] = None, status: Optional[str] = None, limit: int = 1000) -> List[PositionModel]:
        """
        Get positions filtered by source for analytics.
        
        Args:
            source: 'nac', 'manual', 'external', or None for all
            status: 'open', 'closed', or None for all
            limit: Max results
            
        Returns:
            List of positions
        """
        query = self.db.query(PositionModel)
        if source:
            query = query.filter(PositionModel.source == source)
        if status:
            query = query.filter(PositionModel.status == status)
        return query.order_by(PositionModel.opened_at.desc()).limit(limit).all()


class PositionExitRepository:
    """Repository for position exit operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, exit_data: dict) -> "PositionExitModel":
        """Create a new position exit record."""
        from nexus2.db.models import PositionExitModel
        exit_record = PositionExitModel(**exit_data)
        self.db.add(exit_record)
        self.db.commit()
        self.db.refresh(exit_record)
        return exit_record
    
    def get_by_position(self, position_id: str) -> List["PositionExitModel"]:
        """Get all exits for a position."""
        from nexus2.db.models import PositionExitModel
        return self.db.query(PositionExitModel).filter(
            PositionExitModel.position_id == position_id
        ).order_by(PositionExitModel.exited_at).all()
    
    def get_avg_exit_price(self, position_id: str) -> Optional[str]:
        """Calculate weighted average exit price for a position."""
        from decimal import Decimal
        exits = self.get_by_position(position_id)
        if not exits:
            return None
        
        total_value = Decimal("0")
        total_shares = 0
        
        for ex in exits:
            total_value += Decimal(ex.exit_price) * ex.shares
            total_shares += ex.shares
        
        if total_shares == 0:
            return None
        
        avg_price = total_value / total_shares
        return str(avg_price.quantize(Decimal("0.01")))


class SettingsRepository:
    """Repository for settings operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get(self, key: str, default: str = None) -> Optional[str]:
        """Get a setting value."""
        setting = self.db.query(SettingsModel).filter(SettingsModel.key == key).first()
        return setting.value if setting else default
    
    def set(self, key: str, value: str) -> SettingsModel:
        """Set a setting value."""
        setting = self.db.query(SettingsModel).filter(SettingsModel.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = SettingsModel(key=key, value=value)
            self.db.add(setting)
        self.db.commit()
        self.db.refresh(setting)
        return setting
    
    def get_all(self) -> dict:
        """Get all settings as dictionary."""
        settings = self.db.query(SettingsModel).all()
        return {s.key: s.value for s in settings}
    
    def set_many(self, settings: dict) -> None:
        """Set multiple settings."""
        for key, value in settings.items():
            self.set(key, str(value))


class WatchlistRepository:
    """Repository for watchlist candidate operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def upsert(self, candidate_data: dict) -> "WatchlistCandidateModel":
        """
        Insert or update a candidate.
        
        If symbol already exists, update metrics and add source.
        """
        from nexus2.db.models import WatchlistCandidateModel
        
        existing = self.db.query(WatchlistCandidateModel).filter(
            WatchlistCandidateModel.symbol == candidate_data["symbol"]
        ).first()
        
        if existing:
            # Update with latest scan data
            for key, value in candidate_data.items():
                if key != "id" and hasattr(existing, key):
                    setattr(existing, key, value)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            candidate = WatchlistCandidateModel(**candidate_data)
            self.db.add(candidate)
            self.db.commit()
            self.db.refresh(candidate)
            return candidate
    
    def get_all(
        self,
        tier: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List["WatchlistCandidateModel"]:
        """Get candidates with optional filters."""
        from nexus2.db.models import WatchlistCandidateModel
        
        query = self.db.query(WatchlistCandidateModel)
        
        if tier:
            query = query.filter(WatchlistCandidateModel.tier == tier)
        if source:
            query = query.filter(WatchlistCandidateModel.source == source)
        if status:
            query = query.filter(WatchlistCandidateModel.status == status)
        
        return query.order_by(
            WatchlistCandidateModel.quality_score.desc()
        ).limit(limit).all()
    
    def get_by_symbol(self, symbol: str) -> Optional["WatchlistCandidateModel"]:
        """Get candidate by symbol."""
        from nexus2.db.models import WatchlistCandidateModel
        return self.db.query(WatchlistCandidateModel).filter(
            WatchlistCandidateModel.symbol == symbol
        ).first()
    
    def update_status(self, symbol: str, status: str, notes: str = None) -> Optional["WatchlistCandidateModel"]:
        """Update candidate status."""
        from nexus2.db.models import WatchlistCandidateModel
        
        candidate = self.get_by_symbol(symbol)
        if candidate:
            candidate.status = status
            if notes:
                candidate.notes = notes
            self.db.commit()
            self.db.refresh(candidate)
        return candidate
    
    def delete(self, symbol: str) -> bool:
        """Delete a candidate."""
        from nexus2.db.models import WatchlistCandidateModel
        
        candidate = self.get_by_symbol(symbol)
        if candidate:
            self.db.delete(candidate)
            self.db.commit()
            return True
        return False
    
    def clear_all(self) -> int:
        """Clear all candidates. Returns count deleted."""
        from nexus2.db.models import WatchlistCandidateModel
        
        count = self.db.query(WatchlistCandidateModel).count()
        self.db.query(WatchlistCandidateModel).delete()
        self.db.commit()
        return count
    
    def get_today(self) -> List["WatchlistCandidateModel"]:
        """Get candidates scanned today."""
        from nexus2.db.models import WatchlistCandidateModel
        from datetime import date
        
        today = date.today()
        return self.db.query(WatchlistCandidateModel).filter(
            WatchlistCandidateModel.scanned_at >= datetime(today.year, today.month, today.day)
        ).order_by(WatchlistCandidateModel.quality_score.desc()).all()


class SchedulerSettingsRepository:
    """Repository for scheduler settings operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get(self) -> "SchedulerSettingsModel":
        """Get scheduler settings (creates default if not exists)."""
        from nexus2.db.models import SchedulerSettingsModel
        
        settings = self.db.query(SchedulerSettingsModel).first()
        if not settings:
            # Create default settings
            settings = SchedulerSettingsModel()
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)
        return settings
    
    def update(self, updates: dict) -> "SchedulerSettingsModel":
        """Update scheduler settings."""
        from nexus2.db.models import SchedulerSettingsModel
        
        settings = self.get()
        
        for key, value in updates.items():
            if hasattr(settings, key):
                # Handle boolean conversion for adopt_quick_actions
                if key == "adopt_quick_actions":
                    value = "true" if value else "false"
                # Handle list conversion for scan_modes
                elif key == "scan_modes" and isinstance(value, list):
                    value = ",".join(value)
                setattr(settings, key, value)
        
        self.db.commit()
        self.db.refresh(settings)
        return settings
