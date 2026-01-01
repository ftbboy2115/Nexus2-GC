"""
WebSocket Routes

Real-time updates for positions, P&L, and orders.
"""

import asyncio
import json
from typing import List, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from decimal import Decimal
import random

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        print(f"[WS] Client connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        print(f"[WS] Client disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        if not self.active_connections:
            return
        
        data = json.dumps(message)
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)
        
        for conn in disconnected:
            self.active_connections.discard(conn)


# Managers for different channels
position_manager = ConnectionManager()
order_manager = ConnectionManager()


def get_mock_positions():
    """Generate mock position data for demo."""
    symbols = ['NVDA', 'AAPL', 'META', 'TSLA', 'AMD']
    positions = []
    
    for i, symbol in enumerate(symbols):
        entry = 100 + i * 50 + random.random() * 10
        current = entry * (1 + (random.random() - 0.4) * 0.1)
        shares = 50 + i * 20
        pnl = (current - entry) * shares
        pnl_pct = ((current - entry) / entry) * 100
        
        positions.append({
            "id": f"pos-{i+1}",
            "symbol": symbol,
            "shares": shares,
            "entry_price": round(entry, 2),
            "current_price": round(current, 2),
            "unrealized_pnl": round(pnl, 2),
            "unrealized_pnl_pct": round(pnl_pct, 2),
            "status": "open",
        })
    
    return positions


@router.websocket("/ws/positions")
async def websocket_positions(websocket: WebSocket):
    """
    WebSocket endpoint for real-time position updates.
    
    Sends position data every second with updated prices.
    """
    await position_manager.connect(websocket)
    
    try:
        while True:
            # Generate mock position updates
            positions = get_mock_positions()
            
            # Calculate totals
            total_pnl = sum(p["unrealized_pnl"] for p in positions)
            
            message = {
                "type": "positions_update",
                "positions": positions,
                "total_unrealized_pnl": round(total_pnl, 2),
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            await websocket.send_json(message)
            
            # Wait 1 second before next update
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        position_manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Error: {e}")
        position_manager.disconnect(websocket)


@router.websocket("/ws/orders")
async def websocket_orders(websocket: WebSocket):
    """
    WebSocket endpoint for real-time order updates.
    
    Clients connect and receive order status updates via broadcast.
    """
    await order_manager.connect(websocket)
    
    try:
        # Keep connection alive, waiting for broadcasts
        while True:
            # Wait for client messages (ping/pong or disconnect)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
            
    except WebSocketDisconnect:
        order_manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS Orders] Error: {e}")
        order_manager.disconnect(websocket)


async def broadcast_order_update(
    order_id: str,
    symbol: str,
    status: str,
    shares: int,
    fill_price: float | None = None,
    message: str | None = None,
):
    """
    Broadcast order update to all connected clients.
    
    Call this from trade routes when order status changes.
    """
    print(f"[WS Orders] Broadcasting: {symbol} {status} - {len(order_manager.active_connections)} clients")
    update = {
        "type": "order_update",
        "order_id": order_id,
        "symbol": symbol,
        "status": status,  # submitted, pending, filled, cancelled, rejected
        "shares": shares,
        "fill_price": fill_price,
        "message": message,
    }
    await order_manager.broadcast(update)

