"""
Analytics Service

Calculate aggregate trading statistics from closed trades.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Dict
import logging

from nexus2.domain.analytics.models import TradeStats, SetupStats, ComparisonStats
from nexus2.domain.positions.trade_models import ManagedTrade, TradeStatus

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Calculate trading performance statistics.
    
    Metrics:
    - Win rate, avg win/loss
    - Expectancy, profit factor
    - R-multiple distribution
    - Max drawdown
    """
    
    def calculate_stats(
        self,
        trades: List[ManagedTrade],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> TradeStats:
        """
        Calculate aggregate stats from a list of trades.
        
        Args:
            trades: List of completed trades
            start_date: Optional start filter
            end_date: Optional end filter
            
        Returns:
            TradeStats with all metrics
        """
        # Filter to closed trades only
        closed = [t for t in trades if t.status in (TradeStatus.CLOSED, TradeStatus.STOPPED_OUT)]
        
        # Filter by date if provided
        if start_date:
            closed = [t for t in closed if t.entry_date >= start_date]
        if end_date:
            closed = [t for t in closed if t.final_exit_date and t.final_exit_date <= end_date]
        
        if not closed:
            return TradeStats(start_date=start_date, end_date=end_date)
        
        # Categorize trades
        winners = [t for t in closed if t.realized_pnl > 0]
        losers = [t for t in closed if t.realized_pnl < 0]
        breakeven = [t for t in closed if t.realized_pnl == 0]
        
        total = len(closed)
        
        # Calculate P&L
        gross_profit = sum(t.realized_pnl for t in winners) if winners else Decimal("0")
        gross_loss = abs(sum(t.realized_pnl for t in losers)) if losers else Decimal("0")
        net_profit = gross_profit - gross_loss
        
        # Win rate
        win_rate = Decimal(len(winners)) / Decimal(total) * 100 if total > 0 else Decimal("0")
        loss_rate = Decimal(len(losers)) / Decimal(total) * 100 if total > 0 else Decimal("0")
        
        # Averages
        avg_win = gross_profit / len(winners) if winners else Decimal("0")
        avg_loss = gross_loss / len(losers) if losers else Decimal("0")
        avg_trade = net_profit / total if total > 0 else Decimal("0")
        
        # R-multiples (if initial_risk_dollars available)
        r_multiples = []
        for t in closed:
            if t.initial_risk_dollars and t.initial_risk_dollars > 0:
                r = t.realized_pnl / t.initial_risk_dollars
                r_multiples.append(r)
        
        avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else Decimal("0")
        best_r = max(r_multiples) if r_multiples else Decimal("0")
        worst_r = min(r_multiples) if r_multiples else Decimal("0")
        
        # Profit factor
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else Decimal("999")
        
        # Payoff ratio
        payoff_ratio = avg_win / avg_loss if avg_loss > 0 else Decimal("999")
        
        # Expectancy: (win_rate × avg_win) - (loss_rate × avg_loss)
        wr = Decimal(len(winners)) / Decimal(total) if total > 0 else Decimal("0")
        lr = Decimal(len(losers)) / Decimal(total) if total > 0 else Decimal("0")
        expectancy = (wr * avg_win) - (lr * avg_loss)
        
        # Max drawdown (simple peak-to-trough on cumulative P&L)
        max_dd = self._calculate_max_drawdown(closed)
        
        # Days held
        winner_days = [t.days_held for t in winners if hasattr(t, 'days_held')]
        loser_days = [t.days_held for t in losers if hasattr(t, 'days_held')]
        avg_days_winners = Decimal(sum(winner_days)) / len(winner_days) if winner_days else Decimal("0")
        avg_days_losers = Decimal(sum(loser_days)) / len(loser_days) if loser_days else Decimal("0")
        
        # Determine date range from trades
        trade_start = min(t.entry_date for t in closed)
        trade_end = max(t.final_exit_date or t.entry_date for t in closed)
        
        return TradeStats(
            total_trades=total,
            winning_trades=len(winners),
            losing_trades=len(losers),
            breakeven_trades=len(breakeven),
            win_rate=win_rate,
            loss_rate=loss_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit=net_profit,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade=avg_trade,
            avg_r_multiple=avg_r,
            best_r=best_r,
            worst_r=worst_r,
            profit_factor=profit_factor,
            payoff_ratio=payoff_ratio,
            expectancy=expectancy,
            max_drawdown=max_dd,
            avg_days_held_winners=avg_days_winners,
            avg_days_held_losers=avg_days_losers,
            start_date=start_date or trade_start,
            end_date=end_date or trade_end,
        )
    
    def calculate_by_setup(self, trades: List[ManagedTrade]) -> List[SetupStats]:
        """
        Calculate stats grouped by setup type.
        
        Returns:
            List of SetupStats for each setup type
        """
        # Group trades by setup_type
        by_setup: Dict[str, List[ManagedTrade]] = {}
        for t in trades:
            setup = t.setup_type or "unknown"
            if setup not in by_setup:
                by_setup[setup] = []
            by_setup[setup].append(t)
        
        result = []
        for setup_type, setup_trades in by_setup.items():
            stats = self.calculate_stats(setup_trades)
            result.append(SetupStats(setup_type=setup_type, stats=stats))
        
        return result
    
    def compare_kk_vs_non_kk(self, trades: List[ManagedTrade]) -> ComparisonStats:
        """
        Compare KK-style trades (use_dual_stops=False) vs non-KK (use_dual_stops=True).
        """
        kk_trades = [t for t in trades if not getattr(t, 'use_dual_stops', False)]
        non_kk_trades = [t for t in trades if getattr(t, 'use_dual_stops', False)]
        
        return ComparisonStats(
            kk_style=self.calculate_stats(kk_trades),
            non_kk_style=self.calculate_stats(non_kk_trades),
        )
    
    def _calculate_max_drawdown(self, trades: List[ManagedTrade]) -> Decimal:
        """
        Calculate maximum drawdown from cumulative P&L curve.
        
        Simple method: sort trades by exit date, track running equity.
        """
        if not trades:
            return Decimal("0")
        
        # Sort by exit date
        sorted_trades = sorted(
            [t for t in trades if t.final_exit_date],
            key=lambda t: t.final_exit_date
        )
        
        if not sorted_trades:
            return Decimal("0")
        
        equity = Decimal("0")
        peak = Decimal("0")
        max_dd = Decimal("0")
        
        for trade in sorted_trades:
            equity += trade.realized_pnl
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            if drawdown > max_dd:
                max_dd = drawdown
        
        return max_dd


# Singleton instance
_service: Optional[AnalyticsService] = None

def get_analytics_service() -> AnalyticsService:
    """Get or create singleton service."""
    global _service
    if _service is None:
        _service = AnalyticsService()
    return _service
