"""
Analytics Models

Data structures for trading performance analytics.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional, List, Dict


@dataclass
class TradeStats:
    """Aggregate trading statistics."""
    
    # Trade counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    
    # Win rate
    win_rate: Decimal = Decimal("0")
    loss_rate: Decimal = Decimal("0")
    
    # P&L
    gross_profit: Decimal = Decimal("0")
    gross_loss: Decimal = Decimal("0")
    net_profit: Decimal = Decimal("0")
    
    # Averages
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    avg_trade: Decimal = Decimal("0")
    
    # Risk metrics
    avg_r_multiple: Decimal = Decimal("0")
    best_r: Decimal = Decimal("0")
    worst_r: Decimal = Decimal("0")
    
    # Ratio metrics
    profit_factor: Decimal = Decimal("0")  # gross_profit / gross_loss
    payoff_ratio: Decimal = Decimal("0")   # avg_win / avg_loss
    expectancy: Decimal = Decimal("0")     # Expected $ per trade
    
    # Drawdown
    max_drawdown: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    
    # Time-based
    avg_days_held_winners: Decimal = Decimal("0")
    avg_days_held_losers: Decimal = Decimal("0")
    
    # Period
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    def to_dict(self) -> Dict:
        """Convert to dict for API response."""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": float(self.win_rate),
            "gross_profit": float(self.gross_profit),
            "gross_loss": float(self.gross_loss),
            "net_profit": float(self.net_profit),
            "avg_win": float(self.avg_win),
            "avg_loss": float(self.avg_loss),
            "avg_r_multiple": float(self.avg_r_multiple),
            "best_r": float(self.best_r),
            "worst_r": float(self.worst_r),
            "profit_factor": float(self.profit_factor),
            "payoff_ratio": float(self.payoff_ratio),
            "expectancy": float(self.expectancy),
            "max_drawdown": float(self.max_drawdown),
            "avg_days_held_winners": float(self.avg_days_held_winners),
            "avg_days_held_losers": float(self.avg_days_held_losers),
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
        }


@dataclass
class SetupStats:
    """Stats grouped by setup type."""
    setup_type: str
    stats: TradeStats


@dataclass
class ComparisonStats:
    """Compare KK-style vs non-KK trades."""
    kk_style: TradeStats  # use_dual_stops = False
    non_kk_style: TradeStats  # use_dual_stops = True
