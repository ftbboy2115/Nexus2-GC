"""
Alpaca Broker

Alpaca paper and live trading integration.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional
from uuid import UUID

import httpx

from nexus2.adapters.broker.protocol import (
    BrokerOrder,
    BrokerOrderStatus,
    BrokerPosition,
)
from nexus2 import config as app_config


class AlpacaBrokerError(Exception):
    """Alpaca broker error."""
    pass


class OrderNotFoundError(AlpacaBrokerError):
    """Order not found."""
    pass


@dataclass
class AlpacaBrokerConfig:
    """Configuration for Alpaca broker."""
    api_key: str
    api_secret: str
    paper: bool = True  # Default to paper trading
    timeout: float = 10.0


class AlpacaBroker:
    """
    Alpaca broker for paper and live trading.
    
    Default is paper trading (paper-api.alpaca.markets).
    Live trading requires explicit paper=False.
    """
    
    PAPER_URL = "https://paper-api.alpaca.markets"
    LIVE_URL = "https://api.alpaca.markets"
    
    # Map Alpaca status to our status
    STATUS_MAP = {
        "new": BrokerOrderStatus.PENDING,
        "accepted": BrokerOrderStatus.ACCEPTED,
        "pending_new": BrokerOrderStatus.PENDING,
        "accepted_for_bidding": BrokerOrderStatus.ACCEPTED,
        "filled": BrokerOrderStatus.FILLED,
        "partially_filled": BrokerOrderStatus.PARTIALLY_FILLED,
        "canceled": BrokerOrderStatus.CANCELLED,
        "cancelled": BrokerOrderStatus.CANCELLED,
        "expired": BrokerOrderStatus.EXPIRED,
        "rejected": BrokerOrderStatus.REJECTED,
        "pending_cancel": BrokerOrderStatus.PENDING,
        "pending_replace": BrokerOrderStatus.PENDING,
    }
    
    def __init__(self, config: Optional[AlpacaBrokerConfig] = None):
        if config:
            self.config = config
        else:
            # Load from app config
            self.config = AlpacaBrokerConfig(
                api_key=app_config.ALPACA_KEY or "",
                api_secret=app_config.ALPACA_SECRET or "",
                paper=True,
            )
        
        self._base_url = self.PAPER_URL if self.config.paper else self.LIVE_URL
        
        self._client = httpx.Client(
            timeout=self.config.timeout,
            headers={
                "APCA-API-KEY-ID": self.config.api_key,
                "APCA-API-SECRET-KEY": self.config.api_secret,
            }
        )
        
        # Track client_order_id -> broker_order_id mapping
        self._order_map: Dict[UUID, str] = {}
    
    def __del__(self):
        if hasattr(self, '_client'):
            self._client.close()
    
    def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict] = None,
    ) -> Optional[dict]:
        """Make API request."""
        url = f"{self._base_url}/v2/{endpoint}"
        
        try:
            if method == "GET":
                response = self._client.get(url)
            elif method == "POST":
                response = self._client.post(url, json=json)
            elif method == "DELETE":
                response = self._client.delete(url)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            response.raise_for_status()
            return response.json() if response.content else None
            
        except httpx.HTTPStatusError as e:
            # Include response body for detailed error info
            try:
                error_body = e.response.json()
                error_detail = error_body.get('message', str(error_body))
            except:
                error_detail = e.response.text
            raise AlpacaBrokerError(f"Alpaca API error {e.response.status_code}: {error_detail}")
        except Exception as e:
            raise AlpacaBrokerError(f"Alpaca request error: {e}")
    
    def _parse_order(self, data: dict, client_order_id: UUID) -> BrokerOrder:
        """Parse Alpaca order response to BrokerOrder."""
        status = self.STATUS_MAP.get(
            data.get("status", ""),
            BrokerOrderStatus.PENDING
        )
        
        filled_qty = int(data.get("filled_qty", 0) or 0)
        avg_price = data.get("filled_avg_price")
        
        return BrokerOrder(
            client_order_id=client_order_id,
            broker_order_id=data["id"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=int(data["qty"]),
            order_type=data["type"],
            status=status,
            limit_price=Decimal(str(data["limit_price"])) if data.get("limit_price") else None,
            stop_price=Decimal(str(data["stop_price"])) if data.get("stop_price") else None,
            filled_quantity=filled_qty,
            avg_fill_price=Decimal(str(avg_price)) if avg_price else None,
            submitted_at=datetime.fromisoformat(data["submitted_at"].replace("Z", "+00:00")) if data.get("submitted_at") else None,
            filled_at=datetime.fromisoformat(data["filled_at"].replace("Z", "+00:00")) if data.get("filled_at") else None,
        )
    
    def submit_order(
        self,
        client_order_id: UUID,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        extended_hours: bool = False,
    ) -> BrokerOrder:
        """Submit order to Alpaca."""
        
        # CRITICAL SAFETY CHECK: Prevent selling without existing long position
        # KK-style trading is LONG ONLY - never short
        if side.lower() == "sell":
            positions = self.get_positions()
            position = positions.get(symbol)
            if not position:
                error_msg = f"BLOCKED: Attempted to sell {symbol} but no long position exists. This would create a short position."
                print(f"🛑 [SAFETY] {error_msg}")
                raise AlpacaBrokerError(error_msg)
            if position.quantity < quantity:
                error_msg = f"BLOCKED: Attempted to sell {quantity} shares of {symbol} but only hold {position.quantity}. This would create a short position."
                print(f"🛑 [SAFETY] {error_msg}")
                raise AlpacaBrokerError(error_msg)
        
        payload = {
            "symbol": symbol,
            "qty": str(quantity),
            "side": side,
            "type": order_type,
            "time_in_force": "day",
            "client_order_id": str(client_order_id),
        }
        
        # Extended hours requires limit orders only
        if extended_hours:
            payload["extended_hours"] = True
        
        if limit_price:
            payload["limit_price"] = str(limit_price)
        if stop_price:
            payload["stop_price"] = str(stop_price)
        
        data = self._request("POST", "orders", json=payload)
        if not data:
            raise AlpacaBrokerError("Empty response from Alpaca")
        
        order = self._parse_order(data, client_order_id)
        self._order_map[client_order_id] = order.broker_order_id
        
        return order
    
    def submit_bracket_order(
        self,
        client_order_id: UUID,
        symbol: str,
        quantity: int,
        stop_loss_price: Decimal,
        limit_price: Optional[Decimal] = None,
        take_profit_price: Optional[Decimal] = None,
    ) -> BrokerOrder:
        """
        Submit a bracket order: market/limit entry with attached stop-loss.
        
        The stop-loss is held by Alpaca and will trigger even if Nexus is offline.
        This is the recommended way to enter positions with KK-style stops.
        
        Args:
            client_order_id: Unique client order ID
            symbol: Stock symbol
            quantity: Number of shares to buy
            stop_loss_price: Stop-loss price (required for safety)
            limit_price: Optional limit price (if None, uses market order)
            take_profit_price: Optional take-profit price
            
        Returns:
            BrokerOrder for the entry leg
        """
        # Build order class - OTO (one-triggers-other) for bracket
        order_class = "bracket" if take_profit_price else "oto"
        order_type = "limit" if limit_price else "market"
        
        payload = {
            "symbol": symbol,
            "qty": str(quantity),
            "side": "buy",
            "type": order_type,
            "time_in_force": "day",
            "client_order_id": str(client_order_id),
            "order_class": order_class,
            "stop_loss": {
                "stop_price": str(round(float(stop_loss_price), 2)),  # Round to 2 decimals for Alpaca
            },
        }
        
        if limit_price:
            payload["limit_price"] = str(limit_price)
        
        if take_profit_price:
            payload["take_profit"] = {
                "limit_price": str(take_profit_price),
            }
        
        data = self._request("POST", "orders", json=payload)
        if not data:
            raise AlpacaBrokerError("Empty response from Alpaca")
        
        order = self._parse_order(data, client_order_id)
        self._order_map[client_order_id] = order.broker_order_id
        
        return order
    
    def cancel_order(self, broker_order_id: str) -> BrokerOrder:
        """Cancel an order."""
        self._request("DELETE", f"orders/{broker_order_id}")
        return self.get_order_status(broker_order_id)
    
    def get_open_orders(self, symbol: str = None) -> list[dict]:
        """Get open (pending) orders, optionally filtered by symbol.
        
        Args:
            symbol: If provided, only return orders for this symbol.
            
        Returns:
            List of order dicts with id, symbol, side, qty, status, etc.
        """
        endpoint = "orders?status=open"
        if symbol:
            endpoint += f"&symbols={symbol}"
        
        data = self._request("GET", endpoint)
        return data if data else []
    
    def cancel_open_orders(self, symbol: str, side: str = None) -> int:
        """Cancel all open orders for a symbol, optionally filtered by side.
        
        Args:
            symbol: Symbol to cancel orders for.
            side: If provided, only cancel "buy" or "sell" orders.
            
        Returns:
            Number of orders cancelled.
        """
        orders = self.get_open_orders(symbol)
        cancelled = 0
        
        for order in orders:
            if side and order.get("side") != side:
                continue
            try:
                order_id = order.get("id")
                self._request("DELETE", f"orders/{order_id}")
                print(f"[Warrior] Cancelled pending order: {symbol} {order.get('side')} {order.get('qty')}")
                cancelled += 1
            except Exception as e:
                print(f"[Warrior] Failed to cancel order {order.get('id')}: {e}")
        
        return cancelled
    
    def get_order_status(self, broker_order_id: str) -> BrokerOrder:
        """Get current order status."""
        data = self._request("GET", f"orders/{broker_order_id}")
        if not data:
            raise OrderNotFoundError(f"Order not found: {broker_order_id}")
        
        # Find client_order_id from our map or use the one from response
        client_id_str = data.get("client_order_id", "")
        try:
            client_order_id = UUID(client_id_str)
        except (ValueError, TypeError):
            # Generate a placeholder if not found
            client_order_id = UUID(int=0)
        
        return self._parse_order(data, client_order_id)
    
    def get_positions(self) -> Dict[str, BrokerPosition]:
        """Get all open positions."""
        data = self._request("GET", "positions")
        if not data:
            return {}
        
        positions = {}
        for p in data:
            qty = int(p["qty"])
            market_value = Decimal(str(p["market_value"]))
            
            # Use Alpaca's current_price directly
            current_price_raw = p.get("current_price")
            current_price = Decimal(str(current_price_raw)) if current_price_raw else (market_value / qty if qty > 0 else None)
            
            # Get today's P/L % from Alpaca (position-based, not stock daily change)
            # This is how much YOUR POSITION changed today, from yesterday's close
            change_today_raw = p.get("unrealized_intraday_plpc")
            change_today = Decimal(str(change_today_raw)) * 100 if change_today_raw else None  # Convert to %
            
            # Get today's P/L in dollars from Alpaca
            today_pnl_raw = p.get("unrealized_intraday_pl")
            today_pnl = Decimal(str(today_pnl_raw)) if today_pnl_raw else None
            
            positions[p["symbol"]] = BrokerPosition(
                symbol=p["symbol"],
                quantity=qty,
                avg_price=Decimal(str(p["avg_entry_price"])),
                market_value=market_value,
                unrealized_pnl=Decimal(str(p["unrealized_pl"])),
                current_price=current_price,
                change_today=change_today,
                today_pnl=today_pnl,
            )
        
        return positions
    
    def get_account_value(self) -> Decimal:
        """Get total account value."""
        data = self._request("GET", "account")
        if not data:
            raise AlpacaBrokerError("Could not get account info")
        
        return Decimal(str(data.get("equity", 0)))
    
    def get_position_entry_dates(self, symbols: list[str] = None) -> Dict[str, datetime]:
        """
        Get the earliest fill date for each open position.
        
        Alpaca positions API doesn't return entry dates, so we query
        the orders API to find when each position was originally opened.
        
        Args:
            symbols: Optional list of symbols to check. If None, checks all open positions.
            
        Returns:
            Dict mapping symbol -> earliest fill datetime
        """
        # Get all filled buy orders (last 90 days by default)
        try:
            data = self._request("GET", "orders?status=filled&limit=500")
        except Exception as e:
            print(f"[AlpacaBroker] Failed to fetch orders for entry dates: {e}")
            return {}
        
        if not data:
            return {}
        
        # Find earliest fill date per symbol for buy orders
        entry_dates: Dict[str, datetime] = {}
        
        for order in data:
            symbol = order.get("symbol")
            side = order.get("side", "").lower()
            filled_at_str = order.get("filled_at")
            
            # Only consider buy orders (positions are opened by buys)
            if side != "buy" or not filled_at_str:
                continue
            
            # Filter by requested symbols if provided
            if symbols and symbol not in symbols:
                continue
            
            try:
                filled_at = datetime.fromisoformat(filled_at_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            
            # Keep the earliest fill date per symbol
            if symbol not in entry_dates or filled_at < entry_dates[symbol]:
                entry_dates[symbol] = filled_at
        
        return entry_dates
    
    def get_daily_capital_stats(self) -> dict:
        """
        Calculate capital statistics for today's trading.
        
        Returns:
            Dict with:
            - peak_exposure: Maximum capital deployed at any point today
            - total_capital_deployed: Sum of all buy order values today
            - total_realized_pnl: P&L from closed trades today
        """
        from zoneinfo import ZoneInfo
        
        # Get today's date in ET
        et = ZoneInfo("America/New_York")
        today = datetime.now(et).date()
        today_start = datetime(today.year, today.month, today.day, tzinfo=et)
        
        try:
            # Fetch today's filled orders
            data = self._request("GET", "orders?status=filled&limit=500")
        except Exception as e:
            print(f"[AlpacaBroker] Failed to fetch orders for capital stats: {e}")
            return {"peak_exposure": 0, "total_capital_deployed": 0, "total_realized_pnl": 0}
        
        if not data:
            return {"peak_exposure": 0, "total_capital_deployed": 0, "total_realized_pnl": 0}
        
        # Process orders chronologically to calculate peak exposure
        trades = []
        for order in data:
            filled_at_str = order.get("filled_at")
            if not filled_at_str:
                continue
            
            try:
                filled_at = datetime.fromisoformat(filled_at_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            
            # Filter to today only
            if filled_at.astimezone(et).date() != today:
                continue
            
            symbol = order.get("symbol")
            side = order.get("side", "").lower()
            qty = int(float(order.get("filled_qty", 0)))
            avg_price = float(order.get("filled_avg_price", 0))
            
            trades.append({
                "time": filled_at,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": avg_price,
                "value": qty * avg_price,
            })
        
        if not trades:
            return {"peak_exposure": 0, "total_capital_deployed": 0, "total_realized_pnl": 0}
        
        # Sort by time ascending
        trades.sort(key=lambda t: t["time"])
        
        # Calculate peak exposure by simulating position changes
        positions: dict[str, dict] = {}  # symbol -> {qty, avg_cost}
        current_exposure = 0.0
        peak_exposure = 0.0
        total_capital_deployed = 0.0
        total_realized_pnl = 0.0
        
        for trade in trades:
            symbol = trade["symbol"]
            side = trade["side"]
            qty = trade["qty"]
            price = trade["price"]
            value = trade["value"]
            
            if side == "buy":
                # Add to position
                total_capital_deployed += value
                
                if symbol not in positions:
                    positions[symbol] = {"qty": 0, "total_cost": 0}
                
                pos = positions[symbol]
                pos["total_cost"] += value
                pos["qty"] += qty
                
                current_exposure = sum(p["total_cost"] for p in positions.values() if p["qty"] > 0)
                peak_exposure = max(peak_exposure, current_exposure)
                
            elif side == "sell":
                # Remove from position
                if symbol in positions and positions[symbol]["qty"] > 0:
                    pos = positions[symbol]
                    avg_cost = pos["total_cost"] / pos["qty"] if pos["qty"] > 0 else 0
                    
                    # Calculate realized P&L
                    cost_basis = avg_cost * qty
                    realized = value - cost_basis
                    total_realized_pnl += realized
                    
                    # Update position
                    pos["qty"] -= qty
                    pos["total_cost"] = max(0, pos["total_cost"] - cost_basis)
                
                current_exposure = sum(p["total_cost"] for p in positions.values() if p["qty"] > 0)
        
        return {
            "peak_exposure": round(peak_exposure, 2),
            "total_capital_deployed": round(total_capital_deployed, 2),
            "total_realized_pnl": round(total_realized_pnl, 2),
        }
