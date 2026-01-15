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
from nexus2.utils.time_utils import now_utc


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
    WARRIOR_SPREAD_EXIT = "SPREAD_EXIT"  # Liquidity protection
    WARRIOR_FULL_EXIT = "FULL_EXIT"
    
    def __init__(self):
        pass
    
    def _get_market_context(self) -> Dict[str, Any]:
        """
        Capture current market conditions (SPY, VIX, MAs) for event context.
        
        Returns dict with spy_price, spy_change_pct, vix, spy_ma_status, timestamp.
        Failures return empty dict (non-blocking).
        """
        try:
            from nexus2.adapters.market_data.unified import UnifiedMarketData
            
            umd = UnifiedMarketData()
            context = {}
            
            # Get SPY quote
            spy_quote = umd.get_quote("SPY")
            if spy_quote:
                context["spy_price"] = float(spy_quote.price)
                # Calculate change if we have open price
                if hasattr(spy_quote, 'open') and spy_quote.open:
                    change_pct = ((spy_quote.price - spy_quote.open) / spy_quote.open) * 100
                    context["spy_change_pct"] = round(float(change_pct), 2)
            
            # Get VIX (CBOE Volatility Index)
            vix_quote = umd.get_quote("VIXY")  # VIX ETF proxy
            if vix_quote:
                context["vix"] = float(vix_quote.price)
            
            # SPY Moving Average Status
            try:
                spy_ma = self._get_spy_ma_status(umd)
                if spy_ma:
                    context.update(spy_ma)
            except Exception as e:
                logger.debug(f"[TradeEvent] SPY MA calculation failed: {e}")
            
            context["market_snapshot_time"] = now_utc().isoformat()
            
            return context
        except Exception as e:
            logger.debug(f"[TradeEvent] Market context capture failed: {e}")
            return {}
    
    def _get_spy_ma_status(self, umd) -> Dict[str, Any]:
        """
        Calculate SPY's position relative to 20/50/200 day moving averages.
        
        Returns:
            {
                "spy_above_20ma": True/False,
                "spy_above_50ma": True/False,
                "spy_above_200ma": True/False,
                "spy_ma_trend": "bullish" / "neutral" / "bearish"
            }
        """
        try:
            # Get 200 days of SPY data (need 200 for 200 MA)
            bars = umd.fmp.get_daily_bars("SPY", limit=210)
            if not bars:
                logger.warning("[TradeEvent] SPY MA: FMP returned no bars")
                return {}
            if len(bars) < 20:
                logger.warning(f"[TradeEvent] SPY MA: Only got {len(bars)} bars (need 20+)")
                return {}
            
            # Bars are typically newest-first, so reverse for chronological
            closes = [float(bar.get('close', bar.get('c', 0))) for bar in bars]
            if not closes or closes[0] == 0:
                logger.warning("[TradeEvent] SPY MA: Invalid close prices in bars")
                return {}
            
            # For FMP, bars are usually newest first, so closes[0] is current
            current_price = closes[0]
            
            # Calculate MAs (simple moving averages)
            result = {}
            
            if len(closes) >= 20:
                ma20 = sum(closes[:20]) / 20
                result["spy_20ma"] = round(ma20, 2)
                result["spy_above_20ma"] = current_price > ma20
            
            if len(closes) >= 50:
                ma50 = sum(closes[:50]) / 50
                result["spy_50ma"] = round(ma50, 2)
                result["spy_above_50ma"] = current_price > ma50
            
            if len(closes) >= 200:
                ma200 = sum(closes[:200]) / 200
                result["spy_200ma"] = round(ma200, 2)
                result["spy_above_200ma"] = current_price > ma200
            
            # Determine overall trend
            above_all = result.get("spy_above_20ma") and result.get("spy_above_50ma") and result.get("spy_above_200ma")
            below_all = not result.get("spy_above_20ma") and not result.get("spy_above_50ma") and not result.get("spy_above_200ma", True)
            
            if above_all:
                result["spy_ma_trend"] = "bullish"
            elif below_all:
                result["spy_ma_trend"] = "bearish"
            else:
                result["spy_ma_trend"] = "neutral"
            
            return result
            
        except Exception as e:
            logger.warning(f"[TradeEvent] SPY MA exception: {type(e).__name__}: {e}")
            return {}
    
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
                    created_at=now_utc(),
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
        metadata = {
            "entry_price": str(entry_price),
            "stop_price": str(stop_price),
            "shares": shares,
            "setup_type": setup_type,
            "quality_score": quality_score,
        }
        # Add market context
        metadata.update(self._get_market_context())
        
        return self._log_event(
            strategy="NAC",
            position_id=position_id,
            symbol=symbol,
            event_type=self.NAC_ENTRY,
            new_value=str(entry_price),
            reason=f"Entry: {shares} shares @ ${entry_price}",
            metadata=metadata,
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
        
        metadata = {
            "exit_price": str(exit_price),
            "exit_type": exit_type,
            "pnl": str(pnl),
        }
        # Add market context
        metadata.update(self._get_market_context())
        
        return self._log_event(
            strategy="NAC",
            position_id=position_id,
            symbol=symbol,
            event_type=event_type,
            new_value=str(exit_price),
            reason=reason or f"Exit @ ${exit_price}, P&L: ${pnl}",
            metadata=metadata,
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
        intended_price: Decimal = None,
        slippage_cents: Decimal = None,
    ) -> Optional[int]:
        """Log Warrior position entry with optional slippage tracking."""
        metadata = {
            "entry_price": str(entry_price),
            "stop_price": str(stop_price),
            "shares": shares,
            "trigger_type": trigger_type,
        }
        
        # Track slippage if provided
        if intended_price and slippage_cents is not None:
            metadata["intended_price"] = str(intended_price)
            metadata["slippage_cents"] = float(slippage_cents)
            if intended_price > 0:
                slippage_bps = float((entry_price / intended_price - 1) * 10000)
                metadata["slippage_bps"] = round(slippage_bps, 1)
        
        # Add market context
        metadata.update(self._get_market_context())
        
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=self.WARRIOR_ENTRY,
            new_value=str(entry_price),
            reason=f"{trigger_type} Entry: {shares} shares @ ${entry_price}",
            metadata=metadata,
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
    
    # Alias for log_warrior_stop_moved (used by scaling logic)
    log_warrior_stop_update = log_warrior_stop_moved
    
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
            "spread_exit": self.WARRIOR_SPREAD_EXIT,
        }
        event_type = event_type_map.get(exit_reason, self.WARRIOR_FULL_EXIT)
        
        metadata = {
            "exit_price": str(exit_price),
            "exit_reason": exit_reason,
            "pnl": str(pnl),
        }
        # Add market context
        metadata.update(self._get_market_context())
        
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=event_type,
            new_value=str(exit_price),
            reason=f"Exit ({exit_reason}) @ ${exit_price}, P&L: ${pnl}",
            metadata=metadata,
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
