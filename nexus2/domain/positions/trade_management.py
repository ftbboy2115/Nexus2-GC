"""
Trade Management Service

Manages active trades through their lifecycle.
Based on: trade_management_research.md
"""

from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Protocol
from uuid import uuid4

from nexus2.domain.positions.trade_models import (
    ManagedTrade,
    TradeStatus,
    ExitReason,
    PartialExitRecord,
    PartialExitSignal,
    ExitSignal,
)
from nexus2.settings.risk_settings import PartialExitSettings


class NotificationService(Protocol):
    """Protocol for notifications."""
    
    def send_trade_alert(self, message: str, trade_id: str) -> None:
        """Send trade-related alert."""
        ...


class TradeManagementService:
    """
    Manages active trades through their lifecycle.
    
    Responsibilities:
    - Check partial exit conditions (time + gain)
    - Generate exit signals
    - Update trailing stops
    - Track trade performance
    - Send notifications
    """
    
    def __init__(
        self,
        partial_settings: PartialExitSettings,
        notifications: Optional[NotificationService] = None,
    ):
        self.partial_settings = partial_settings
        self.notifications = notifications
    
    def check_partial_exit(
        self,
        trade: ManagedTrade,
        current_price: Decimal,
    ) -> Optional[PartialExitSignal]:
        """
        Check if partial profit should be taken.
        
        KK Style: After 3-5 days AND up 10-15%, sell 1/3 to 1/2.
        
        Args:
            trade: Active trade
            current_price: Current price
            
        Returns:
            PartialExitSignal if conditions met, None otherwise
        """
        ps = self.partial_settings
        
        # Already had partial exit (only one partial per trade)
        if trade.is_breakeven_eligible:
            return None
        
        # Calculate gain
        gain_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100
        
        # Check conditions
        time_met = trade.days_held >= ps.partial_exit_days
        gain_met = gain_pct >= ps.partial_exit_gain_pct
        
        if ps.require_both_conditions:
            should_exit = time_met and gain_met
        else:
            should_exit = time_met or gain_met
        
        if not should_exit:
            return None
        
        # Create signal
        signal = PartialExitSignal.from_time_rule(
            trade=trade,
            fraction=ps.partial_exit_fraction,
            current_price=current_price,
        )
        
        # Send notification if enabled
        if self.notifications:
            self._send_partial_notification(trade, signal, gain_pct)
        
        return signal
    
    def execute_partial_exit(
        self,
        trade: ManagedTrade,
        shares: int,
        exit_price: Decimal,
        reason: ExitReason,
    ) -> ManagedTrade:
        """
        Execute a partial exit on a trade.
        
        Args:
            trade: Trade to partially exit
            shares: Number of shares to exit
            exit_price: Exit price
            reason: Reason for exit
            
        Returns:
            Updated trade
        """
        if shares > trade.remaining_shares:
            shares = trade.remaining_shares
        
        # Calculate P&L for this exit
        pnl = (exit_price - trade.entry_price) * shares
        pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
        r_mult = pnl / trade.initial_risk_dollars if trade.initial_risk_dollars > 0 else Decimal("0")
        
        # Record the exit
        record = PartialExitRecord(
            id=uuid4(),
            shares=shares,
            exit_price=exit_price,
            exit_date=date.today(),
            exit_time=datetime.now(),
            reason=reason,
            pnl=pnl,
            pnl_percent=pnl_pct,
            r_multiple=r_mult,
        )
        
        trade.partial_exits.append(record)
        trade.remaining_shares -= shares
        trade.realized_pnl += pnl
        trade.status = TradeStatus.PARTIAL_EXIT
        trade.updated_at = datetime.now()
        
        # Auto move to breakeven if enabled
        if self.partial_settings.move_to_breakeven_after:
            trade.current_stop = trade.entry_price
            trade.stop_type = "breakeven"
        
        return trade
    
    def check_trailing_exit(
        self,
        trade: ManagedTrade,
        close_price: Decimal,
        ma_value: Decimal,
    ) -> Optional[ExitSignal]:
        """
        Check if trailing MA exit is triggered.
        
        KK Style: Exit on first close below trailing MA.
        
        Args:
            trade: Active trade
            close_price: Daily closing price
            ma_value: Trailing MA value
            
        Returns:
            ExitSignal if triggered, None otherwise
        """
        if trade.stop_type != "trailing":
            return None
        
        if close_price < ma_value:
            return ExitSignal(
                trade_id=trade.id,
                exit_type="full",
                shares=trade.remaining_shares,
                reason=ExitReason.MA_CLOSE,
                trigger_price=ma_value,
                message=f"Close ${close_price:.2f} below {trade.trailing_ma_type} ${ma_value:.2f}",
            )
        
        return None
    
    def check_stop_hit(
        self,
        trade: ManagedTrade,
        current_price: Decimal,
    ) -> Optional[ExitSignal]:
        """
        Check if stop has been hit.
        
        Args:
            trade: Active trade
            current_price: Current price
            
        Returns:
            ExitSignal if stop hit, None otherwise
        """
        if current_price <= trade.current_stop:
            reason_map = {
                "initial": ExitReason.INITIAL_STOP,
                "breakeven": ExitReason.BREAKEVEN_STOP,
                "trailing": ExitReason.TRAILING_STOP,
            }
            reason = reason_map.get(trade.stop_type, ExitReason.INITIAL_STOP)
            
            return ExitSignal(
                trade_id=trade.id,
                exit_type="full",
                shares=trade.remaining_shares,
                reason=reason,
                trigger_price=trade.current_stop,
                message=f"Stop hit at ${trade.current_stop:.2f}",
            )
        
        return None
    
    def check_invalidation_breach(
        self,
        trade: ManagedTrade,
        current_price: Decimal,
    ) -> Optional[dict]:
        """
        Check if invalidation level has been breached (KK-style).
        
        This is ALERT ONLY - does not trigger auto-exit.
        If price breaches invalidation level, the setup is dead and
        trader should reassess (but might hold if tactical stop not hit).
        
        Args:
            trade: Active trade with invalidation_level set
            current_price: Current price
            
        Returns:
            Alert dict if breached, None otherwise
        """
        if not trade.invalidation_level:
            return None
        
        if current_price <= trade.invalidation_level:
            # Setup is invalidated, but don't auto-exit
            alert = {
                "trade_id": str(trade.id),
                "symbol": trade.symbol,
                "type": "invalidation_breach",
                "severity": "warning",
                "message": f"Setup invalidated: price ${current_price:.2f} below EP candle low ${trade.invalidation_level:.2f}",
                "action": "Consider closing if price action confirms breakdown",
            }
            
            # Send notification if available
            if self.notifications:
                self.notifications.send_trade_alert(
                    f"⚠️ SETUP INVALIDATED: {trade.symbol}\n"
                    f"Price ${current_price:.2f} below EP candle low ${trade.invalidation_level:.2f}\n"
                    f"Tactical stop: ${trade.current_stop:.2f}",
                    str(trade.id)
                )
            
            return alert
        
        return None
    
    def close_trade(
        self,
        trade: ManagedTrade,
        exit_price: Decimal,
        reason: ExitReason,
    ) -> ManagedTrade:
        """
        Close out remaining position.
        
        Args:
            trade: Trade to close
            exit_price: Exit price
            reason: Reason for closing
            
        Returns:
            Updated trade
        """
        # Calculate final P&L
        final_pnl = (exit_price - trade.entry_price) * trade.remaining_shares
        trade.realized_pnl += final_pnl
        
        # Update trade
        trade.remaining_shares = 0
        trade.final_exit_price = exit_price
        trade.final_exit_date = date.today()
        trade.final_exit_reason = reason
        trade.status = TradeStatus.CLOSED
        trade.updated_at = datetime.now()
        
        # Notify
        if self.notifications:
            self._send_close_notification(trade, exit_price, reason)
        
        return trade
    
    def get_trades_needing_attention(
        self,
        trades: List[ManagedTrade],
        current_prices: dict,  # symbol -> price
    ) -> List[dict]:
        """
        Get trades that need attention.
        
        Checks for:
        - Partial exit eligibility
        - Near stop
        - Extended gains
        
        Returns:
            List of attention items
        """
        attention = []
        
        for trade in trades:
            if trade.status == TradeStatus.CLOSED:
                continue
            
            price = current_prices.get(trade.symbol)
            if not price:
                continue
            
            # Check partial exit
            signal = self.check_partial_exit(trade, price)
            if signal:
                attention.append({
                    "trade_id": str(trade.id),
                    "symbol": trade.symbol,
                    "type": "partial_exit",
                    "message": signal.message,
                })
            
            # Check near stop
            stop_distance_pct = ((price - trade.current_stop) / price) * 100
            if stop_distance_pct < Decimal("2.0"):
                attention.append({
                    "trade_id": str(trade.id),
                    "symbol": trade.symbol,
                    "type": "near_stop",
                    "message": f"Price within 2% of stop",
                })
        
        return attention
    
    def _send_partial_notification(
        self,
        trade: ManagedTrade,
        signal: PartialExitSignal,
        gain_pct: Decimal,
    ) -> None:
        """Send partial exit notification."""
        if self.notifications:
            msg = (
                f"🎯 PARTIAL EXIT SIGNAL: {trade.symbol}\n"
                f"Days held: {trade.days_held} | Gain: {gain_pct:.1f}%\n"
                f"Sell {signal.shares_to_exit} shares"
            )
            self.notifications.send_trade_alert(msg, str(trade.id))
    
    def _send_close_notification(
        self,
        trade: ManagedTrade,
        exit_price: Decimal,
        reason: ExitReason,
    ) -> None:
        """Send trade close notification."""
        if self.notifications:
            r_mult = trade.realized_pnl / trade.initial_risk_dollars if trade.initial_risk_dollars > 0 else 0
            emoji = "✅" if trade.realized_pnl > 0 else "❌"
            msg = (
                f"{emoji} TRADE CLOSED: {trade.symbol}\n"
                f"P&L: ${trade.realized_pnl:.2f} ({r_mult:.1f}R)\n"
                f"Reason: {reason.value}"
            )
            self.notifications.send_trade_alert(msg, str(trade.id))
