"""
Alpaca Streaming Client

Real-time price streaming via Alpaca WebSocket for position monitoring.
Uses Alpaca's Data API v2 WebSocket.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Set
from datetime import datetime

import websockets

# Import centralized config
from nexus2 import config as app_config
from nexus2.utils.time_utils import now_utc


logger = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    """Configuration for Alpaca streaming."""
    api_key: str
    api_secret: str
    feed: str = "iex"  # "iex" (free) or "sip" (paid)
    ws_url: str = "wss://stream.data.alpaca.markets/v2"


@dataclass
class TradeUpdate:
    """Real-time trade update from stream."""
    symbol: str
    price: Decimal
    size: int
    timestamp: datetime


@dataclass
class QuoteUpdate:
    """Real-time quote update from stream."""
    symbol: str
    bid_price: Decimal
    ask_price: Decimal
    bid_size: int
    ask_size: int
    timestamp: datetime
    
    @property
    def mid_price(self) -> Decimal:
        return (self.bid_price + self.ask_price) / 2


class AlpacaStreamingClient:
    """
    Real-time streaming client for Alpaca market data.
    
    Subscribes to trades/quotes for symbols and triggers callbacks
    when prices update.
    """
    
    def __init__(self, config: Optional[StreamConfig] = None):
        if config:
            self.config = config
        else:
            # Load from centralized config
            self.config = StreamConfig(
                api_key=app_config.ALPACA_API_KEY,
                api_secret=app_config.ALPACA_API_SECRET,
            )
        
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Subscribed symbols
        self._subscribed_symbols: Set[str] = set()
        
        # Latest prices (updated by stream)
        self._prices: Dict[str, Decimal] = {}
        
        # Callbacks
        self._on_price_update: Optional[Callable[[str, Decimal], None]] = None
        self._on_trade: Optional[Callable[[TradeUpdate], None]] = None
        self._on_quote: Optional[Callable[[QuoteUpdate], None]] = None
    
    def set_callbacks(
        self,
        on_price_update: Callable[[str, Decimal], None] = None,
        on_trade: Callable[[TradeUpdate], None] = None,
        on_quote: Callable[[QuoteUpdate], None] = None,
    ):
        """Set callbacks for price updates."""
        self._on_price_update = on_price_update
        self._on_trade = on_trade
        self._on_quote = on_quote
    
    async def start(self) -> dict:
        """Start the streaming connection."""
        if self._running:
            return {"status": "already_running"}
        
        self._running = True
        self._task = asyncio.create_task(self._connection_loop())
        
        logger.info("Alpaca streaming client started")
        return {"status": "started"}
    
    async def stop(self) -> dict:
        """Stop the streaming connection."""
        if not self._running:
            return {"status": "already_stopped"}
        
        self._running = False
        
        if self._ws:
            await self._ws.close()
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Alpaca streaming client stopped")
        return {"status": "stopped"}
    
    async def subscribe(self, symbols: List[str]) -> dict:
        """Subscribe to symbols for price updates."""
        new_symbols = set(symbols) - self._subscribed_symbols
        
        if not new_symbols:
            return {"status": "already_subscribed", "symbols": list(symbols)}
        
        if self._ws:
            # Send subscription message
            sub_msg = {
                "action": "subscribe",
                "trades": list(new_symbols),
                "quotes": list(new_symbols),
            }
            await self._ws.send(json.dumps(sub_msg))
            
            self._subscribed_symbols.update(new_symbols)
            logger.info(f"Subscribed to: {new_symbols}")
        
        return {"status": "subscribed", "symbols": list(new_symbols)}
    
    async def unsubscribe(self, symbols: List[str]) -> dict:
        """Unsubscribe from symbols."""
        to_remove = set(symbols) & self._subscribed_symbols
        
        if not to_remove:
            return {"status": "not_subscribed"}
        
        if self._ws:
            unsub_msg = {
                "action": "unsubscribe",
                "trades": list(to_remove),
                "quotes": list(to_remove),
            }
            await self._ws.send(json.dumps(unsub_msg))
            
            self._subscribed_symbols -= to_remove
        
        return {"status": "unsubscribed", "symbols": list(to_remove)}
    
    def get_price(self, symbol: str) -> Optional[Decimal]:
        """Get latest streamed price for a symbol."""
        return self._prices.get(symbol)
    
    def get_all_prices(self) -> Dict[str, Decimal]:
        """Get all current prices."""
        return dict(self._prices)
    
    async def _connection_loop(self):
        """Main connection loop with auto-reconnect."""
        reconnect_delay = 1
        
        while self._running:
            try:
                await self._connect_and_stream()
                reconnect_delay = 1  # Reset on successful connection
            except Exception as e:
                logger.error(f"Stream connection error: {e}")
                
                if self._running:
                    logger.info(f"Reconnecting in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 60)  # Exponential backoff
    
    async def _connect_and_stream(self):
        """Connect to WebSocket and handle messages."""
        ws_url = f"{self.config.ws_url}/{self.config.feed}"
        
        async with websockets.connect(ws_url) as ws:
            self._ws = ws
            
            # Authenticate
            auth_msg = {
                "action": "auth",
                "key": self.config.api_key,
                "secret": self.config.api_secret,
            }
            await ws.send(json.dumps(auth_msg))
            
            # Wait for auth response
            auth_response = await ws.recv()
            auth_data = json.loads(auth_response)
            logger.debug(f"Auth response: {auth_data}")
            
            # Re-subscribe to any previously subscribed symbols
            if self._subscribed_symbols:
                await self.subscribe(list(self._subscribed_symbols))
            
            # Message loop
            async for message in ws:
                await self._handle_message(message)
    
    async def _handle_message(self, message: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            
            # Alpaca sends arrays of messages
            if not isinstance(data, list):
                data = [data]
            
            for msg in data:
                msg_type = msg.get("T")
                
                if msg_type == "t":  # Trade
                    await self._handle_trade(msg)
                elif msg_type == "q":  # Quote
                    await self._handle_quote(msg)
                elif msg_type == "error":
                    logger.error(f"Stream error: {msg}")
                elif msg_type in ("success", "subscription"):
                    logger.debug(f"Stream message: {msg}")
                    
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_trade(self, msg: dict):
        """Handle trade message."""
        symbol = msg.get("S", "")
        price = Decimal(str(msg.get("p", 0)))
        size = int(msg.get("s", 0))
        
        # Update price cache
        self._prices[symbol] = price
        
        # Trigger callbacks
        if self._on_price_update:
            self._on_price_update(symbol, price)
        
        if self._on_trade:
            trade = TradeUpdate(
                symbol=symbol,
                price=price,
                size=size,
                timestamp=now_utc(),
            )
            self._on_trade(trade)
    
    async def _handle_quote(self, msg: dict):
        """Handle quote message."""
        symbol = msg.get("S", "")
        bid = Decimal(str(msg.get("bp", 0)))
        ask = Decimal(str(msg.get("ap", 0)))
        
        # Update price cache with mid price
        if bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            self._prices[symbol] = mid
            
            # Trigger callbacks
            if self._on_price_update:
                self._on_price_update(symbol, mid)
        
        if self._on_quote:
            quote = QuoteUpdate(
                symbol=symbol,
                bid_price=bid,
                ask_price=ask,
                bid_size=int(msg.get("bs", 0)),
                ask_size=int(msg.get("as", 0)),
                timestamp=now_utc(),
            )
            self._on_quote(quote)
    
    def get_status(self) -> dict:
        """Get streaming client status."""
        return {
            "running": self._running,
            "connected": self._ws is not None and not self._ws.closed if self._ws else False,
            "subscribed_symbols": list(self._subscribed_symbols),
            "cached_prices": len(self._prices),
            "feed": self.config.feed,
        }


# Singleton for shared streaming client
_streaming_client: Optional[AlpacaStreamingClient] = None


def get_streaming_client() -> AlpacaStreamingClient:
    """Get singleton streaming client."""
    global _streaming_client
    if _streaming_client is None:
        _streaming_client = AlpacaStreamingClient()
    return _streaming_client
