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
            positions[p["symbol"]] = BrokerPosition(
                symbol=p["symbol"],
                quantity=int(p["qty"]),
                avg_price=Decimal(str(p["avg_entry_price"])),
                market_value=Decimal(str(p["market_value"])),
                unrealized_pnl=Decimal(str(p["unrealized_pl"])),
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
