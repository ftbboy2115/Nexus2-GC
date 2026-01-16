"""
Warrior Broker Routes

Alpaca Account B integration for live paper trading.
Includes callback wiring, position management, and trade history.
"""

import time
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from .warrior_callbacks import (
    create_get_quote,
    create_get_quotes_batch,
    create_get_quote_with_spread,
    create_get_intraday_bars,
    create_execute_exit,
    check_pending_fill,
)


# =============================================================================
# ROUTER
# =============================================================================

broker_router = APIRouter(tags=["warrior-broker"])


# =============================================================================
# BROKER STATE
# =============================================================================

_warrior_alpaca_broker = None


def get_warrior_alpaca_broker():
    """Get Warrior's Alpaca broker (Account B) if configured."""
    return _warrior_alpaca_broker


def set_warrior_alpaca_broker(broker):
    """Set Warrior's Alpaca broker."""
    global _warrior_alpaca_broker
    _warrior_alpaca_broker = broker


def create_warrior_alpaca_broker():
    """Create AlpacaBroker using Account B credentials."""
    from nexus2 import config
    
    if not config.ALPACA_KEY_B or not config.ALPACA_SECRET_B:
        return None
    
    from nexus2.adapters.broker import AlpacaBroker, AlpacaBrokerConfig
    
    return AlpacaBroker(AlpacaBrokerConfig(
        api_key=config.ALPACA_KEY_B,
        api_secret=config.ALPACA_SECRET_B,
        paper=True,
    ))


# =============================================================================
# BROKER STATUS
# =============================================================================

@broker_router.get("/broker/status")
async def get_warrior_broker_status():
    """Get Warrior Alpaca broker status."""
    from nexus2 import config
    from .warrior_routes import get_engine
    
    has_credentials = bool(config.ALPACA_KEY_B and config.ALPACA_SECRET_B)
    broker = get_warrior_alpaca_broker()
    
    if not has_credentials:
        return {
            "broker_enabled": False,
            "message": "Account B credentials not set.",
        }
    
    if broker is None:
        return {
            "broker_enabled": False,
            "credentials_set": True,
            "message": "Broker not initialized. POST /warrior/broker/enable",
        }
    
    try:
        account_value = broker.get_account_value()
        positions = broker.get_positions()
        
        total_unrealized_pnl = 0.0
        total_invested = 0.0
        positions_list = list(positions.values()) if isinstance(positions, dict) else positions
        for p in positions_list:
            total_unrealized_pnl += float(p.unrealized_pnl) if p.unrealized_pnl else 0
            total_invested += float(p.avg_price) * p.quantity if p.avg_price else 0
        
        from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
        monitor = get_warrior_monitor()
        monitor_realized_pnl = float(monitor.realized_pnl_today)
        
        account_pnl = broker.get_account_daily_pnl()
        total_daily_pnl = account_pnl["daily_pnl"]
        daily_pnl_percent = account_pnl["daily_pnl_percent"]
        
        capital_stats = broker.get_daily_capital_stats()
        peak_exposure = capital_stats["peak_exposure"]
        total_capital_deployed = capital_stats["total_capital_deployed"]
        
        return {
            "broker_enabled": True,
            "paper_mode": True,
            "account_value": account_value,
            "positions_count": len(positions_list),
            "realized_pnl_today": monitor_realized_pnl,
            "unrealized_pnl": total_unrealized_pnl,
            "total_daily_pnl": total_daily_pnl,
            "invested_capital": total_invested,
            "peak_exposure": peak_exposure,
            "total_capital_deployed": total_capital_deployed,
            "daily_pnl_percent": round(daily_pnl_percent, 2),
            "positions": [
                {
                    "symbol": p.symbol,
                    "qty": p.quantity,
                    "avg_price": float(p.avg_price),
                    "current_price": float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pnl),
                }
                for p in positions_list
            ],
        }
    except Exception as e:
        return {"broker_enabled": False, "error": str(e)}


# =============================================================================
# CLOSE POSITION
# =============================================================================

