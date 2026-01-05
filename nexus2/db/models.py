"""
Database Models

SQLAlchemy models for orders and positions.
"""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum, ForeignKey, Text, Boolean
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship

from nexus2.db.database import Base


class OrderModel(Base):
    """Order database model."""
    __tablename__ = "orders"
    
    id = Column(String(36), primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    side = Column(String(10), nullable=False)  # buy, sell
    order_type = Column(String(20), nullable=False)  # market, limit, stop, stop_limit
    status = Column(String(20), nullable=False, index=True)  # draft, pending, submitted, filled, cancelled, rejected
    
    quantity = Column(Integer, nullable=False)
    filled_quantity = Column(Integer, default=0)
    
    limit_price = Column(String(20), nullable=True)
    stop_price = Column(String(20), nullable=True)
    tactical_stop = Column(String(20), nullable=True)
    avg_fill_price = Column(String(20), nullable=True)
    
    # Setup info
    setup_type = Column(String(50), nullable=True)
    parent_order_id = Column(String(36), ForeignKey("orders.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    filled_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    
    # Relationships
    fills = relationship("FillModel", back_populates="order", cascade="all, delete-orphan")
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "status": self.status,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "tactical_stop": self.tactical_stop,
            "avg_fill_price": self.avg_fill_price,
            "setup_type": self.setup_type,
            "parent_order_id": self.parent_order_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
        }


class FillModel(Base):
    """Fill database model."""
    __tablename__ = "fills"
    
    id = Column(String(36), primary_key=True)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False, index=True)
    
    quantity = Column(Integer, nullable=False)
    price = Column(String(20), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship
    order = relationship("OrderModel", back_populates="fills")
    
    def to_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "quantity": self.quantity,
            "price": self.price,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

class PositionExitModel(Base):
    """Tracks individual exits from a position."""
    __tablename__ = "position_exits"
    
    id = Column(String(36), primary_key=True)
    position_id = Column(String(36), ForeignKey("positions.id"), nullable=False, index=True)
    shares = Column(Integer, nullable=False)
    exit_price = Column(String(20), nullable=False)
    reason = Column(String(50), nullable=True)  # partial_profit, stop_out, manual, etc.
    exit_order_id = Column(String(36), ForeignKey("orders.id"), nullable=True)
    exited_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def to_dict(self):
        return {
            "id": self.id,
            "position_id": self.position_id,
            "shares": self.shares,
            "exit_price": self.exit_price,
            "reason": self.reason,
            "exit_order_id": self.exit_order_id,
            "exited_at": self.exited_at.isoformat() if self.exited_at else None,
        }


class PositionModel(Base):
    """Position database model."""
    __tablename__ = "positions"
    
    id = Column(String(36), primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    setup_type = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, index=True)  # open, closed
    
    # Entry info
    entry_price = Column(String(20), nullable=False)
    shares = Column(Integer, nullable=False)
    remaining_shares = Column(Integer, nullable=False)
    
    # Stop info
    initial_stop = Column(String(20), nullable=True)
    current_stop = Column(String(20), nullable=True)
    
    # P&L
    realized_pnl = Column(String(20), default="0")
    unrealized_pnl = Column(String(20), default="0")
    
    # Timestamps
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    
    # Broker/Account context
    broker_type = Column(String(20), default="paper")  # paper, alpaca_paper
    account = Column(String(10), default="A")  # A or B
    
    # Related order
    entry_order_id = Column(String(36), ForeignKey("orders.id"), nullable=True)
    
    # Signal quality at entry (for tracking/analysis)
    quality_score = Column(Integer, nullable=True)
    tier = Column(String(20), nullable=True)  # FOCUS, WIDE
    rs_percentile = Column(Integer, nullable=True)
    adr_percent = Column(String(10), nullable=True)
    
    # Partial exit tracking (prevents repeated partial exits)
    partial_taken = Column(Boolean, default=False)
    
    # Trade source tracking (for analytics filtering)
    source = Column(String(20), default="manual")  # "nac", "manual", "external"
    
    # Exit data (for P&L calculation in analytics)
    exit_price = Column(String(20), nullable=True)
    exit_date = Column(DateTime, nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "setup_type": self.setup_type,
            "status": self.status,
            "entry_price": self.entry_price,
            "shares": self.shares,
            "remaining_shares": self.remaining_shares,
            "initial_stop": self.initial_stop,
            "current_stop": self.current_stop,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "broker_type": self.broker_type,
            "account": self.account,
            "entry_order_id": self.entry_order_id,
            "quality_score": self.quality_score,
            "tier": self.tier,
            "rs_percentile": self.rs_percentile,
            "adr_percent": self.adr_percent,
            "partial_taken": self.partial_taken,
            "source": self.source,
            "exit_price": self.exit_price,
            "exit_date": self.exit_date.isoformat() if self.exit_date else None,
            "days_held": (datetime.utcnow() - self.opened_at).days if self.opened_at else 0,
        }


class SettingsModel(Base):
    """User settings database model."""
    __tablename__ = "settings"
    
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SchedulerSettingsModel(Base):
    """Scheduler scan settings for automated trading."""
    __tablename__ = "scheduler_settings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Mode: use Quick Actions settings or custom
    adopt_quick_actions = Column(String(5), default="true")  # "true" or "false"
    
    # Preset mode (when not adopting Quick Actions)
    preset = Column(String(20), default="strict")  # strict, relaxed, custom
    
    # Custom settings
    min_quality = Column(Integer, default=7)
    stop_mode = Column(String(10), default="atr")  # atr or percent
    max_stop_atr = Column(String(10), default="1.0")
    max_stop_percent = Column(String(10), default="5.0")
    
    # Scanner selection (comma-separated: ep,breakout,htf)
    scan_modes = Column(String(50), default="ep,breakout,htf")
    
    # HTF timing: every_cycle or market_open (once since 9am)
    htf_frequency = Column(String(20), default="market_open")
    
    # Auto-execute orders when signals found (default False for safety)
    auto_execute = Column(String(5), default="false")  # "true" or "false"
    
    # Maximum position value for automation (overrides global max_per_symbol if set)
    # Stored as string to handle Decimal, None means use global setting
    max_position_value = Column(String(20), nullable=True, default=None)
    
    # Auto-start settings for headless operation
    auto_start_enabled = Column(String(5), default="false")  # "true" or "false"
    auto_start_time = Column(String(5), nullable=True, default=None)  # HH:MM format (ET timezone)
    
    # NAC-specific broker/account (separate from dashboard settings)
    nac_broker_type = Column(String(20), default="alpaca_paper")  # alpaca_paper, alpaca_live
    nac_account = Column(String(10), default="A")  # A or B (default A for Automation)
    
    # Simulation mode (uses MockBroker instead of real broker)
    sim_mode = Column(String(5), default="false")  # "true" or "false"
    
    # Minimum stock price filter for scanner (defaults to $5 if not set)
    min_price = Column(String(10), nullable=True, default=None)
    
    # Discord notification settings
    discord_alerts_enabled = Column(String(5), default="true")  # "true" or "false"
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "adopt_quick_actions": self.adopt_quick_actions == "true",
            "preset": self.preset,
            "min_quality": self.min_quality,
            "stop_mode": self.stop_mode,
            "max_stop_atr": float(self.max_stop_atr) if self.max_stop_atr else 1.0,
            "max_stop_percent": float(self.max_stop_percent) if self.max_stop_percent else 5.0,
            "scan_modes": self.scan_modes.split(",") if self.scan_modes else ["ep", "breakout", "htf"],
            "htf_frequency": self.htf_frequency,
            "auto_execute": self.auto_execute == "true",
            "max_position_value": float(self.max_position_value) if self.max_position_value else None,
            "auto_start_enabled": self.auto_start_enabled == "true",
            "auto_start_time": self.auto_start_time,
            "nac_broker_type": self.nac_broker_type or "alpaca_paper",
            "nac_account": self.nac_account or "A",
            "sim_mode": self.sim_mode == "true",
            "min_price": float(self.min_price) if self.min_price else 5.0,
            "discord_alerts_enabled": self.discord_alerts_enabled == "true",
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WatchlistCandidateModel(Base):
    """Watchlist candidate from scanner results."""
    __tablename__ = "watchlist_candidates"
    
    id = Column(String(36), primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    name = Column(String(200), nullable=True)
    
    # Source tracking
    source = Column(String(20), nullable=False)  # gainers, actives, screener
    tier = Column(String(20), nullable=False)  # FOCUS, WIDE, UNIVERSE
    
    # Metrics at scan time
    price = Column(String(20), nullable=True)
    change_pct = Column(String(10), nullable=True)
    quality_score = Column(Integer, nullable=True)
    rs_percentile = Column(Integer, nullable=True)
    adr_percent = Column(String(10), nullable=True)
    
    # Status
    status = Column(String(20), default="new")  # new, watching, traded, dismissed
    notes = Column(Text, nullable=True)
    
    # Timestamps
    scanned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "name": self.name,
            "source": self.source,
            "tier": self.tier,
            "price": self.price,
            "change_pct": self.change_pct,
            "quality_score": self.quality_score,
            "rs_percentile": self.rs_percentile,
            "adr_percent": self.adr_percent,
            "status": self.status,
            "notes": self.notes,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
