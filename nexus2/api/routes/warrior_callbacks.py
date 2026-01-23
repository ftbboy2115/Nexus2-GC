"""
Warrior Callback Factories

Shared callback functions for both simulation and live broker modes.
Factory functions create configured callbacks for a given broker instance.
"""

import asyncio
from decimal import Decimal
from uuid import uuid4
from typing import Optional, Callable, Any
from functools import partial


# =============================================================================
# SUBMIT ORDER CALLBACK
# =============================================================================

def create_submit_order(broker, get_broker_fn: Callable = None):
    """Create a submit_order callback for the given broker.
    
    Args:
        broker: Broker instance (AlpacaBroker or MockBroker)
        get_broker_fn: Optional function to get broker at runtime (for lazy loading)
    
    Returns:
        Async submit_order callback function
    """
    async def submit_order(
        symbol: str,
        shares: int,
        side: str = "buy",
        order_type: str = "limit",
        stop_loss: float = None,
        limit_price: float = None,
        **kwargs,
    ):
        """Submit order to broker."""
        active_broker = get_broker_fn() if get_broker_fn else broker
        if active_broker is None:
            print(f"[Warrior] No broker configured")
            return None
        
        try:
            result = active_broker.submit_order(
                client_order_id=uuid4(),
                symbol=symbol,
                side=side,
                quantity=shares,
                order_type=order_type,
                limit_price=Decimal(str(limit_price)) if limit_price else None,
                extended_hours=True,
            )
            print(f"[Warrior] LIMIT order submitted: {symbol} x{shares} @ ${limit_price} ({side})")
            return result
        except Exception as e:
            error_str = str(e).lower()
            if "not tradable" in error_str or "is not fractionable" in error_str or "asset not found" in error_str:
                print(f"[Warrior] {symbol} is not tradable - adding to blacklist")
                return {"blacklist": True, "symbol": symbol, "error": str(e)}
            print(f"[Warrior] Order failed: {e}")
            return None
    
    return submit_order


# =============================================================================
# GET POSITIONS CALLBACK
# =============================================================================

def create_get_positions(broker, get_broker_fn: Callable = None):
    """Create a get_positions callback."""
    async def get_positions():
        """Get positions from broker."""
        active_broker = get_broker_fn() if get_broker_fn else broker
        if active_broker is None:
            return []
        
        try:
            positions = active_broker.get_positions()
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
            print(f"[Warrior] Failed to get positions: {e}")
            return []
    
    return get_positions


# =============================================================================
# QUOTE CALLBACKS
# =============================================================================

def create_get_quote():
    """Create a get_quote callback using UnifiedMarketData."""
    from nexus2.adapters.market_data.unified import UnifiedMarketData
    umd = UnifiedMarketData()
    
    async def get_quote(symbol: str):
        """Get quote from real market data."""
        quote = umd.get_quote(symbol)
        return float(quote.price) if quote else None
    
    return get_quote


def create_get_quotes_batch():
    """Create a batch quotes callback using cross-validated UnifiedMarketData."""
    from nexus2.adapters.market_data.unified import UnifiedMarketData
    umd = UnifiedMarketData()
    
    async def get_quotes_batch(symbols: list):
        """Get quotes for multiple symbols with cross-validation."""
        try:
            # Use individual cross-validated quotes for each symbol
            # This ensures each price is validated against FMP
            prices = {}
            for symbol in symbols:
                quote = umd.get_quote(symbol)
                if quote and quote.price > 0:
                    prices[symbol] = float(quote.price)
            return prices
        except Exception as e:
            print(f"[Warrior] Batch quote failed: {e}")
            return {}
    
    return get_quotes_batch


