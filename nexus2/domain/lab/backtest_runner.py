"""
Backtest Runner - Execute strategies against historical data.

Replays market data through strategy scanner/engine/monitor
and captures trades, equity curve, and performance metrics.
"""

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
import math

from .backtest_models import (
    BacktestTrade,
    BacktestResult,
    BacktestMetrics,
    BacktestComparison,
    EquityPoint,
    TradeOutcome,
)
from .strategy_schema import StrategySpec
from .historical_loader import get_historical_loader
from .lab_logger import log_backtest_start, log_backtest_complete, log_backtest_trade


logger = logging.getLogger(__name__)


class BacktestRunner:
    """Executes backtests against historical market data."""
    
    def __init__(self):
        self.loader = get_historical_loader()
    
    def run(
        self,
        strategy: StrategySpec,
        start_date: date,
        end_date: date,
        initial_capital: Decimal = Decimal("25000"),
        symbols: Optional[List[str]] = None,
    ) -> BacktestResult:
        """Run a backtest for a strategy.
        
        Args:
            strategy: Strategy specification to test
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Starting capital
            symbols: Optional list of symbols to test (else uses gapper universe)
            
        Returns:
            BacktestResult with trades, metrics, and equity curve
        """
        started_at = datetime.utcnow()
        result_id = str(uuid.uuid4())[:8]
        
        logger.info(f"[Backtest] Starting {strategy.name} v{strategy.version} "
                   f"from {start_date} to {end_date}")
        
        # Log to dedicated lab.log
        log_backtest_start(
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            start_date=str(start_date),
            end_date=str(end_date),
            initial_capital=float(initial_capital),
        )
        
        # Initialize tracking
        equity = initial_capital
        peak_equity = initial_capital
        trades: List[BacktestTrade] = []
        equity_curve: List[EquityPoint] = []
        symbols_traded: set = set()
        
        # Iterate through trading days
        current_date = start_date
        trading_days = 0
        
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            trading_days += 1
            
            # Get symbols for this day (gapper universe or provided list)
            day_symbols = symbols or self._get_day_symbols(current_date, strategy)
            
            # Simulate trades for each symbol
            for symbol in day_symbols[:strategy.engine.max_positions]:
                trade = self._simulate_trade(symbol, current_date, strategy, equity)
                
                if trade:
                    trades.append(trade)
                    equity += trade.realized_pnl
                    symbols_traded.add(symbol)
                    
                    # Update peak and record equity point
                    if equity > peak_equity:
                        peak_equity = equity
                    
                    drawdown = float((peak_equity - equity) / peak_equity * 100) if peak_equity > 0 else 0
                    equity_curve.append(EquityPoint(
                        timestamp=datetime.combine(current_date, datetime.min.time()),
                        equity=equity,
                        drawdown=drawdown,
                    ))
            
            current_date += timedelta(days=1)
        
        # Calculate metrics
        metrics = self._calculate_metrics(trades, initial_capital, equity, peak_equity)
        
        completed_at = datetime.utcnow()
        duration = (completed_at - started_at).total_seconds()
        
        total_return = float((equity - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0
        
        # Log individual trades to lab.log
        for trade in trades:
            log_backtest_trade(
                symbol=trade.symbol,
                entry_price=float(trade.entry_price),
                exit_price=float(trade.exit_price) if trade.exit_price else 0,
                shares=trade.entry_shares,
                pnl=float(trade.realized_pnl),
                outcome=trade.outcome.value if trade.outcome else "unknown",
                exit_reason=trade.exit_reason or "unknown",
            )
        
        # Log completion to lab.log
        log_backtest_complete(
            strategy_name=strategy.name,
            result_id=result_id,
            total_trades=len(trades),
            win_rate=metrics.win_rate,
            total_pnl=float(metrics.total_pnl),
            duration_seconds=duration,
        )
        
        return BacktestResult(
            result_id=result_id,
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            final_equity=equity,
            total_return=total_return,
            trades=trades,
            metrics=metrics,
            equity_curve=equity_curve,
            symbols_traded=list(symbols_traded),
            trading_days=trading_days,
        )
    
    def _get_day_symbols(self, target_date: date, strategy: StrategySpec) -> List[str]:
        """Get symbols to trade for a given day based on strategy criteria."""
        # Use historical loader to get gapper universe
        gappers = self.loader.get_gapper_universe(
            target_date,
            min_gap_percent=strategy.scanner.min_gap_percent,
            min_price=float(strategy.scanner.min_price),
            min_volume=strategy.scanner.min_volume,
        )
        return [g["symbol"] for g in gappers]
    
    def _simulate_trade(
        self,
        symbol: str,
        trade_date: date,
        strategy: StrategySpec,
        available_capital: Decimal,
    ) -> Optional[BacktestTrade]:
        """Simulate a trade for a symbol on a given day.
        
        Uses intraday bars if available, falls back to daily OHLC simulation.
        """
        # Try intraday bars first
        bars = self.loader.get_intraday_bars(symbol, trade_date, interval="5min")
        
        if bars and len(bars) >= 10:
            return self._simulate_intraday_trade(symbol, trade_date, strategy, bars)
        
        # Fallback to daily bar simulation
        return self._simulate_daily_trade(symbol, trade_date, strategy)
    
    def _simulate_daily_trade(
        self,
        symbol: str,
        trade_date: date,
        strategy: StrategySpec,
    ) -> Optional[BacktestTrade]:
        """Simulate trade using daily OHLC bar (when intraday not available)."""
        # Get the daily bar for target date
        bars = self.loader.get_daily_bars(symbol, trade_date, trade_date)
        
        if not bars:
            return None
        
        bar = bars[0]
        
        # Entry at open
        entry_price = Decimal(str(bar["open"]))
        high = Decimal(str(bar["high"]))
        low = Decimal(str(bar["low"]))
        close = Decimal(str(bar["close"]))
        
        # Calculate stop and target
        stop_distance = Decimal(str(strategy.monitor.stop_cents or 15)) / 100
        stop_price = entry_price - stop_distance
        target_price = entry_price + (stop_distance * Decimal(str(strategy.monitor.target_r)))
        
        # Calculate position size
        risk_per_trade = strategy.engine.risk_per_trade
        shares = int(risk_per_trade / stop_distance) if stop_distance > 0 else 0
        
        if shares <= 0:
            return None
        
        # Cap to max position size
        max_shares = int(strategy.engine.max_position_size / entry_price)
        shares = min(shares, max_shares)
        
        # Determine outcome based on daily bar
        # Conservative: assume stop hit if low <= stop, else check target
        if low <= stop_price:
            exit_price = stop_price
            exit_reason = "stop"
        elif high >= target_price:
            exit_price = target_price
            exit_reason = "target"
        else:
            exit_price = close
            exit_reason = "eod"
        
        # Calculate P&L
        pnl = (exit_price - entry_price) * shares
        r_multiple = float(pnl / risk_per_trade) if risk_per_trade > 0 else 0
        
        # Determine outcome
        if pnl > Decimal("1"):
            outcome = TradeOutcome.WIN
        elif pnl < Decimal("-1"):
            outcome = TradeOutcome.LOSS
        else:
            outcome = TradeOutcome.BREAKEVEN
        
        entry_time = datetime.combine(trade_date, datetime.strptime("09:35", "%H:%M").time())
        exit_time = datetime.combine(trade_date, datetime.strptime("16:00", "%H:%M").time())
        
        return BacktestTrade(
            trade_id=f"{trade_date.isoformat()}_{symbol}",
            symbol=symbol,
            entry_time=entry_time,
            entry_price=entry_price,
            entry_shares=shares,
            entry_trigger=strategy.engine.entry_triggers[0] if strategy.engine.entry_triggers else "gap",
            exit_time=exit_time,
            exit_price=exit_price,
            exit_shares=shares,
            exit_reason=exit_reason,
            stop_price=stop_price,
            target_price=target_price,
            risk_dollars=risk_per_trade,
            realized_pnl=pnl,
            realized_r=r_multiple,
            outcome=outcome,
        )
    
    def _simulate_intraday_trade(
        self,
        symbol: str,
        trade_date: date,
        strategy: StrategySpec,
        bars: List[Dict],
    ) -> Optional[BacktestTrade]:
        """Simulate trade using intraday bars (detailed simulation)."""
        # Entry at first bar after 9:35 AM
        entry_bar = None
        for bar in bars:
            bar_time = datetime.fromisoformat(bar["timestamp"])
            if bar_time.hour == 9 and bar_time.minute >= 35:
                entry_bar = bar
                break
        
        if not entry_bar:
            return None
        
        entry_price = Decimal(str(entry_bar["close"]))
        
        # Calculate stop and target
        stop_distance = Decimal(str(strategy.monitor.stop_cents or 15)) / 100
        stop_price = entry_price - stop_distance
        target_price = entry_price + (stop_distance * Decimal(str(strategy.monitor.target_r)))
        
        # Calculate position size
        risk_per_trade = strategy.engine.risk_per_trade
        shares = int(risk_per_trade / stop_distance) if stop_distance > 0 else 0
        
        if shares <= 0:
            return None
        
        # Cap to max position size
        max_shares = int(strategy.engine.max_position_size / entry_price)
        shares = min(shares, max_shares)
        
        # Simulate exit by scanning remaining bars
        exit_bar = None
        exit_price = None
        exit_reason = ""
        
        entry_time = datetime.fromisoformat(entry_bar["timestamp"])
        
        for bar in bars:
            bar_time = datetime.fromisoformat(bar["timestamp"])
            if bar_time <= entry_time:
                continue
            
            bar_low = Decimal(str(bar["low"]))
            bar_high = Decimal(str(bar["high"]))
            
            # Check stop hit
            if bar_low <= stop_price:
                exit_bar = bar
                exit_price = stop_price
                exit_reason = "stop"
                break
            
            # Check target hit
            if bar_high >= target_price:
                exit_bar = bar
                exit_price = target_price
                exit_reason = "target"
                break
        
        # If no exit, close at last bar (EOD)
        if not exit_bar:
            exit_bar = bars[-1]
            exit_price = Decimal(str(exit_bar["close"]))
            exit_reason = "eod"
        
        # Calculate P&L
        pnl = (exit_price - entry_price) * shares
        r_multiple = float(pnl / risk_per_trade) if risk_per_trade > 0 else 0
        
        # Determine outcome
        if pnl > Decimal("1"):
            outcome = TradeOutcome.WIN
        elif pnl < Decimal("-1"):
            outcome = TradeOutcome.LOSS
        else:
            outcome = TradeOutcome.BREAKEVEN
        
        return BacktestTrade(
            trade_id=f"{trade_date.isoformat()}_{symbol}",
            symbol=symbol,
            entry_time=entry_time,
            entry_price=entry_price,
            entry_shares=shares,
            entry_trigger=strategy.engine.entry_triggers[0] if strategy.engine.entry_triggers else "unknown",
            exit_time=datetime.fromisoformat(exit_bar["timestamp"]),
            exit_price=exit_price,
            exit_shares=shares,
            exit_reason=exit_reason,
            stop_price=stop_price,
            target_price=target_price,
            risk_dollars=risk_per_trade,
            realized_pnl=pnl,
            realized_r=r_multiple,
            outcome=outcome,
        )
    
    def _calculate_metrics(
        self,
        trades: List[BacktestTrade],
        initial_capital: Decimal,
        final_equity: Decimal,
        peak_equity: Decimal,
    ) -> BacktestMetrics:
        """Calculate performance metrics from trades."""
        
        if not trades:
            return BacktestMetrics()
        
        # Categorize trades
        wins = [t for t in trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in trades if t.outcome == TradeOutcome.LOSS]
        breakevens = [t for t in trades if t.outcome == TradeOutcome.BREAKEVEN]
        
        total = len(trades)
        win_count = len(wins)
        loss_count = len(losses)
        
        # Rates (stored as decimals 0.0-1.0 for proper % formatting)
        win_rate = (win_count / total) if total > 0 else 0
        loss_rate = (loss_count / total) if total > 0 else 0
        
        # R-multiples
        all_r = [t.realized_r for t in trades if t.realized_r is not None]
        win_r = [t.realized_r for t in wins if t.realized_r is not None]
        loss_r = [t.realized_r for t in losses if t.realized_r is not None]
        
        avg_r = sum(all_r) / len(all_r) if all_r else 0
        avg_win_r = sum(win_r) / len(win_r) if win_r else 0
        avg_loss_r = sum(loss_r) / len(loss_r) if loss_r else 0
        max_win_r = max(all_r) if all_r else 0
        max_loss_r = min(all_r) if all_r else 0
        
        # P&L
        total_pnl = sum(t.realized_pnl for t in trades)
        gross_profit = sum(t.realized_pnl for t in wins)
        gross_loss = abs(sum(t.realized_pnl for t in losses))
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0
        
        # Drawdown
        max_dd_pct = float((peak_equity - final_equity) / peak_equity * 100) if peak_equity > 0 else 0
        max_dd_dollars = peak_equity - final_equity
        
        # Hold time
        hold_times = []
        for t in trades:
            if t.entry_time and t.exit_time:
                delta = (t.exit_time - t.entry_time).total_seconds() / 60
                hold_times.append(delta)
        avg_hold = sum(hold_times) / len(hold_times) if hold_times else None
        
        # Sharpe (simplified - daily returns)
        # Would need proper daily P&L series for accurate calculation
        sharpe = None
        if total > 10 and avg_r != 0:
            std_r = math.sqrt(sum((r - avg_r) ** 2 for r in all_r) / len(all_r)) if len(all_r) > 1 else 1
            sharpe = (avg_r / std_r) * math.sqrt(252) if std_r > 0 else None
        
        return BacktestMetrics(
            total_trades=total,
            winning_trades=win_count,
            losing_trades=loss_count,
            breakeven_trades=len(breakevens),
            win_rate=win_rate,
            loss_rate=loss_rate,
            avg_r=avg_r,
            avg_win_r=avg_win_r,
            avg_loss_r=avg_loss_r,
            max_win_r=max_win_r,
            max_loss_r=max_loss_r,
            total_pnl=total_pnl,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            max_drawdown=max_dd_pct,
            max_drawdown_dollars=max_dd_dollars,
            sharpe_ratio=sharpe,
            avg_hold_time_minutes=avg_hold,
        )
    
    def compare(
        self,
        baseline: BacktestResult,
        variant: BacktestResult,
    ) -> BacktestComparison:
        """Compare two backtest results.
        
        Args:
            baseline: The baseline/production strategy result
            variant: The experimental variant result
            
        Returns:
            BacktestComparison with deltas and recommendation
        """
        # Calculate deltas
        win_rate_delta = variant.metrics.win_rate - baseline.metrics.win_rate
        avg_r_delta = variant.metrics.avg_r - baseline.metrics.avg_r
        total_return_delta = variant.total_return - baseline.total_return
        max_dd_delta = baseline.metrics.max_drawdown - variant.metrics.max_drawdown  # Positive = less DD
        
        sharpe_delta = None
        if baseline.metrics.sharpe_ratio and variant.metrics.sharpe_ratio:
            sharpe_delta = variant.metrics.sharpe_ratio - baseline.metrics.sharpe_ratio
        
        # Calculate improvement score (weighted)
        # 40% win rate, 30% Sharpe, 20% DD, 10% min trades
        score = 0.0
        score += 0.40 * (win_rate_delta / 100)  # Normalize to 0-1 range
        if sharpe_delta:
            score += 0.30 * (sharpe_delta / 2)  # Sharpe delta scaled
        score += 0.20 * (1.0 if max_dd_delta >= 0 else 0.0)
        score += 0.10 * (1.0 if variant.metrics.total_trades >= 30 else 0.0)
        
        # Recommendation
        if score >= 0.6:
            recommendation = "promote"
            summary = f"Variant shows {win_rate_delta:+.1f}% win rate improvement"
        elif score >= 0.3:
            recommendation = "iterate"
            summary = f"Variant shows promise but needs refinement"
        else:
            recommendation = "reject"
            summary = f"Variant underperforms baseline"
        
        return BacktestComparison(
            baseline=baseline,
            variant=variant,
            win_rate_delta=win_rate_delta,
            avg_r_delta=avg_r_delta,
            total_return_delta=total_return_delta,
            sharpe_delta=sharpe_delta,
            max_dd_delta=max_dd_delta,
            improvement_score=score,
            recommendation=recommendation,
            summary=summary,
        )


# Singleton
_runner: Optional[BacktestRunner] = None


def get_backtest_runner() -> BacktestRunner:
    """Get the singleton backtest runner."""
    global _runner
    if _runner is None:
        _runner = BacktestRunner()
    return _runner
