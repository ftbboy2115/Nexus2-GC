"""
Trade Event Service

Logs trade management events to the database for audit and analysis.
Supports both NAC (KK swing) and Warrior (day trading) strategies.
"""

import json
import logging
from contextvars import ContextVar
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from nexus2.db.database import get_session
from nexus2.db.models import TradeEventModel
from nexus2.utils.time_utils import now_utc


logger = logging.getLogger(__name__)


# ContextVar for sim mode detection (concurrent batch mode)
_is_sim_mode: ContextVar[bool] = ContextVar('is_sim_mode', default=False)


def set_sim_mode_ctx(value: bool) -> None:
    """Set sim mode for current async task context."""
    _is_sim_mode.set(value)


def is_sim_mode() -> bool:
    """Check if current context is in simulation mode."""
    if _is_sim_mode.get():
        return True
    # Fallback to legacy global check
    from nexus2.api.routes.warrior_sim_routes import get_warrior_sim_broker
    return get_warrior_sim_broker() is not None


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
    WARRIOR_BROKER_SYNC_CLOSE = "BROKER_SYNC_CLOSE"  # Orphan auto-closed by sync
    WARRIOR_EXIT_FAILED = "EXIT_FAILED"  # Exit callback error (diagnostic)
    WARRIOR_FILL_CONFIRMED = "FILL_CONFIRMED"  # Broker fill price received (entry)
    WARRIOR_EXIT_FILL_CONFIRMED = "EXIT_FILL_CONFIRMED"  # Broker exit fill received
    WARRIOR_GUARD_BLOCK = "GUARD_BLOCK"  # Entry blocked by guard (position, macd, cooldown, etc.)
    WARRIOR_REENTRY_ENABLED = "REENTRY_ENABLED"  # Re-entry enabled after profit exit (Phase 11 C4)
    
    def __init__(self):
        # TML (Trade Management Log) file paths for forensics
        from pathlib import Path
        self._nac_log_path = Path(__file__).parent.parent.parent.parent / "data" / "nac_trade.log"
        self._nac_log_path.parent.mkdir(exist_ok=True)
        self._warrior_log_path = Path(__file__).parent.parent.parent.parent / "data" / "warrior_trade.log"
    
    def _log_to_file(self, strategy: str, symbol: str, event_type: str, details: str, order_id: str = None):
        """Append event to persistent TML file for forensics (NAC and Warrior)."""
        try:
            from nexus2.utils.time_utils import now_et
            timestamp = now_et().strftime("%Y-%m-%d %H:%M:%S")
            order_info = f" | order={order_id[:8]}..." if order_id else ""
            line = f"{timestamp} | {event_type:25} | {symbol:6} | {details}{order_info}\n"
            
            if strategy == "NAC":
                with open(self._nac_log_path, "a") as f:
                    f.write(line)
            elif strategy == "WARRIOR":
                with open(self._warrior_log_path, "a") as f:
                    f.write(line)
        except Exception as e:
            logger.debug(f"[TML] File log failed: {e}")
    
    def _get_market_context(self) -> Dict[str, Any]:
        """
        Capture current market conditions (SPY, VIX, MAs) for event context.
        
        Returns dict with spy_price, spy_change_pct, vix, spy_ma_status, timestamp.
        Failures return empty dict (non-blocking).
        
        IMPORTANT: Skips during simulation mode to prevent blocking API calls.
        """
        try:
            # Skip external API calls during simulation mode (they block with time.sleep)
            if is_sim_mode():
                return {"market_context": "skipped_sim_mode", "market_snapshot_time": now_utc().isoformat()}
            
            # Skip when FMP is rate limited to prevent blocking async event loop
            # (FMP uses sync time.sleep() during rate limiting which blocks everything)
            try:
                from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
                fmp = get_fmp_adapter()
                if fmp and fmp.rate_limiter.remaining < 50:
                    return {"market_context": "skipped_rate_limited", "market_snapshot_time": now_utc().isoformat()}
            except Exception:
                pass  # If we can't check, proceed anyway
            
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
            
            # Get VIX (CBOE Volatility Index) — use FMP directly for index quotes
            try:
                from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
                fmp_vix = get_fmp_adapter()
                if fmp_vix:
                    vix_quote = fmp_vix.get_quote("^VIX")
                    if vix_quote:
                        context["vix"] = float(vix_quote.price)
            except Exception as e:
                logger.debug(f"[TradeEvent] VIX quote failed: {e}")
            
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
            # Use Polygon (unlimited) instead of FMP (rate limited) to avoid blocking
            from nexus2.adapters.market_data.polygon_adapter import get_polygon_adapter
            from nexus2.utils.time_utils import now_et
            from datetime import timedelta
            
            polygon = get_polygon_adapter()
            # Request 1 year of data to ensure 210+ trading days
            to_date = now_et().strftime("%Y-%m-%d")
            from_date = (now_et() - timedelta(days=365)).strftime("%Y-%m-%d")
            bars = polygon.get_daily_bars("SPY", limit=300, from_date=from_date, to_date=to_date)
            if not bars:
                logger.warning("[TradeEvent] SPY MA: Polygon returned no bars")
                return {}
            if len(bars) < 20:
                logger.warning(f"[TradeEvent] SPY MA: Only got {len(bars)} bars (need 20+)")
                return {}
            
            # Polygon returns oldest-first (sort=asc), so reverse for newest-first
            bars = list(reversed(bars))
            
            # Bars are now newest-first
            closes = [float(bar.close) for bar in bars if hasattr(bar, 'close') and bar.close]
            if not closes:
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
    
    def _get_symbol_technical_context(self, symbol: str, current_price: float) -> Dict[str, Any]:
        """
        Capture symbol-specific technical indicators for trade event metadata.
        
        Returns dict with MACD status, VWAP position, and EMA levels.
        Failures return empty dict (non-blocking).
        """
        # Skip during simulation to prevent blocking API calls
        if is_sim_mode():
            return {}
        
        try:
            from nexus2.adapters.market_data.unified import get_unified_market_data
            umd = get_unified_market_data()
            
            result = {}
            
            # Get intraday data for VWAP and current indicators
            bars = umd.get_intraday_bars(symbol, interval="1min", limit=50)
            if bars and len(bars) > 0:
                latest = bars[-1]
                vwap = latest.get("vwap")
                if vwap:
                    result["symbol_vwap"] = round(vwap, 2)
                    result["symbol_above_vwap"] = current_price > vwap
            
            # Get MACD from quote snapshot if available
            quote = umd.get_quote(symbol)
            if quote:
                macd = quote.get("macd")
                if macd is not None:
                    result["symbol_macd_value"] = round(macd, 4)
                    if macd > 0.05:
                        result["symbol_macd_status"] = "positive"
                    elif macd >= -0.05:
                        result["symbol_macd_status"] = "flat"
                    else:
                        result["symbol_macd_status"] = "negative"
            
            # Get EMA values from daily bars
            daily_bars = umd.get_daily_bars(symbol, limit=25)
            if daily_bars and len(daily_bars) >= 9:
                closes = [b["close"] for b in daily_bars[-9:]]
                ema9 = sum(closes) / len(closes)  # Simple approximation
                result["symbol_ema9"] = round(ema9, 2)
                result["symbol_above_ema9"] = current_price > ema9
            
            if daily_bars and len(daily_bars) >= 20:
                closes = [b["close"] for b in daily_bars[-20:]]
                ema20 = sum(closes) / len(closes)
                result["symbol_ema20"] = round(ema20, 2)
                result["symbol_above_ema20"] = current_price > ema20
            
            return result
            
        except Exception as e:
            logger.debug(f"[TradeEvent] Symbol technical context failed for {symbol}: {e}")
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
    
    def has_entry_event(self, position_id: str) -> bool:
        """Check if an ENTRY event already exists for a position_id."""
        try:
            with get_session() as db:
                count = db.query(TradeEventModel).filter(
                    TradeEventModel.position_id == str(position_id),
                    TradeEventModel.event_type == "ENTRY",
                ).count()
                return count > 0
        except Exception as e:
            logger.debug(f"[TradeEvent] has_entry_event check failed: {e}")
            return False  # Fail open — allow logging if check fails
    
    def has_fill_confirmed_event(self, position_id: str) -> bool:
        """Check if a FILL_CONFIRMED event already exists for a position_id.
        
        Used by broker sync recovery to avoid logging a duplicate FILL_CONFIRMED
        when the entry poll loop already logged one.
        """
        try:
            with get_session() as db:
                count = db.query(TradeEventModel).filter(
                    TradeEventModel.position_id == str(position_id),
                    TradeEventModel.event_type == "FILL_CONFIRMED",
                ).count()
                return count > 0
        except Exception as e:
            logger.debug(f"[TradeEvent] has_fill_confirmed_event check failed: {e}")
            return False  # Fail open — allow logging if check fails
    
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
        
        # TML: Write to persistent file log
        self._log_to_file(
            strategy="NAC",
            symbol=symbol,
            event_type=self.NAC_ENTRY,
            details=f"{shares} @ ${entry_price} | stop=${stop_price}",
        )
        
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
        # TML: Write to persistent file log
        self._log_to_file(
            strategy="NAC",
            symbol=symbol,
            event_type=self.NAC_PARTIAL_EXIT,
            details=f"{shares_sold} @ ${exit_price} | P&L=${pnl} | Day {days_held}",
        )
        
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
        
        # TML: Write to persistent file log
        self._log_to_file(
            strategy="NAC",
            symbol=symbol,
            event_type=event_type,
            details=f"@ ${exit_price} | P&L=${pnl} | reason={exit_type}",
        )
        
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
        exit_mode: str = None,  # home_run or base_hit
        technical_context: Optional[Dict[str, Any]] = None,  # Pass from caller for consistency
    ) -> Optional[int]:
        """Log Warrior position entry with optional slippage tracking.
        
        Args:
            technical_context: Optional dict with MACD/VWAP/EMA values from entry logic.
                               If provided, uses these instead of fetching (ensures consistency).
                               Expected keys: symbol_macd_value, symbol_macd_status, symbol_vwap, 
                               symbol_above_vwap, symbol_ema9, symbol_above_ema9, etc.
        """
        # Check if this is a Mock Market (simulation) trade
        is_mock_market = is_sim_mode()
        
        metadata = {
            "entry_price": str(entry_price),
            "stop_price": str(stop_price),
            "shares": shares,
            "trigger_type": trigger_type,
            "is_mock_market": is_mock_market,
        }
        
        # Include exit_mode for Entry Type column display
        if exit_mode:
            metadata["exit_mode"] = exit_mode
        
        # Track slippage if provided
        if intended_price and slippage_cents is not None:
            metadata["intended_price"] = str(intended_price)
            metadata["slippage_cents"] = float(slippage_cents)
            if intended_price > 0:
                slippage_bps = float((entry_price / intended_price - 1) * 10000)
                metadata["slippage_bps"] = round(slippage_bps, 1)
        
        # Add market context
        metadata.update(self._get_market_context())
        
        # Add symbol technical context (MACD, VWAP, EMA)
        # PRIORITY: Use caller-provided context to ensure consistency with entry logic
        if technical_context:
            # Caller passed the same snapshot used for entry decisions
            metadata.update(technical_context)
            metadata["technicals_source"] = "caller_snapshot"  # Audit: data came from entry logic
        elif not is_mock_market and entry_price:
            # Live trading: fetch fresh (backward compatibility)
            fetched_context = self._get_symbol_technical_context(symbol, float(entry_price))
            if fetched_context:
                metadata.update(fetched_context)
                metadata["technicals_source"] = "live_api"
            else:
                metadata["technicals_source"] = "unavailable"
                logger.warning(f"[TradeEvent] {symbol}: Technical context unavailable from live API - audit gap")
        else:
            # Sim mode without caller context OR no entry price
            metadata["technicals_source"] = "unavailable"
            if is_mock_market:
                logger.warning(f"[TradeEvent] {symbol}: Technical context missing for Mock Market entry - should be passed from caller")
        
        # TML: Write to persistent file log
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_ENTRY,
            details=f"{shares} @ ${entry_price} | stop=${stop_price} | trigger={trigger_type}",
        )
        
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=self.WARRIOR_ENTRY,
            new_value=str(entry_price),
            reason=f"{trigger_type} Entry: {shares} shares @ ${entry_price}",
            metadata=metadata,
        )
    
    def log_warrior_fill_confirmed(
        self,
        position_id: str,
        symbol: str,
        quote_price: Decimal,
        fill_price: Decimal,
        slippage_cents: float,
        shares: int,
    ) -> Optional[int]:
        """Log when broker confirms actual fill price vs quote."""
        metadata = {
            "quote_price": str(quote_price),
            "fill_price": str(fill_price),
            "slippage_cents": slippage_cents,
            "shares": shares,
        }
        
        # Format slippage for display
        if slippage_cents > 0:
            slip_str = f"+{slippage_cents:.1f}¢ slippage"
        elif slippage_cents < 0:
            slip_str = f"{slippage_cents:.1f}¢ improvement"
        else:
            slip_str = "no slippage"
        
        # TML: Write to persistent file log
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_FILL_CONFIRMED,
            details=f"Quote ${quote_price} → Fill ${fill_price} ({slip_str})",
        )
        
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=self.WARRIOR_FILL_CONFIRMED,
            old_value=str(quote_price),
            new_value=str(fill_price),
            reason=f"Fill confirmed: ${quote_price} → ${fill_price} ({slip_str})",
            metadata=metadata,
        )
    
    def log_warrior_exit_fill_confirmed(
        self,
        position_id: str,
        symbol: str,
        intended_price: Decimal,
        actual_price: Decimal,
        shares: int,
        exit_reason: str,
        pnl: Decimal,
    ) -> Optional[int]:
        """Log when broker confirms actual exit fill price.
        
        This completes the audit trail for exits:
          1. EXIT intent event (e.g., CANDLE_UNDER_CANDLE_EXIT) → PENDING_EXIT
          2. EXIT_FILL_CONFIRMED → CLOSED
        """
        slippage_cents = float((actual_price - intended_price) * 100)
        
        metadata = {
            "intended_price": str(intended_price),
            "actual_price": str(actual_price),
            "slippage_cents": slippage_cents,
            "shares": shares,
            "exit_reason": exit_reason,
            "pnl": str(pnl),
        }
        
        # Format slippage for display
        # For EXITS (sells): actual > intended = BETTER (got more money)
        if slippage_cents > 0:
            slip_str = f"{slippage_cents:.1f}¢ better"
        elif slippage_cents < 0:
            slip_str = f"{abs(slippage_cents):.1f}¢ worse"
        else:
            slip_str = "no slippage"
        
        # TML: Write to persistent file log
        pnl_str = f"+${pnl}" if float(pnl) >= 0 else f"-${abs(float(pnl))}"
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_EXIT_FILL_CONFIRMED,
            details=f"Exit fill ${intended_price} → ${actual_price} ({slip_str}) | P&L={pnl_str}",
        )
        
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=self.WARRIOR_EXIT_FILL_CONFIRMED,
            old_value=str(intended_price),
            new_value=str(actual_price),
            reason=f"Exit fill confirmed: ${intended_price} → ${actual_price} ({slip_str})",
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
        # TML: Write to persistent file log
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_STOP_MOVED,
            details=f"${old_stop} → ${new_stop} | {reason}",
        )
        
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
        shares: int = None,
        old_stop: Decimal = None,
    ) -> Optional[int]:
        """Log Warrior stop moved to breakeven after partial."""
        metadata = {}
        if shares is not None:
            metadata["shares"] = shares
        if old_stop is not None:
            metadata["old_stop"] = str(old_stop)
        metadata["new_stop"] = str(entry_price)

        # TML: Write to persistent file log
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_BREAKEVEN_SET,
            details=f"Stop to breakeven @ ${entry_price}",
        )
        
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=self.WARRIOR_BREAKEVEN_SET,
            new_value=str(entry_price),
            reason="Stop to breakeven after 2:1 R partial",
            metadata=metadata if metadata else None,
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
        # TML: Write to persistent file log
        pnl_str = f"+${pnl}" if float(pnl) >= 0 else f"-${abs(float(pnl))}"
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_PARTIAL_EXIT,
            details=f"{shares_sold} shares @ ${exit_price} | P&L={pnl_str} | {r_multiple:.1f}R",
        )
        
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
        from nexus2.api.routes.warrior_sim_routes import get_warrior_sim_broker
        
        # TML: Write to persistent file log
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_SCALE_IN,
            details=f"+{shares_added} @ ${add_price}",
        )
        
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
                "is_mock_market": is_sim_mode(),
            },
        )
    
    def log_warrior_exit(
        self,
        position_id: str,
        symbol: str,
        exit_price: Decimal,
        exit_reason: str,
        pnl: Decimal,
        shares: int = None,
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
        
        # Check if this is a Mock Market (simulation) trade
        is_mock_market = is_sim_mode()
        
        metadata = {
            "exit_price": str(exit_price),
            "exit_reason": exit_reason,
            "pnl": str(pnl),
            "is_mock_market": is_mock_market,
        }
        if shares is not None:
            metadata["shares"] = shares
        # Add market context
        metadata.update(self._get_market_context())
        
        # TML: Write to persistent file log
        pnl_str = f"+${pnl}" if float(pnl) >= 0 else f"-${abs(float(pnl))}"
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=event_type,
            details=f"@ ${exit_price} | P&L={pnl_str} | reason={exit_reason}",
        )
        
        return self._log_event(
            strategy="WARRIOR",
            position_id=position_id,
            symbol=symbol,
            event_type=event_type,
            new_value=str(exit_price),
            reason=f"Exit ({exit_reason}) @ ${exit_price}, P&L: ${pnl}",
            metadata=metadata,
        )
    
    def log_warrior_broker_sync_close(
        self,
        trade_id: str,
        symbol: str,
        exit_price: float,
        pnl: float,
    ) -> Optional[int]:
        """Log Warrior trade auto-closed by broker sync (orphan recovery)."""
        # Broker sync happens in live mode, not mock market
        metadata = {
            "exit_price": str(exit_price),
            "exit_reason": "broker_sync",
            "pnl": str(pnl),
            "sync_type": "orphan_recovery",
            "is_mock_market": False,  # Broker sync only happens in live mode
        }
        metadata.update(self._get_market_context())
        
        # TML: Write to persistent file log
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_BROKER_SYNC_CLOSE,
            details=f"ORPHAN SYNC @ ${exit_price:.2f} | P&L={pnl_str}",
        )
        
        return self._log_event(
            strategy="WARRIOR",
            position_id=trade_id,
            symbol=symbol,
            event_type=self.WARRIOR_BROKER_SYNC_CLOSE,
            new_value=str(exit_price),
            reason=f"Orphan auto-closed by broker sync @ ${exit_price:.2f}, P&L: ${pnl:.2f}",
            metadata=metadata,
        )
    
    def log_warrior_exit_failed(
        self,
        trade_id: str,
        symbol: str,
        error_message: str,
        error_type: str = "unknown",
        exit_price: float = None,
        shares: int = None,
    ) -> Optional[int]:
        """Log Warrior exit failure for diagnosis (callback threw exception)."""
        metadata = {
            "error_message": error_message,
            "error_type": error_type,
        }
        if exit_price:
            metadata["intended_exit_price"] = str(exit_price)
        if shares:
            metadata["intended_shares"] = shares
        metadata.update(self._get_market_context())
        
        # TML: Write to persistent file log for forensics
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_EXIT_FAILED,
            details=f"EXIT FAILED: {error_type} | {error_message}",
        )
        
        return self._log_event(
            strategy="WARRIOR",
            position_id=trade_id,
            symbol=symbol,
            event_type=self.WARRIOR_EXIT_FAILED,
            new_value=error_type,
            reason=f"Exit callback failed: {error_message}",
            metadata=metadata,
        )
    
    def log_warrior_guard_block(
        self,
        symbol: str,
        guard_name: str,
        reason: str,
        trigger_type: str = "unknown",
        price: float = None,
    ) -> None:
        """
        Log when an entry guard blocks a trade attempt.
        
        Writes to BOTH the TML file (forensic review) AND the database
        (queryable via Data Explorer → Trade Events tab).
        """
        price_str = f"${price:.2f}" if price else "N/A"
        details = f"guard={guard_name} | trigger={trigger_type} | price={price_str} | {reason}"
        
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_GUARD_BLOCK,
            details=details,
        )
        
        self._log_event(
            strategy="WARRIOR",
            position_id="GUARD_BLOCK",
            symbol=symbol,
            event_type=self.WARRIOR_GUARD_BLOCK,
            new_value=guard_name,
            reason=reason,
            metadata={
                "guard_name": guard_name,
                "trigger_type": trigger_type,
                "price": price,
            },
        )
    
    def log_warrior_reentry_enabled(
        self,
        symbol: str,
        exit_price: float,
        attempt_count: int,
    ) -> None:
        """Log Warrior re-entry enabled after profit exit (TML-only, no DB).
        
        This is a lightweight observability event — file log only to avoid
        noise in the events table. Primarily for forensic review of re-entry decisions.
        """
        self._log_to_file(
            strategy="WARRIOR",
            symbol=symbol,
            event_type=self.WARRIOR_REENTRY_ENABLED,
            details=f"Re-entry ENABLED after profit exit @ ${exit_price:.2f} (attempt #{attempt_count})",
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