@broker_router.post("/broker/close/{symbol}")
async def close_warrior_position(symbol: str, limit_price: float = None):
    """Close a position manually via limit order."""
    broker = get_warrior_alpaca_broker()
    
    if broker is None:
        raise HTTPException(status_code=400, detail="Broker not enabled")
    
    try:
        positions = broker.get_positions()
        positions_dict = positions if isinstance(positions, dict) else {p.symbol: p for p in positions}
        
        if symbol not in positions_dict:
            raise HTTPException(status_code=404, detail=f"Position {symbol} not found")
        
        pos = positions_dict[symbol]
        qty = pos.quantity
        
        if limit_price is None:
            from nexus2.adapters.market_data import UnifiedMarketData
            market_data = UnifiedMarketData()
            quote = market_data.get_quote(symbol)
            if quote:
                limit_price = float(quote.price) if hasattr(quote, 'price') else float(pos.current_price) * 0.99
            else:
                limit_price = float(pos.current_price) * 0.99
        
        result = broker.submit_order(
            client_order_id=uuid4(),
            symbol=symbol,
            side="sell",
            quantity=qty,
            order_type="limit",
            limit_price=Decimal(str(round(limit_price, 2))),
            extended_hours=True,
        )
        
        return {
            "success": True,
            "symbol": symbol,
            "shares": qty,
            "limit_price": limit_price,
            "result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# WIRE CALLBACKS
# =============================================================================

async def wire_warrior_callbacks(broker) -> dict:
    """Wire WarriorEngine and Monitor callbacks to Alpaca broker."""
    from .warrior_routes import get_engine
    
    try:
        account_value = broker.get_account_value()
    except Exception as e:
        raise Exception(f"Failed to connect to Alpaca: {e}")
    
    engine = get_engine()
    engine.config.sim_only = False
    
    # Create submit_order callback
    async def broker_submit_order(
        symbol: str,
        shares: int,
        side: str = "buy",
        order_type: str = "limit",
        stop_loss: float = None,
        limit_price: float = None,
        **kwargs,
    ):
        alpaca = get_warrior_alpaca_broker()
        if alpaca is None:
            return None
        
        try:
            result = alpaca.submit_order(
                client_order_id=uuid4(),
                symbol=symbol,
                side=side,
                quantity=shares,
                order_type=order_type,
                limit_price=Decimal(str(limit_price)) if limit_price else None,
                extended_hours=True,
            )
            print(f"[Warrior] LIMIT order: {symbol} x{shares} @ ${limit_price} ({side})")
            return result
        except Exception as e:
            error_str = str(e).lower()
            if "not tradable" in error_str or "is not fractionable" in error_str:
                return {"blacklist": True, "symbol": symbol, "error": str(e)}
            print(f"[Warrior] Order failed: {e}")
            return None
    
    async def broker_get_positions():
        alpaca = get_warrior_alpaca_broker()
        if alpaca is None:
            return []
        
        try:
            positions = alpaca.get_positions()
            return [
                {
                    "symbol": p.symbol,
                    "qty": p.quantity,
                    "avg_price": float(p.avg_price),
                    "current_price": float(p.current_price) if p.current_price else 0,
                    "unrealized_pnl": float(p.unrealized_pnl),
                }
                for p in positions.values()
            ]
        except Exception as e:
            print(f"[Warrior] Get positions failed: {e}")
            return []
    
    # Use callback factories
    broker_get_quote = create_get_quote()
    broker_get_quotes_batch = create_get_quotes_batch()
    broker_get_quote_with_spread = create_get_quote_with_spread()
    broker_get_intraday_bars = create_get_intraday_bars()
    broker_execute_exit = create_execute_exit(
        get_broker_fn=get_warrior_alpaca_broker,
        get_quote_fn=broker_get_quote,
        get_quote_with_spread_fn=broker_get_quote_with_spread,
    )
    
    # Wire engine callbacks
    engine.set_callbacks(
        submit_order=broker_submit_order,
        get_quote=broker_get_quote,
        get_positions=broker_get_positions,
        check_pending_fill=check_pending_fill,
    )
    
    # Wire scanner to broker for HTB/ETB lookups (Ross Cameron methodology)
    engine.scanner.alpaca_broker = broker
    
    # Wire monitor callbacks
    from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
    monitor = get_warrior_monitor()
    
    async def broker_get_positions_async():
        try:
            positions = broker.get_positions()
            return [
                {"symbol": symbol, "qty": pos.quantity, "avg_price": pos.avg_price}
                for symbol, pos in positions.items()
            ]
        except Exception as e:
            print(f"[Warrior] Error getting broker positions: {e}")
            return None
    
    async def broker_get_order_status(order_id: str):
        """Get order status from Alpaca by broker_order_id."""
        try:
            return broker.get_order_status(order_id)
        except Exception as e:
            print(f"[Warrior] Error getting order status: {e}")
            return None
    
    monitor.set_callbacks(
        get_broker_positions=broker_get_positions_async,
        get_prices_batch=broker_get_quotes_batch,
        get_price=broker_get_quote,
        get_quote_with_spread=broker_get_quote_with_spread,
        get_intraday_candles=broker_get_intraday_bars,
        execute_exit=broker_execute_exit,
        submit_scale_order=broker_submit_order,
        get_order_status=broker_get_order_status,
    )
    monitor._execute_exit = broker_execute_exit
    
    # Sync broker positions
    print("[Warrior] Syncing positions from Alpaca...")
    await monitor._sync_with_broker()
    
    # Sync SCALING positions - reconcile in-flight scale orders
    from nexus2.db.warrior_db import check_scaling_positions, complete_scaling, revert_scaling, close_orphaned_trades
    scaling_positions = check_scaling_positions()
    if scaling_positions:
        print(f"[Warrior] Syncing {len(scaling_positions)} SCALING positions...")
        broker_positions = broker.get_positions()
        for pos in scaling_positions:
            symbol = pos["symbol"]
            db_qty = pos["quantity"]
            if symbol in broker_positions:
                broker_qty = broker_positions[symbol].quantity
                if broker_qty > db_qty:
                    # Scale filled - update DB with new quantity
                    print(f"[Warrior] {symbol}: Scale filled (DB:{db_qty} → Broker:{broker_qty})")
                    complete_scaling(pos["id"], broker_qty)
                else:
                    # Scale didn't fill - revert to OPEN
                    print(f"[Warrior] {symbol}: Scale not filled, reverting to OPEN")
                    revert_scaling(pos["id"])
            else:
                # Position no longer at broker - revert to OPEN
                print(f"[Warrior] {symbol}: Position not at broker, reverting to OPEN")
                revert_scaling(pos["id"])
    
    # Close orphaned trades - positions marked 'open' in DB but not at broker
    broker_positions = broker.get_positions()
    active_symbols = set(broker_positions.keys())
    orphaned = close_orphaned_trades(active_symbols)
    if orphaned:
        print(f"[Warrior] Closed {len(orphaned)} orphaned trades: {orphaned}")
    
    return {
        "status": "enabled",
        "broker": "alpaca_paper_b",
        "account_value": account_value,
    }


# =============================================================================
# ENABLE/TEST BROKER
# =============================================================================

@broker_router.post("/broker/enable")
async def enable_warrior_broker():
    """Enable Alpaca Account B for Warrior engine."""
    global _warrior_alpaca_broker
    
    broker = create_warrior_alpaca_broker()
    
    if broker is None:
        raise HTTPException(
            status_code=400,
            detail="Account B credentials not configured.",
        )
    
    _warrior_alpaca_broker = broker
    
    try:
        result = await wire_warrior_callbacks(broker)
        result["message"] = "WarriorEngine connected to Alpaca Account B (paper)"
        return result
    except Exception as e:
        _warrior_alpaca_broker = None
        raise HTTPException(status_code=500, detail=str(e))


@broker_router.post("/broker/test")
async def test_warrior_broker():
    """Test Alpaca connection by placing and canceling a limit order."""
    broker = get_warrior_alpaca_broker()
    
    if broker is None:
        raise HTTPException(status_code=400, detail="Broker not enabled.")
    
    try:
        test_client_id = uuid4()
        order = broker.submit_order(
            client_order_id=test_client_id,
            symbol="AAPL",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=Decimal("1.00"),
        )
        
        order_id = order.broker_order_id
        print(f"[Warrior] Test order placed: {order_id}")
        
        time.sleep(0.5)
        
        broker.cancel_order(order_id)
        print(f"[Warrior] Test order canceled: {order_id}")
        
        return {
            "status": "success",
            "message": "Alpaca connection verified",
            "order_id": str(order_id),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Alpaca test failed: {e}")


# =============================================================================
# BACKFILL
# =============================================================================

@broker_router.post("/db/backfill")
async def backfill_warrior_trades():
    """Backfill synced positions into the Warrior trade log."""
    from nexus2.db.warrior_db import log_warrior_entry, get_warrior_trade_by_symbol
    from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
    
    monitor = get_warrior_monitor()
    positions = monitor.get_positions()
    
    backfilled = []
    skipped = []
    
    for pos in positions:
        symbol = pos.symbol
        
        existing = get_warrior_trade_by_symbol(symbol)
        if existing:
            skipped.append(symbol)
            continue
        
        try:
            trade_id = str(uuid4())
            log_warrior_entry(
                trade_id=trade_id,
                symbol=symbol,
                entry_price=float(pos.entry_price),
                quantity=pos.shares,
                stop_price=float(pos.mental_stop),
                target_price=float(pos.profit_target),
                trigger_type="backfill",
                support_level=float(pos.technical_stop) if pos.technical_stop else None,
            )
            backfilled.append({
                "symbol": symbol,
                "entry_price": float(pos.entry_price),
                "stop_price": float(pos.mental_stop),
                "shares": pos.shares,
            })
        except Exception as e:
            print(f"[Warrior] Backfill failed for {symbol}: {e}")
    
    return {
        "status": "completed",
        "backfilled": backfilled,
        "skipped": skipped,
        "message": f"Backfilled {len(backfilled)} trades, skipped {len(skipped)} existing",
    }


# =============================================================================
# CANCEL ORDERS
# =============================================================================

@broker_router.delete("/orders/{symbol}")
async def cancel_orders_for_symbol(symbol: str):
    """Cancel all open orders for a symbol."""
    from nexus2.domain.automation.warrior_engine import get_warrior_engine
    
    engine = get_warrior_engine()
    if not engine:
        raise HTTPException(status_code=500, detail="Warrior engine not initialized")
    
    symbol = symbol.upper()
    
    if not engine.broker:
        raise HTTPException(status_code=400, detail="No broker configured")
    
    try:
        cancelled = []
        
        orders = engine.broker.get_open_orders()
        
        for order in orders:
            order_symbol = getattr(order, 'symbol', None) or order.get('symbol', '')
            if order_symbol.upper() == symbol:
                order_id = getattr(order, 'id', None) or order.get('id', '')
                try:
                    engine.broker.cancel_order(order_id)
                    cancelled.append(str(order_id))
                    print(f"[Warrior] Cancelled order {order_id} for {symbol}")
                except Exception as e:
                    print(f"[Warrior] Failed to cancel order {order_id}: {e}")
        
        if cancelled:
            try:
                from nexus2.db.warrior_db import get_warrior_trade_by_symbol, update_warrior_status
                from nexus2.domain.positions.position_state_machine import PositionStatus
                trade = get_warrior_trade_by_symbol(symbol)
                if trade and trade["status"] == PositionStatus.PENDING_EXIT.value:
                    update_warrior_status(trade["id"], PositionStatus.OPEN.value)
                    print(f"[Warrior] {symbol}: PENDING_EXIT → OPEN")
            except Exception as e:
                print(f"[Warrior] Failed to update status: {e}")
        
        return {
            "status": "success" if cancelled else "no_orders",
            "symbol": symbol,
            "cancelled_count": len(cancelled),
            "cancelled_order_ids": cancelled,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel orders: {e}")


# =============================================================================
# TRADE HISTORY
# =============================================================================

@broker_router.get("/trades")
async def get_trade_history(limit: int = 50, status: str = None):
    """Get Warrior trade history with summary statistics."""
    from nexus2.db.warrior_db import get_all_warrior_trades
    
    result = get_all_warrior_trades(limit=limit, status_filter=status)
    return result


@broker_router.get("/trades/{trade_id}")
async def get_trade_detail(trade_id: str):
    """Get a single trade by ID."""
    from nexus2.db.warrior_db import get_trade_by_id
    
    trade = get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    
    return {"trade": trade}
