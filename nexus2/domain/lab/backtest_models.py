"""
Backtest Models - Data structures for backtesting results.

Captures trade history, equity curve, and performance metrics.
"""

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class TradeDirection(str, Enum):
    """Trade direction."""
    LONG = "long"
    SHORT = "short"


class TradeOutcome(str, Enum):
    """Trade outcome category."""
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"


class BacktestTrade(BaseModel):
    """Individual trade record from a backtest."""
    
    # Identity
    trade_id: str = Field(..., description="Unique trade identifier")
    symbol: str = Field(..., description="Stock symbol")
    
    # Entry
    entry_time: datetime = Field(..., description="Entry timestamp")
    entry_price: Decimal = Field(..., description="Entry price")
    entry_shares: int = Field(..., description="Initial shares bought")
    entry_trigger: str = Field(default="", description="Entry trigger type (ORB, PMH, etc.)")
    
    # Exit
    exit_time: Optional[datetime] = Field(default=None, description="Exit timestamp")
    exit_price: Optional[Decimal] = Field(default=None, description="Exit price")
    exit_shares: Optional[int] = Field(default=None, description="Shares sold")
    exit_reason: str = Field(default="", description="Exit reason (stop, target, etc.)")
    
    # Risk management
    stop_price: Optional[Decimal] = Field(default=None, description="Stop loss price")
    target_price: Optional[Decimal] = Field(default=None, description="Profit target")
    risk_dollars: Optional[Decimal] = Field(default=None, description="Dollar risk on trade")
    
    # Results
    realized_pnl: Decimal = Field(default=Decimal("0"), description="Realized P&L")
    realized_r: Optional[float] = Field(default=None, description="P&L in R multiples")
    outcome: Optional[TradeOutcome] = Field(default=None, description="Win/loss/breakeven")
    
    # Scales (if any)
    scales: List[Dict[str, Any]] = Field(default_factory=list, description="Scale-in records")
    
    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat(),
        }


class BacktestMetrics(BaseModel):
    """Performance metrics from a backtest."""
    
    # Trade counts
    total_trades: int = Field(default=0, description="Total trades taken")
    winning_trades: int = Field(default=0, description="Number of winners")
    losing_trades: int = Field(default=0, description="Number of losers")
    breakeven_trades: int = Field(default=0, description="Number of breakeven")
    
    # Rates
    win_rate: float = Field(default=0.0, description="Win rate percentage")
    loss_rate: float = Field(default=0.0, description="Loss rate percentage")
    
    # R-multiples
    avg_r: float = Field(default=0.0, description="Average R-multiple")
    avg_win_r: float = Field(default=0.0, description="Average winning R")
    avg_loss_r: float = Field(default=0.0, description="Average losing R")
    max_win_r: float = Field(default=0.0, description="Best trade in R")
    max_loss_r: float = Field(default=0.0, description="Worst trade in R")
    
    # P&L
    total_pnl: Decimal = Field(default=Decimal("0"), description="Total P&L")
    gross_profit: Decimal = Field(default=Decimal("0"), description="Sum of winning trades")
    gross_loss: Decimal = Field(default=Decimal("0"), description="Sum of losing trades")
    profit_factor: float = Field(default=0.0, description="Gross profit / gross loss")
    
    # Risk metrics
    max_drawdown: float = Field(default=0.0, description="Maximum drawdown %")
    max_drawdown_dollars: Decimal = Field(default=Decimal("0"), description="Max DD in dollars")
    sharpe_ratio: Optional[float] = Field(default=None, description="Sharpe ratio")
    
    # Time analysis
    avg_hold_time_minutes: Optional[float] = Field(default=None, description="Avg trade duration")
    best_hour: Optional[int] = Field(default=None, description="Most profitable hour (ET)")
    worst_hour: Optional[int] = Field(default=None, description="Least profitable hour (ET)")
    
    class Config:
        json_encoders = {Decimal: str}


class EquityPoint(BaseModel):
    """Single point on equity curve."""
    timestamp: datetime
    equity: Decimal
    drawdown: float = Field(default=0.0, description="Drawdown % from peak")


class BacktestResult(BaseModel):
    """Complete backtest result with trades, metrics, and equity curve."""
    
    # Identity
    result_id: str = Field(..., description="Unique result identifier")
    strategy_name: str = Field(..., description="Strategy name")
    strategy_version: str = Field(..., description="Strategy version")
    
    # Parameters
    start_date: date = Field(..., description="Backtest start date")
    end_date: date = Field(..., description="Backtest end date")
    initial_capital: Decimal = Field(..., description="Starting capital")
    
    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    duration_seconds: Optional[float] = Field(default=None)
    
    # Results
    final_equity: Decimal = Field(default=Decimal("0"), description="Ending capital")
    total_return: float = Field(default=0.0, description="Total return %")
    
    # Components
    trades: List[BacktestTrade] = Field(default_factory=list)
    metrics: BacktestMetrics = Field(default_factory=BacktestMetrics)
    equity_curve: List[EquityPoint] = Field(default_factory=list)
    
    # Metadata
    symbols_traded: List[str] = Field(default_factory=list, description="Unique symbols")
    trading_days: int = Field(default=0, description="Number of trading days")
    
    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
        }


class BacktestComparison(BaseModel):
    """Comparison between two backtest results."""
    
    baseline: BacktestResult
    variant: BacktestResult
    
    # Deltas
    win_rate_delta: float = Field(default=0.0, description="Win rate difference")
    avg_r_delta: float = Field(default=0.0, description="Avg R difference")
    total_return_delta: float = Field(default=0.0, description="Total return difference")
    sharpe_delta: Optional[float] = Field(default=None, description="Sharpe difference")
    max_dd_delta: float = Field(default=0.0, description="Max DD difference (positive = less DD)")
    
    # Verdict
    improvement_score: float = Field(default=0.0, description="Weighted improvement score")
    recommendation: str = Field(default="", description="iterate/promote/reject")
    summary: str = Field(default="", description="Human-readable summary")
