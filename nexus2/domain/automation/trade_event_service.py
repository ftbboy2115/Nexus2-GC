"""
Trade Event Service

Logs trade management events to the database for audit and analysis.
Supports both NAC (KK swing) and Warrior (day trading) strategies.
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from nexus2.db.database import get_session
from nexus2.db.models import TradeEventModel


logger = logging.getLogger(__name__)


class TradeEventService:
    """
    Service for logging trade management events.
    
    Used by both NAC and Warrior monitors to create an audit trail
    of all position management actions.
    """
    
    # NAC Event Types
    NAC_ENTRY = "ENTRY"
    NAC_STOP_MOVED = "STOP_MOVED"
    NAC_BREAKEVEN_SET = "BREAKEVEN_SET"
    NAC_PARTIAL_EXIT = "PARTIAL_EXIT"
    NAC_TRAILING_STOP_EXIT = "TRAILING_STOP_EXIT"
    NAC_CHARACTER_CHANGE_EXIT = "CHARACTER_CHANGE_EXIT"
    NAC_MA_CHECK_EXIT = "MA_CHECK_EXIT"
    NAC_STOP_HIT = "STOP_HIT"
    NAC_FULL_EXIT = "FULL_EXIT"
    
    # Warrior Event Types
    WARRIOR_ENTRY = "ENTRY"
    WARRIOR_STOP_MOVED = "STOP_MOVED"
    WARRIOR_BREAKEVEN_SET = "BREAKEVEN_SET"
    WARRIOR_PARTIAL_EXIT = "PARTIAL_EXIT"
    WARRIOR_SCALE_IN = "SCALE_IN"
    WARRIOR_MENTAL_STOP_EXIT = "MENTAL_STOP_EXIT"
    WARRIOR_TECHNICAL_STOP_EXIT = "TECHNICAL_STOP_EXIT"
    WARRIOR_CANDLE_UNDER_CANDLE_EXIT = "CANDLE_UNDER_CANDLE_EXIT"
    WARRIOR_TOPPING_TAIL_EXIT = "TOPPING_TAIL_EXIT"
    WARRIOR_TIME_STOP_EXIT = "TIME_STOP_EXIT"
    WARRIOR_AFTER_HOURS_EXIT = "AFTER_HOURS_EXIT"
    WARRIOR_FULL_EXIT = "FULL_EXIT"
    
    def __init__(self):
        pass
    
    def _log_event(
        self,
        strategy: str,
        position_id: str,
        symbol: str,
        event_type: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """
        Internal method to log an event to the database.
        
        Returns the event ID if successful, None otherwise.
        """
        try:
            with get_session() as db:
                event = TradeEventModel(
                    strategy=strategy,
                    position_id=str(position_id),
                    symbol=symbol.upper(),
                    event_type=event_type,
                    old_value=old_value,
                    new_value=new_value,
                    reason=reason,
                    metadata_json=json.dumps(metadata) if metadata else None,
                    created_at=datetime.utcnow(),
                )
                db.add(event)
                db.commit()
                db.refresh(event)
                logger.info(f"[TradeEvent] {strategy} | {symbol} | {event_type} | {reason or ''}")
                return event.id
        except Exception as e:
            logger.error(f"[TradeEvent] Failed to log event: {e}")
            return None
    
    # ==================== NAC Methods ====================
    
    def log_nac_entry(
        self,
        position_id: str,
        symbol: str,
        entry_price: Decimal,
        stop_price: Decimal,
        shares: int,
        setup_type: str = "unknown",
        quality_score: int = 0,
    ) -> Optional[int]:
        """Log NAC position entry."""
        return self._log_event(
            strategy="NAC",
            position_id=position_id,
            symbol=symbol,
            event_type=self.NAC_ENTRY,
            new_value=str(entry_price),
            reason=f"Entry: {shares} shares @ ${entry_price}",
            metadata={
                "entry_price": str(entry_price),
                "stop_price": str(stop_price),
                "shares": shares,
                "setup_type": setup_type,
                "quality_score": quality_score,
            },
        )
    
    def log_nac_stop_moved(
        self,
        position_id: str,
        symbol: str,
        old_stop: Decimal,
        new_stop: Decimal,
        reason: str = "Manual adjustment",
    ) -> Optional[int]:
        """Log NAC stop price change."""
        return self._log_event(
            strategy="NAC",
            position_id=position_id,
            symbol=symbol,
            event_type=self.NAC_STOP_MOVED,
            old_value=str(old_stop),
            new_value=str(new_stop),
            reason=reason,
        )
    
    def log_nac_breakeven(
        self,
        position_id: str,
        symbol: str,
        entry_price: Decimal,
    ) -> Optional[int]:
        """Log NAC stop moved to breakeven."""
        return self._log_event(
            strategy="NAC",
            position_id=position_id,
            symbol=symbol,
            event_type=self.NAC_BREAKEVEN_SET,
            new_value=str(entry_price),
            reason="Stop moved to breakeven after 1R gain",
        )
    
    def log_nac_partial_exit(
        self,
        position_id: str,
        symbol: str,
        shares_sold: int,
        exit_price: Decimal,
        pnl: Decimal,
        days_held: int = 0,
    ) -> Optional[int]:
        """Log NAC partial exit (Day 3-5 rule)."""
        return self._log_event(
            strategy="NAC",
            position_id=position_id,
            symbol=symbol,
            event_type=self.NAC_PARTIAL_EXIT,
            new_value=str(exit_price),
            reason=f"Day {days_held} partial: {shares_sold} shares @ ${exit_price}",
            metadata={
                "shares_sold": shares_sold,
                "exit_price": str(exit_price),
                "pnl": str(pnl),
                "days_held": days_held,
            },
        )
    
    def log_nac_exit(
        self,
        position_id: str,
        symbol: str,
        exit_price: Decimal,
        exit_type: str,
        pnl: Decimal,
        reason: str = "",
    ) -> Optional[int]:
        """Log NAC full exit."""
        # Map exit type to event type
        event_type_map = {
            "stop_hit": self.NAC_STOP_HIT,
            "trailing_stop": self.NAC_TRAILING_STOP_EXIT,
            "character_change": self.NAC_CHARACTER_CHANGE_EXIT,
            "ma_check": self.NAC_MA_CHECK_EXIT,
        }
        event_type = event_type_map.get(exit_type, self.NAC_FULL_EXIT)
        
        return self._log_event(
            strategy="NAC",
            position_id=position_id,
            symbol=symbol,
            event_type=event_type,
            new_value=str(exit_price),
            reason=reason or f"Exit @ ${exit_price}, P&L: ${pnl}",
            metadata={
                "exit_price": str(exit_price),
                "exit_type": exit_type,
                "pnl": str(pnl),
            },
        )
    
    # ==================== Warrior Methods ====================
    
    def log_warrior_entry(
        self,
        position_id: str,
        symbol: str,
        entry_price: Decimal,
        stop_price: Decimal,
        shares: int,
        trigger_type: str = "ORB",
    ) -> Optional[int]:
        """Log Warrior position entry."""
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=self.WARRIOR_ENTRY,
            new_value=str(entry_price),
            reason=f"{trigger_type} Entry: {shares} shares @ ${entry_price}",
            metadata={
                "entry_price": str(entry_price),
                "stop_price": str(stop_price),
                "shares": shares,
                "trigger_type": trigger_type,
            },
        )
    
    def log_warrior_stop_moved(
        self,
        position_id: str,
        symbol: str,
        old_stop: Decimal,
        new_stop: Decimal,
        reason: str = "Manual adjustment",
    ) -> Optional[int]:
        """Log Warrior stop price change."""
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=self.WARRIOR_STOP_MOVED,
            old_value=str(old_stop),
            new_value=str(new_stop),
            reason=reason,
        )
    
    def log_warrior_breakeven(
        self,
        position_id: str,
        symbol: str,
        entry_price: Decimal,
    ) -> Optional[int]:
        """Log Warrior stop moved to breakeven after partial."""
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=self.WARRIOR_BREAKEVEN_SET,
            new_value=str(entry_price),
            reason="Stop to breakeven after 2:1 R partial",
        )
    
    def log_warrior_partial_exit(
        self,
        position_id: str,
        symbol: str,
        shares_sold: int,
        exit_price: Decimal,
        pnl: Decimal,
        r_multiple: float = 0.0,
    ) -> Optional[int]:
        """Log Warrior partial exit (2:1 R target)."""
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=self.WARRIOR_PARTIAL_EXIT,
            new_value=str(exit_price),
            reason=f"{r_multiple:.1f}R partial: {shares_sold} shares @ ${exit_price}",
            metadata={
                "shares_sold": shares_sold,
                "exit_price": str(exit_price),
                "pnl": str(pnl),
                "r_multiple": r_multiple,
            },
        )
    
    def log_warrior_scale_in(
        self,
        position_id: str,
        symbol: str,
        add_price: Decimal,
        shares_added: int,
    ) -> Optional[int]:
        """Log Warrior scale-in (add on strength)."""
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=self.WARRIOR_SCALE_IN,
            new_value=str(add_price),
            reason=f"Added {shares_added} shares @ ${add_price}",
            metadata={
                "add_price": str(add_price),
                "shares_added": shares_added,
            },
        )
    
    def log_warrior_exit(
        self,
        position_id: str,
        symbol: str,
        exit_price: Decimal,
        exit_reason: str,
        pnl: Decimal,
    ) -> Optional[int]:
        """Log Warrior full exit."""
        # Map exit reason to event type
        event_type_map = {
            "mental_stop": self.WARRIOR_MENTAL_STOP_EXIT,
            "technical_stop": self.WARRIOR_TECHNICAL_STOP_EXIT,
            "candle_under_candle": self.WARRIOR_CANDLE_UNDER_CANDLE_EXIT,
            "topping_tail": self.WARRIOR_TOPPING_TAIL_EXIT,
            "time_stop": self.WARRIOR_TIME_STOP_EXIT,
            "after_hours_exit": self.WARRIOR_AFTER_HOURS_EXIT,
        }
        event_type = event_type_map.get(exit_reason, self.WARRIOR_FULL_EXIT)
        
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=event_type,
            new_value=str(exit_price),
            reason=f"Exit ({exit_reason}) @ ${exit_price}, P&L: ${pnl}",
            metadata={
                "exit_price": str(exit_price),
                "exit_reason": exit_reason,
                "pnl": str(pnl),
            },
        )
    
    # ==================== Query Methods ====================
    
    def get_events_for_position(
        self,
        position_id: str,
        strategy: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get all events for a position."""
        try:
            with get_session() as db:
                query = db.query(TradeEventModel).filter(
                    TradeEventModel.position_id == str(position_id)
                )
                if strategy:
                    query = query.filter(TradeEventModel.strategy == strategy)
                events = query.order_by(TradeEventModel.created_at.asc()).all()
                return [e.to_dict() for e in events]
        except Exception as e:
            logger.error(f"[TradeEvent] Failed to get events: {e}")
            return []
    
    def get_recent_events(
        self,
        strategy: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get recent events across all positions."""
        try:
            with get_session() as db:
                query = db.query(TradeEventModel)
                if strategy:
                    query = query.filter(TradeEventModel.strategy == strategy)
                events = query.order_by(TradeEventModel.created_at.desc()).limit(limit).all()
                return [e.to_dict() for e in events]
        except Exception as e:
            logger.error(f"[TradeEvent] Failed to get recent events: {e}")
            return []


# Singleton instance for easy access
trade_event_service = TradeEventService()