def create_get_quote_with_spread():
    """Create a quote-with-spread callback with Schwab fallback."""
    # Schwab quote cache (10-second TTL to stay under 120 calls/min limit)
    _schwab_quote_cache: dict = {}
    _schwab_cache_ttl = 10
    # Log throttle: only log Schwab fallback once per minute per symbol
    _schwab_log_throttle: dict = {}
    _schwab_log_interval = 60
    
    async def get_quote_with_spread(symbol: str):
        """Get quote with bid/ask spread for spread exit trigger.
        
        Priority: Alpaca (primary) -> Schwab (fallback when bid/ask = 0)
        """
        import time
        nonlocal _schwab_quote_cache
        
        bid = 0
        ask = 0
        price = 0
        
        # Try Alpaca first
        try:
            from nexus2.adapters.market_data.alpaca_adapter import AlpacaAdapter
            alpaca = AlpacaAdapter()
            quote = alpaca.get_quote(symbol)
            if quote:
                price = float(quote.price)
                bid = float(quote.bid) if hasattr(quote, 'bid') and quote.bid else 0
                ask = float(quote.ask) if hasattr(quote, 'ask') and quote.ask else 0
        except Exception as e:
            print(f"[Warrior] Alpaca quote failed for {symbol}: {e}")
        
        # Schwab fallback if Alpaca doesn't have bid/ask
        if bid <= 0 or ask <= 0:
            cache_key = symbol
            now = time.time()
            if cache_key in _schwab_quote_cache:
                cached_time, cached_data = _schwab_quote_cache[cache_key]
                if now - cached_time < _schwab_cache_ttl:
                    bid = cached_data.get("bid", bid)
                    ask = cached_data.get("ask", ask)
                    price = cached_data.get("price", price)
                else:
                    del _schwab_quote_cache[cache_key]
            
            if cache_key not in _schwab_quote_cache and (bid <= 0 or ask <= 0):
                try:
                    from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
                    schwab = get_schwab_adapter()
                    if schwab.is_authenticated():
                        schwab_quote = schwab.get_quote(symbol)
                        if schwab_quote and schwab_quote.get("bid", 0) > 0:
                            bid = schwab_quote["bid"]
                            ask = schwab_quote["ask"]
                            price = schwab_quote.get("price", price)
                            _schwab_quote_cache[cache_key] = (now, {"bid": bid, "ask": ask, "price": price})
                            # Throttled log: only once per minute per symbol
                            last_log = _schwab_log_throttle.get(symbol, 0)
                            if now - last_log >= _schwab_log_interval:
                                print(f"[Warrior] Schwab fallback for {symbol}: bid=${bid:.2f}, ask=${ask:.2f}")
                                _schwab_log_throttle[symbol] = now
                except Exception as e:
                    print(f"[Warrior] Schwab fallback failed for {symbol}: {e}")
        
        if price > 0 or bid > 0:
            return {"price": price, "bid": bid, "ask": ask}
        return None
    
    return get_quote_with_spread


# =============================================================================
# INTRADAY BARS CALLBACK
# =============================================================================

def create_get_intraday_bars():
    """Create an intraday bars callback for technical indicators."""
    from dataclasses import dataclass
    
    @dataclass
    class Bar:
        open: float
        high: float
        low: float
        close: float
        volume: int
    
    async def get_intraday_bars(symbol: str, timeframe: str = "5min", limit: int = 50):
        """Get intraday bars for technical indicator calculation."""
        try:
            from nexus2.adapters.market_data.alpaca_adapter import AlpacaAdapter
            alpaca = AlpacaAdapter()
            
            if hasattr(alpaca, 'get_bars'):
                bars = alpaca.get_bars(symbol, timeframe=timeframe, limit=limit)
                if bars:
                    return [Bar(
                        open=float(b.open),
                        high=float(b.high),
                        low=float(b.low),
                        close=float(b.close),
                        volume=int(b.volume)
                    ) for b in bars]
            
            # Fallback: FMP (run in thread pool to avoid blocking event loop)
            from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
            fmp = get_fmp_adapter()
            if fmp:
                fmp_bars = await asyncio.to_thread(fmp.get_intraday_bars, symbol, "5min")
                if fmp_bars and len(fmp_bars) >= 5:
                    bars_to_use = fmp_bars[-limit:] if len(fmp_bars) > limit else fmp_bars
                    return [Bar(
                        open=float(b.open),
                        high=float(b.high),
                        low=float(b.low),
                        close=float(b.close),
                        volume=int(b.volume)
                    ) for b in bars_to_use]
            
            return None
        except Exception as e:
            print(f"[Warrior] Intraday bars failed for {symbol}: {e}")
            return None
    
    return get_intraday_bars


# =============================================================================
# EXECUTE EXIT CALLBACK
# =============================================================================

