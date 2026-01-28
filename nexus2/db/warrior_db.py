"""
Warrior Trading Database

Separate SQLite database for Warrior Trading strategy.
Keeps Warrior trades isolated from KK-style Nexus data.
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
WARRIOR_DB_PATH = DB_DIR / "warrior.db"
WARRIOR_DATABASE_URL = f"sqlite:///{WARRIOR_DB_PATH}"

# Create engine
warrior_engine = create_engine(
    WARRIOR_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Session factory
WarriorSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=warrior_engine)

# Base class for Warrior models
WarriorBase = declarative_base()


class WarriorTradeModel(WarriorBase):
    """Warrior Trading trade log for restart recovery."""
    __tablename__ = "warrior_trades"
    
    id = Column(String(36), primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)  # open, closed
    
    # Entry info
    entry_price = Column(String(20), nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    trigger_type = Column(String(20), nullable=True)  # pmh_break, orb, bull_flag
    
    # Stop/Target
    stop_price = Column(String(20), nullable=False)
    stop_method = Column(String(20), nullable=True)  # vwap, candle_low, fallback_15c, etc.
    target_price = Column(String(20), nullable=True)
    support_level = Column(String(20), nullable=True)
    
    # Exit info (when closed)
    exit_price = Column(String(20), nullable=True)
    exit_time = Column(DateTime, nullable=True)
    exit_reason = Column(String(50), nullable=True)  # stop, target, partial, manual
    
    # P&L
    realized_pnl = Column(String(20), default="0")
    
    # Partial tracking
    partial_taken = Column(Boolean, default=False)
    remaining_quantity = Column(Integer, nullable=True)
    
    # Broker order tracking
    entry_order_id = Column(String(36), nullable=True)  # Alpaca order ID for entry
    exit_order_id = Column(String(36), nullable=True)   # Alpaca order ID for exit
    
    # Intraday tracking (for restart recovery)
    high_since_entry = Column(String(20), default="0")  # Track highest price
    
    # Quote vs Fill tracking (phantom quote detection)
    quote_price = Column(String(20), nullable=True)  # Price from quote at decision time
    limit_price = Column(String(20), nullable=True)  # Limit price sent to broker
    fill_price = Column(String(20), nullable=True)   # Actual fill price from broker
    slippage_cents = Column(String(20), nullable=True)  # fill - quote in cents
    quote_source = Column(String(20), nullable=True)  # Alpaca, Schwab, FMP, etc.
    
    # Exit mode tracking (base_hit or home_run)
    exit_mode = Column(String(20), nullable=True)  # Auto-selected based on quality_score
    
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
            "trigger_type": self.trigger_type,
            "stop_price": self.stop_price,
            "stop_method": self.stop_method,
            "target_price": self.target_price,
            "support_level": self.support_level,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_reason": self.exit_reason,
            "realized_pnl": self.realized_pnl,
            "partial_taken": self.partial_taken,
            "remaining_quantity": self.remaining_quantity,
            "entry_order_id": self.entry_order_id,
            "exit_order_id": self.exit_order_id,
            "high_since_entry": self.high_since_entry,
            "quote_price": self.quote_price,
            "limit_price": self.limit_price,
            "fill_price": self.fill_price,
            "slippage_cents": self.slippage_cents,
            "quote_source": self.quote_source,
            "exit_mode": self.exit_mode,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@contextmanager
def get_warrior_session():
    """Context manager for Warrior database sessions."""
    db = WarriorSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_warrior_db():
    """Initialize Warrior database tables."""
    WarriorBase.metadata.create_all(bind=warrior_engine)
    
    # Migration: Add new columns if they don't exist
    from sqlalchemy import text
    with warrior_engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE warrior_trades ADD COLUMN entry_order_id TEXT"))
            conn.commit()
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text("ALTER TABLE warrior_trades ADD COLUMN exit_order_id TEXT"))
            conn.commit()
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text("ALTER TABLE warrior_trades ADD COLUMN high_since_entry TEXT DEFAULT '0'"))
            conn.commit()
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text("ALTER TABLE warrior_trades ADD COLUMN stop_method TEXT"))
            conn.commit()
        except Exception:
            pass  # Column already exists
        # Quote tracking columns (phantom quote detection)
        for col in ["quote_price", "limit_price", "fill_price", "slippage_cents", "quote_source"]:
            try:
                conn.execute(text(f"ALTER TABLE warrior_trades ADD COLUMN {col} TEXT"))
                conn.commit()
            except Exception:
                pass  # Column already exists
        # Exit mode tracking
        try:
            conn.execute(text("ALTER TABLE warrior_trades ADD COLUMN exit_mode TEXT"))
            conn.commit()
        except Exception:
            pass  # Column already exists
    
    print(f"[Warrior DB] Initialized at {WARRIOR_DB_PATH}")


# =============================================================================
# TRADE LOG FUNCTIONS
# =============================================================================

def log_warrior_entry(
    trade_id: str,
    symbol: str,
    entry_price: float,
    quantity: int,
    stop_price: float,
    target_price: float,
    trigger_type: str = "pmh_break",
    support_level: float = None,
    high_since_entry: float = None,
    stop_method: str = None,
    # Quote tracking (phantom quote detection)
    quote_price: float = None,
    limit_price: float = None,
    quote_source: str = None,
    # Exit mode tracking
    exit_mode: str = None,  # "base_hit" or "home_run"
):
    """Log a new Warrior trade entry with quote tracking."""
    # Default high_since_entry to entry_price if not provided
    high = high_since_entry if high_since_entry is not None else entry_price
    
    with get_warrior_session() as db:
        trade = WarriorTradeModel(
            id=trade_id,
            symbol=symbol,
            status=PositionStatus.OPEN.value,
            entry_price=str(entry_price),
            quantity=quantity,
            entry_time=now_utc(),
            trigger_type=trigger_type,
            stop_price=str(stop_price),
            stop_method=stop_method,
            target_price=str(target_price),
            support_level=str(support_level) if support_level else None,
            remaining_quantity=quantity,
            high_since_entry=str(high),
            # Quote tracking
            quote_price=str(quote_price) if quote_price else None,
            limit_price=str(limit_price) if limit_price else None,
            quote_source=quote_source,
            exit_mode=exit_mode,
        )
        db.add(trade)
        db.commit()
        print(f"[Warrior DB] Logged entry: {symbol} x{quantity} @ ${entry_price:.2f} (exit_mode={exit_mode})")


def update_warrior_fill(
    trade_id: str,
    actual_entry_price: float,
    actual_stop_price: float,
    actual_quantity: int,
) -> bool:
    """
    Update a Warrior trade with actual fill price after broker confirmation.
    
    Called after order is filled to update intended price with actual fill.
    Does NOT overwrite trigger_type (that was set in the intent log).
    Also calculates slippage if quote_price was recorded.
    
    Args:
        trade_id: The trade ID to update
        actual_entry_price: Actual fill price from broker
        actual_stop_price: Recalculated stop based on actual fill
        actual_quantity: Actual filled quantity
    
    Returns:
        True if updated successfully, False if trade not found
    """
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(id=trade_id).first()
        if not trade:
            print(f"[Warrior DB] update_warrior_fill: Trade not found: {trade_id}")
            return False
        
        old_price = trade.entry_price
        trade.entry_price = str(actual_entry_price)
        trade.stop_price = str(actual_stop_price)
        trade.quantity = actual_quantity
        trade.remaining_quantity = actual_quantity
        trade.high_since_entry = str(actual_entry_price)  # Reset high to actual fill
        trade.fill_price = str(actual_entry_price)  # Record actual fill
        
        # Calculate slippage if we have quote_price
        if trade.quote_price:
            quote = float(trade.quote_price)
            slippage = (actual_entry_price - quote) * 100  # In cents
            trade.slippage_cents = str(round(slippage, 2))
        
        trade.updated_at = now_utc()
        db.commit()
        
        slippage_str = f", slippage={trade.slippage_cents}¢" if trade.slippage_cents else ""
        print(
            f"[Warrior DB] Updated fill: {trade.symbol} "
            f"${old_price} → ${actual_entry_price:.2f}{slippage_str}"
        )
        return True


def log_warrior_exit(
    trade_id: str,
    exit_price: float,
    exit_reason: str,
    quantity_exited: int = None,
):
    """Log a Warrior trade exit (full or partial)."""
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(id=trade_id).first()
        if not trade:
            print(f"[Warrior DB] Trade not found: {trade_id}")
            return
        
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
        else:
            # Partial exit - transition to PARTIAL state
            trade.status = PositionStatus.PARTIAL.value
            trade.partial_taken = True
            trade.remaining_quantity -= quantity_exited
        
        db.commit()
        print(f"[Warrior DB] Logged exit: {trade.symbol} @ ${exit_price:.2f} ({exit_reason})")


def get_open_warrior_trades():
    """Get all open/active Warrior trades for restart recovery."""
    with get_warrior_session() as db:
        # Include all active states + legacy "open" for backwards compatibility
        active_statuses = [
            PositionStatus.OPEN.value,
            PositionStatus.PENDING_FILL.value,
            PositionStatus.PENDING_EXIT.value,
            PositionStatus.PARTIAL.value,
            PositionStatus.SCALING.value,
            "open",  # Legacy compatibility
        ]
        trades = db.query(WarriorTradeModel).filter(
            WarriorTradeModel.status.in_(active_statuses)
        ).all()
        return [t.to_dict() for t in trades]


def get_warrior_trade_by_symbol(symbol: str, status: str = None):
    """Get open/active trade for a symbol (if any).
    
    Args:
        symbol: Stock symbol to look up
        status: Optional specific status to filter (e.g., "pending_exit"). 
                If None, returns any active trade.
    """
    with get_warrior_session() as db:
        if status:
            # Filter by specific status
            trade = db.query(WarriorTradeModel).filter(
                WarriorTradeModel.symbol == symbol,
                WarriorTradeModel.status == status
            ).first()
        else:
            # Check for active states (open, pending_fill, pending_exit, partial, scaling)
            active_statuses = [
                PositionStatus.OPEN.value,
                PositionStatus.PENDING_FILL.value,
                PositionStatus.PENDING_EXIT.value,
                PositionStatus.PARTIAL.value,
                PositionStatus.SCALING.value,
            ]
            trade = db.query(WarriorTradeModel).filter(
                WarriorTradeModel.symbol == symbol,
                WarriorTradeModel.status.in_(active_statuses)
            ).first()
        return trade.to_dict() if trade else None


def get_warrior_trade_for_recovery(symbol: str, broker_entry_price: float):
    """Get a trade for broker sync recovery, matching by symbol + entry price.
    
    This function is used during broker sync to find existing trades regardless
    of status. It prevents duplicate "external" records from being created when
    the position already exists in the DB (even if status is 'closed').
    
    Args:
        symbol: Stock symbol to look up
        broker_entry_price: Entry price from broker to match
        
    Returns:
        Trade dict if found (prioritizing active status, then recent), else None
    """
    with get_warrior_session() as db:
        # First try: find by symbol with active status (most reliable)
        active_statuses = [
            PositionStatus.OPEN.value,
            PositionStatus.PENDING_FILL.value,
            PositionStatus.PENDING_EXIT.value,
            PositionStatus.PARTIAL.value,
            PositionStatus.SCALING.value,
        ]
        trade = db.query(WarriorTradeModel).filter(
            WarriorTradeModel.symbol == symbol,
            WarriorTradeModel.status.in_(active_statuses)
        ).first()
        
        if trade:
            return trade.to_dict()
        
        # Second try: find by symbol + entry price (within $0.05 tolerance)
        # This catches trades that exist but have a different status
        price_tolerance = 0.05
        trade = db.query(WarriorTradeModel).filter(
            WarriorTradeModel.symbol == symbol,
            WarriorTradeModel.entry_price >= broker_entry_price - price_tolerance,
            WarriorTradeModel.entry_price <= broker_entry_price + price_tolerance,
        ).order_by(WarriorTradeModel.entry_time.desc()).first()
        
        if trade:
            return trade.to_dict()
        
        return None


def update_warrior_status(trade_id: str, new_status: str):
    """
    Update a warrior trade's status using PSM values.
    
    Args:
        trade_id: The trade ID to update
        new_status: New status (use PositionStatus.X.value)
    """
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(id=trade_id).first()
        if trade:
            old_status = trade.status
            trade.status = new_status
            trade.updated_at = now_utc()
            db.commit()
            print(f"[Warrior DB] {trade.symbol}: {old_status} → {new_status}")
            return True
        return False


def set_entry_order_id(trade_id: str, order_id: str):
    """
    Set the entry order ID when entry order is submitted.
    
    Args:
        trade_id: The trade ID to update
        order_id: Alpaca broker order ID
    """
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(id=trade_id).first()
        if trade:
            trade.entry_order_id = order_id
            trade.updated_at = now_utc()
            db.commit()
            return True
        return False


def set_exit_order_id(trade_id: str, order_id: str):
    """
    Set the exit order ID when exit order is submitted.
    
    Args:
        trade_id: The trade ID to update
        order_id: Alpaca broker order ID
    """
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(id=trade_id).first()
        if trade:
            trade.exit_order_id = order_id
            trade.updated_at = now_utc()
            db.commit()
            return True
        return False


def get_warrior_trade_by_order_id(order_id: str):
    """
    Find a trade by its broker entry order ID (for sync recovery).
    
    Used during startup sync to recover existing position_id instead of
    creating a new one.
    
    Args:
        order_id: Alpaca broker order ID
    
    Returns:
        Trade dict if found, None otherwise
    """
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(
            entry_order_id=order_id
        ).first()
        return trade.to_dict() if trade else None


def update_high_since_entry(trade_id: str, new_high: float) -> bool:
    """
    Update the high_since_entry field for a trade.
    
    Called during monitoring when price makes a new high.
    
    Args:
        trade_id: The trade ID to update
        new_high: New high price since entry
    
    Returns:
        True if updated successfully
    """
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(id=trade_id).first()
        if trade:
            trade.high_since_entry = str(new_high)
            trade.updated_at = now_utc()
            db.commit()
            return True
        return False


# =============================================================================
# SCALING STATUS HELPERS (PSM INTEGRATION)
# =============================================================================

def set_scaling_status(trade_id: str) -> bool:
    """
    Mark position as SCALING before submitting add order.
    
    Uses PSM transition validation: OPEN → SCALING
    Returns False if transition is invalid (not in OPEN state).
    
    Args:
        trade_id: The trade ID to update
    
    Returns:
        True if status was set to SCALING, False if transition invalid
    """
    from nexus2.domain.positions.position_state_machine import (
        can_transition, PositionStatus
    )
    
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(id=trade_id).first()
        if not trade:
            print(f"[Warrior DB] set_scaling_status: Trade not found: {trade_id}")
            return False
        
        # Check if transition is valid via PSM
        try:
            current = PositionStatus(trade.status)
        except ValueError:
            # Unknown status - treat as legacy "open"
            current = PositionStatus.OPEN
        
        if not can_transition(current, PositionStatus.SCALING):
            print(f"[Warrior DB] {trade.symbol}: Cannot scale - status is {trade.status}")
            return False
        
        # Valid transition - set SCALING
        old_status = trade.status
        trade.status = PositionStatus.SCALING.value
        trade.updated_at = now_utc()
        db.commit()
        print(f"[Warrior DB] {trade.symbol}: {old_status} → scaling (add order pending)")
        return True


def complete_scaling(trade_id: str, new_quantity: int, new_avg_price: float = None) -> bool:
    """
    Complete scaling: update shares and transition SCALING → OPEN.
    
    Called after scale order fills successfully.
    
    Args:
        trade_id: The trade ID to update
        new_quantity: New total quantity after add
        new_avg_price: New average price (optional - if broker provides)
    
    Returns:
        True if scaling completed successfully
    """
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(id=trade_id).first()
        if not trade:
            print(f"[Warrior DB] complete_scaling: Trade not found: {trade_id}")
            return False
        
        old_qty = trade.quantity
        trade.quantity = new_quantity
        trade.remaining_quantity = new_quantity
        trade.status = PositionStatus.OPEN.value
        
        if new_avg_price:
            trade.entry_price = str(new_avg_price)
        
        trade.updated_at = now_utc()
        db.commit()
        print(f"[Warrior DB] {trade.symbol}: scaling → open (qty: {old_qty} → {new_quantity})")
        return True


def revert_scaling(trade_id: str) -> bool:
    """
    Revert SCALING → OPEN when scale order fails or is rejected.
    
    Args:
        trade_id: The trade ID to update
    
    Returns:
        True if reverted successfully
    """
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(id=trade_id).first()
        if not trade:
            return False
        
        if trade.status == PositionStatus.SCALING.value:
            trade.status = PositionStatus.OPEN.value
            trade.updated_at = now_utc()
            db.commit()
            print(f"[Warrior DB] {trade.symbol}: scaling → open (scale order failed)")
            return True
        return False


def check_scaling_positions() -> list:
    """
    Get all positions in SCALING status for startup sync.
    
    Used during startup to reconcile in-flight scale orders with broker.
    
    Returns:
        List of trade dicts in SCALING status
    """
    with get_warrior_session() as db:
        trades = db.query(WarriorTradeModel).filter_by(
            status=PositionStatus.SCALING.value
        ).all()
        return [t.to_dict() for t in trades]


def get_warrior_trades_by_status(status: str) -> list:
    """
    Get all trades with a specific status.
    
    Args:
        status: Status to filter by (use PositionStatus.X.value)
    """
    with get_warrior_session() as db:
        trades = db.query(WarriorTradeModel).filter_by(status=status).all()
        return [t.to_dict() for t in trades]


def close_orphaned_trades(active_symbols: set):
    """
    Close trades in DB that are marked 'open' but not in the active broker positions.
    
    This reconciles the DB with reality after restarts or manual position closures.
    
    Args:
        active_symbols: Set of symbols currently held on broker (e.g., from Alpaca)
    
    Returns:
        List of symbols that were closed as orphans
    """
    closed = []
    with get_warrior_session() as db:
        # Check both 'open' (legacy) and PositionStatus.OPEN.value
        open_trades = db.query(WarriorTradeModel).filter(
            WarriorTradeModel.status.in_([PositionStatus.OPEN.value, "open"])
        ).all()
        
        for trade in open_trades:
            if trade.symbol not in active_symbols:
                print(f"[Warrior DB] Closing orphan: {trade.symbol} (not on broker)")
                trade.status = PositionStatus.CLOSED.value
                trade.exit_reason = "orphan_cleanup"
                trade.exit_time = now_utc()
                closed.append(trade.symbol)
        
        db.commit()
    
    if closed:
        print(f"[Warrior DB] Closed {len(closed)} orphaned trades: {closed}")
    
    return closed


def get_all_warrior_trades(limit: int = 50, status_filter: str = None):
    """
    Get all Warrior trades with summary statistics.
    
    Args:
        limit: Maximum trades to return
        status_filter: Optional status filter ('open', 'closed', or None for all)
    
    Returns:
        Dict with trades list and summary stats
    """
    with get_warrior_session() as db:
        query = db.query(WarriorTradeModel).order_by(WarriorTradeModel.entry_time.desc())
        
        if status_filter:
            query = query.filter(WarriorTradeModel.status == status_filter)
        
        trades = query.limit(limit).all()
        
        # Calculate summary
        all_trades = db.query(WarriorTradeModel).filter(
            WarriorTradeModel.status == PositionStatus.CLOSED.value
        ).all()
        
        total_trades = len(all_trades)
        winning = sum(1 for t in all_trades if float(t.realized_pnl or 0) > 0)
        losing = sum(1 for t in all_trades if float(t.realized_pnl or 0) < 0)
        total_pnl = sum(float(t.realized_pnl or 0) for t in all_trades)
        
        return {
            "trades": [t.to_dict() for t in trades],
            "summary": {
                "total_trades": total_trades,
                "winning_trades": winning,
                "losing_trades": losing,
                "win_rate": winning / total_trades if total_trades > 0 else 0,
                "total_pnl": round(total_pnl, 2),
            }
        }


def get_trade_by_id(trade_id: str):
    """Get a single trade by ID."""
    with get_warrior_session() as db:
        trade = db.query(WarriorTradeModel).filter_by(id=trade_id).first()
        return trade.to_dict() if trade else None


def get_recent_closed_trades(limit: int = 30) -> list:
    """
    Get recent closed trades for R&D Lab analysis.
    
    Returns trades with complete exit data for performance analysis.
    
    Args:
        limit: Maximum trades to return (default 30)
    
    Returns:
        List of trade dicts with key fields for analysis
    """
    with get_warrior_session() as db:
        trades = db.query(WarriorTradeModel).filter(
            WarriorTradeModel.status == PositionStatus.CLOSED.value,
            WarriorTradeModel.exit_price.isnot(None),  # Must have exit price
            WarriorTradeModel.realized_pnl.isnot(None),  # Must have P&L
        ).order_by(WarriorTradeModel.entry_time.desc()).limit(limit).all()
        
        # Return simplified dict for Lab analysis
        return [
            {
                "symbol": t.symbol,
                "trigger_type": t.trigger_type,
                "exit_reason": t.exit_reason,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "stop_price": t.stop_price,
                "stop_method": t.stop_method,
                "realized_pnl": float(t.realized_pnl) if t.realized_pnl else 0,
                "quantity": t.quantity,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            }
            for t in trades
        ]

