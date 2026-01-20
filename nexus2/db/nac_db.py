"""
NAC Trading Database

Separate SQLite database for NAC (Kristjan Qullamaggie) strategy.
Keeps NAC trades isolated from Warrior data.
Provides PSM integration with order ID tracking.
"""

import os
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

# PSM integration
from nexus2.domain.positions.position_state_machine import PositionStatus
from nexus2.utils.time_utils import now_utc

# Database path
DB_DIR = Path(__file__).parent.parent.parent / "data"
DB_DIR.mkdir(exist_ok=True)
NAC_DB_PATH = DB_DIR / "nac.db"
NAC_DATABASE_URL = f"sqlite:///{NAC_DB_PATH}"

# Create engine
nac_engine = create_engine(
    NAC_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Session factory
NACSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=nac_engine)

# Base class for NAC models
NACBase = declarative_base()


class NACTradeModel(NACBase):
    """NAC Trading trade log for restart recovery and PSM tracking."""
    __tablename__ = "nac_trades"
    
    id = Column(String(36), primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)  # PSM states
    
    # Entry info
    entry_price = Column(String(20), nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    setup_type = Column(String(20), nullable=True)  # ep, breakout, htf
    
    # Stop/Target
    stop_price = Column(String(20), nullable=False)
    target_price = Column(String(20), nullable=True)
    
    # Exit info (when closed)
    exit_price = Column(String(20), nullable=True)
    exit_time = Column(DateTime, nullable=True)
    exit_reason = Column(String(50), nullable=True)  # trend_breakdown, profit_target, eod
    
    # P&L
    realized_pnl = Column(String(20), default="0")
    
    # Partial tracking
    partial_taken = Column(Boolean, default=False)
    remaining_quantity = Column(Integer, nullable=True)
    
    # Broker order tracking (PSM core)
    entry_order_id = Column(String(36), nullable=True)  # Alpaca order ID for entry
    exit_order_id = Column(String(36), nullable=True)   # Alpaca order ID for exit
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "status": self.status,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "setup_type": self.setup_type,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_reason": self.exit_reason,
            "realized_pnl": self.realized_pnl,
            "partial_taken": self.partial_taken,
            "remaining_quantity": self.remaining_quantity,
            "entry_order_id": self.entry_order_id,
            "exit_order_id": self.exit_order_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@contextmanager
def get_nac_session():
    """Context manager for NAC database sessions."""
    db = NACSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_nac_db():
    """Initialize NAC database tables."""
    NACBase.metadata.create_all(bind=nac_engine)
    print(f"[NAC DB] Initialized at {NAC_DB_PATH}")


# =============================================================================
# ENTRY TRACKING (PSM Phase 1: PENDING_FILL → OPEN)
# =============================================================================

def log_nac_entry(
    trade_id: str,
    symbol: str,
    entry_price: float,
    quantity: int,
    stop_price: float,
    setup_type: str = None,
    target_price: float = None,
):
    """
    Log a new NAC trade entry as PENDING_FILL.
    
    Called immediately after submitting order to broker.
    Order ID is set separately via set_entry_order_id() once broker responds.
    """
    with get_nac_session() as db:
        trade = NACTradeModel(
            id=trade_id,
            symbol=symbol,
            status=PositionStatus.PENDING_FILL.value,
            entry_price=str(entry_price),
            quantity=quantity,
            entry_time=now_utc(),
            setup_type=setup_type,
            stop_price=str(stop_price),
            target_price=str(target_price) if target_price else None,
            remaining_quantity=quantity,
        )
        db.add(trade)
        db.commit()
        print(f"[NAC DB] Entry logged: {symbol} x{quantity} @ ${entry_price:.2f} (PENDING_FILL)")


def set_entry_order_id(trade_id: str, order_id: str) -> bool:
    """
    Store broker order ID for entry tracking.
    
    Called after broker returns order confirmation.
    """
    with get_nac_session() as db:
        trade = db.query(NACTradeModel).filter_by(id=trade_id).first()
        if trade:
            trade.entry_order_id = order_id
            trade.updated_at = now_utc()
            db.commit()
            print(f"[NAC DB] {trade.symbol}: Entry order ID set → {order_id[:8]}...")
            return True
        return False


def confirm_fill(trade_id: str, fill_price: float = None, filled_shares: int = None) -> bool:
    """
    Confirm order fill: PENDING_FILL → OPEN.
    
    Called when broker confirms the fill.
    Optionally updates price/shares if different from submitted.
    """
    with get_nac_session() as db:
        trade = db.query(NACTradeModel).filter_by(id=trade_id).first()
        if not trade:
            print(f"[NAC DB] confirm_fill: Trade not found: {trade_id}")
            return False
        
        if trade.status != PositionStatus.PENDING_FILL.value:
            print(f"[NAC DB] {trade.symbol}: Cannot confirm fill - status is {trade.status}")
            return False
        
        trade.status = PositionStatus.OPEN.value
        if fill_price:
            trade.entry_price = str(fill_price)
        if filled_shares:
            trade.quantity = filled_shares
            trade.remaining_quantity = filled_shares
        trade.updated_at = now_utc()
        db.commit()
        print(f"[NAC DB] {trade.symbol}: PENDING_FILL → OPEN")
        return True


# =============================================================================
# EXIT TRACKING (PSM Phase 2: OPEN → PENDING_EXIT → CLOSED)
# =============================================================================

def set_pending_exit(trade_id: str) -> bool:
    """
    Mark position as PENDING_EXIT before submitting exit order.
    
    Prevents duplicate exit orders.
    """
    with get_nac_session() as db:
        trade = db.query(NACTradeModel).filter_by(id=trade_id).first()
        if not trade:
            return False
        
        # Allow from OPEN or PARTIAL
        if trade.status not in [PositionStatus.OPEN.value, PositionStatus.PARTIAL.value]:
            print(f"[NAC DB] {trade.symbol}: Cannot exit - status is {trade.status}")
            return False
        
        old_status = trade.status
        trade.status = PositionStatus.PENDING_EXIT.value
        trade.updated_at = now_utc()
        db.commit()
        print(f"[NAC DB] {trade.symbol}: {old_status} → PENDING_EXIT")
        return True


def set_exit_order_id(trade_id: str, order_id: str) -> bool:
    """
    Store broker order ID for exit tracking.
    
    Called after broker returns exit order confirmation.
    """
    with get_nac_session() as db:
        trade = db.query(NACTradeModel).filter_by(id=trade_id).first()
        if trade:
            trade.exit_order_id = order_id
            trade.updated_at = now_utc()
            db.commit()
            print(f"[NAC DB] {trade.symbol}: Exit order ID set → {order_id[:8]}...")
            return True
        return False


def confirm_exit(
    trade_id: str,
    exit_price: float,
    exit_reason: str,
    quantity_exited: int = None,
) -> bool:
    """
    Confirm exit: PENDING_EXIT → CLOSED (or PARTIAL).
    
    Full exit: CLOSED
    Partial exit: PARTIAL with remaining_quantity updated
    """
    with get_nac_session() as db:
        trade = db.query(NACTradeModel).filter_by(id=trade_id).first()
        if not trade:
            return False
        
        if quantity_exited is None or quantity_exited >= trade.remaining_quantity:
            # Full exit
            trade.status = PositionStatus.CLOSED.value
            trade.exit_price = str(exit_price)
            trade.exit_time = now_utc()
            trade.exit_reason = exit_reason
            
            # Calculate P&L
            entry = float(trade.entry_price)
            pnl = (exit_price - entry) * trade.quantity
            trade.realized_pnl = str(round(pnl, 2))
            print(f"[NAC DB] {trade.symbol}: PENDING_EXIT → CLOSED (${pnl:+.2f})")
        else:
            # Partial exit
            trade.status = PositionStatus.PARTIAL.value
            trade.partial_taken = True
            trade.remaining_quantity -= quantity_exited
            print(f"[NAC DB] {trade.symbol}: PENDING_EXIT → PARTIAL ({trade.remaining_quantity} remaining)")
        
        trade.updated_at = now_utc()
        db.commit()
        return True


def revert_pending_exit(trade_id: str) -> bool:
    """
    Revert PENDING_EXIT → OPEN if exit order fails.
    """
    with get_nac_session() as db:
        trade = db.query(NACTradeModel).filter_by(id=trade_id).first()
        if trade and trade.status == PositionStatus.PENDING_EXIT.value:
            trade.status = PositionStatus.OPEN.value
            trade.exit_order_id = None
            trade.updated_at = now_utc()
            db.commit()
            print(f"[NAC DB] {trade.symbol}: PENDING_EXIT → OPEN (exit failed)")
            return True
        return False


# =============================================================================
# RECONCILIATION (Startup Sync)
# =============================================================================

def get_pending_fills() -> list:
    """Get all trades in PENDING_FILL state for startup sync."""
    with get_nac_session() as db:
        trades = db.query(NACTradeModel).filter_by(
            status=PositionStatus.PENDING_FILL.value
        ).all()
        return [t.to_dict() for t in trades]


def get_pending_exits() -> list:
    """Get all trades in PENDING_EXIT state for startup sync."""
    with get_nac_session() as db:
        trades = db.query(NACTradeModel).filter_by(
            status=PositionStatus.PENDING_EXIT.value
        ).all()
        return [t.to_dict() for t in trades]


def get_nac_trade_by_order_id(order_id: str):
    """Find trade by broker entry order ID (for sync recovery)."""
    with get_nac_session() as db:
        trade = db.query(NACTradeModel).filter_by(
            entry_order_id=order_id
        ).first()
        return trade.to_dict() if trade else None


def get_open_nac_trades() -> list:
    """Get all open/active NAC trades for restart recovery."""
    with get_nac_session() as db:
        active_statuses = [
            PositionStatus.OPEN.value,
            PositionStatus.PENDING_FILL.value,
            PositionStatus.PENDING_EXIT.value,
            PositionStatus.PARTIAL.value,
        ]
        trades = db.query(NACTradeModel).filter(
            NACTradeModel.status.in_(active_statuses)
        ).all()
        return [t.to_dict() for t in trades]


def get_nac_trade_by_symbol(symbol: str):
    """Get active trade for a symbol (if any)."""
    with get_nac_session() as db:
        active_statuses = [
            PositionStatus.OPEN.value,
            PositionStatus.PENDING_FILL.value,
            PositionStatus.PENDING_EXIT.value,
            PositionStatus.PARTIAL.value,
        ]
        trade = db.query(NACTradeModel).filter(
            NACTradeModel.symbol == symbol,
            NACTradeModel.status.in_(active_statuses)
        ).first()
        return trade.to_dict() if trade else None


def close_orphaned_nac_trades(active_symbols: set) -> list:
    """Close trades in DB that are not on broker."""
    closed = []
    with get_nac_session() as db:
        open_trades = db.query(NACTradeModel).filter(
            NACTradeModel.status == PositionStatus.OPEN.value
        ).all()
        
        for trade in open_trades:
            if trade.symbol not in active_symbols:
                print(f"[NAC DB] Closing orphan: {trade.symbol}")
                trade.status = PositionStatus.CLOSED.value
                trade.exit_reason = "orphan_cleanup"
                trade.exit_time = now_utc()
                closed.append(trade.symbol)
        
        db.commit()
    
    return closed