def create_execute_exit(get_broker_fn: Callable, get_quote_fn: Callable, get_quote_with_spread_fn: Callable):
    """Create an execute_exit callback with fill price polling.
    
    Args:
        get_broker_fn: Function to get current broker instance
        get_quote_fn: Quote callback function
        get_quote_with_spread_fn: Quote with spread callback function
    """
    async def execute_exit(signal):
        """Execute exit order for a position."""
        alpaca = get_broker_fn()
        if alpaca is None:
            print("[Warrior] No broker - cannot execute exit")
            return None
        
        position_id = signal.position_id
        shares = signal.shares_to_exit
        reason = signal.reason.value if hasattr(signal.reason, 'value') else str(signal.reason)
        symbol = signal.symbol
        
        # DEFENSIVE GUARD: Check actual broker position to prevent short attempts
        # This handles race conditions where scale orders haven't filled yet
        try:
            broker_positions = alpaca.get_positions()
            if symbol in broker_positions:
                broker_qty = broker_positions[symbol].quantity
                if broker_qty < shares:
                    print(f"[Warrior] {symbol}: Adjusting exit from {shares} to {broker_qty} shares (broker qty)")
                    shares = broker_qty
            else:
                print(f"[Warrior] {symbol}: No broker position found - skipping exit")
                return None
        except Exception as e:
            print(f"[Warrior] {symbol}: Broker position check failed: {e}, using signal qty")
        
        if shares <= 0:
            print(f"[Warrior] {symbol}: No shares to exit after broker check")
            return None
        
        try:
            # Cancel pending BUY orders first (prevents wash trade when scale order pending)
            cancelled_buys = alpaca.cancel_open_orders(symbol, side="buy")
            if cancelled_buys > 0:
                print(f"[Warrior] Cancelled {cancelled_buys} pending buy order(s) for {symbol} (wash trade prevention)")
            
            # Cancel pending sell orders
            cancelled = alpaca.cancel_open_orders(symbol, side="sell")
            if cancelled > 0:
                print(f"[Warrior] Cancelled {cancelled} pending sell order(s) for {symbol}")
            
            # Determine pricing
            use_bid_pricing = reason in ("spread_exit", "after_hours_exit")
            
            if use_bid_pricing:
                spread_data = await get_quote_with_spread_fn(symbol)
                if spread_data and spread_data.get("bid", 0) > 0:
                    current_price = spread_data["bid"]
                    print(f"[Warrior] {reason} using bid: ${current_price:.2f}")
                else:
                    current_price = float(signal.exit_price)
            else:
                current_price = await get_quote_fn(symbol)
                signal_price = float(signal.exit_price)
                if current_price is None:
                    current_price = signal_price
                elif current_price > signal_price * 1.05:
                    current_price = signal_price
            
            # Calculate offset
            if hasattr(signal, 'exit_offset_percent') and signal.exit_offset_percent > 0.01:
                offset = 1.0 - signal.exit_offset_percent
            elif reason in ("mental_stop", "technical_stop", "breakout_failure", "time_stop", "spread_exit", "after_hours_exit"):
                offset = 0.99
            else:
                offset = 0.995
            
            limit_price = round(current_price * offset, 2)
            
            # Submit order
            order = alpaca.submit_order(
                client_order_id=uuid4(),
                symbol=symbol,
                quantity=shares,
                side="sell",
                order_type="limit",
                limit_price=Decimal(str(limit_price)),
                extended_hours=True,
            )
            print(f"[Warrior] Exit LIMIT order submitted: {symbol} x{shares} @ ${limit_price:.2f} ({reason})")
            
            # Poll for actual fill price (up to 2 seconds)
            actual_fill_price = None
            order_id = str(order.id) if hasattr(order, 'id') else None
            if order_id:
                for _ in range(4):
                    await asyncio.sleep(0.5)
                    try:
                        filled_order = alpaca.get_order(order_id)
                        if hasattr(filled_order, 'filled_avg_price') and filled_order.filled_avg_price:
                            actual_fill_price = float(filled_order.filled_avg_price)
                            print(f"[Warrior] {symbol} filled @ ${actual_fill_price:.2f}")
                            break
                    except Exception as poll_err:
                        print(f"[Warrior] Poll error: {poll_err}")
                        break
            
            exit_price = actual_fill_price if actual_fill_price else float(limit_price)
            
            # Log to DB
            try:
                from nexus2.db.warrior_db import log_warrior_exit
                log_warrior_exit(position_id, exit_price, reason, shares)
            except Exception as e:
                print(f"[Warrior] Exit DB log failed: {e}")
            
            return {"order": order, "actual_exit_price": exit_price}
        except Exception as e:
            print(f"[Warrior] Exit order failed: {e}")
            return None
    
    return execute_exit


# =============================================================================
# PENDING FILL CHECK
# =============================================================================

async def check_pending_fill(symbol: str) -> bool:
    """Check if there's a PENDING_FILL position for this symbol.
    
    Prevents duplicate buy orders when engine restarts before order fills.
    """
    try:
        from nexus2.db.database import SessionLocal
        from nexus2.db.repository import PositionRepository
        
        db = SessionLocal()
        try:
            repo = PositionRepository(db)
            pending = repo.get_all(status="pending_fill")
            for p in pending:
                if p.symbol == symbol and p.account == "B":
                    print(f"[Warrior] {symbol}: Found existing PENDING_FILL position")
                    return True
            return False
        finally:
            db.close()
    except Exception as e:
        print(f"[Warrior] Pending fill check failed: {e}")
        return False
