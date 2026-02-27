"""
L2 (Level 2 / Order Book Depth) Data Types

Typed data models for Level 2 order book data from Schwab streaming API.
Used by the L2 streamer, recorder, and signal modules.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any

from nexus2.utils.time_utils import now_utc


class L2BookSide(Enum):
    """Side of the order book."""
    BID = "bid"
    ASK = "ask"


@dataclass
class L2ExchangeEntry:
    """Volume contribution from a single exchange at a price level."""
    exchange_id: str
    volume: int
    sequence: int = 0


@dataclass
class L2PriceLevel:
    """A single price level in the order book."""
    price: Decimal
    total_volume: int
    num_entries: int = 0
    exchanges: List[L2ExchangeEntry] = field(default_factory=list)

    @property
    def is_wall(self) -> bool:
        """Quick heuristic: >10K shares at a single level is notable."""
        return self.total_volume >= 10_000


@dataclass
class L2BookSnapshot:
    """
    Complete order book snapshot for a symbol at a point in time.
    
    Contains bid and ask price levels sorted by best price first:
    - bids: highest price first (best bid at index 0)
    - asks: lowest price first (best ask at index 0)
    """
    symbol: str
    timestamp: datetime
    bids: List[L2PriceLevel] = field(default_factory=list)
    asks: List[L2PriceLevel] = field(default_factory=list)
    source: str = "schwab"

    @property
    def best_bid(self) -> Optional[Decimal]:
        """Best (highest) bid price."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        """Best (lowest) ask price."""
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> Optional[Decimal]:
        """Bid-ask spread."""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def total_bid_volume(self) -> int:
        """Sum of all bid level volumes."""
        return sum(level.total_volume for level in self.bids)

    @property
    def total_ask_volume(self) -> int:
        """Sum of all ask level volumes."""
        return sum(level.total_volume for level in self.asks)

    @property
    def bid_ask_ratio(self) -> Optional[float]:
        """Ratio of bid volume to ask volume. >1 = more buyers."""
        if self.total_ask_volume > 0:
            return self.total_bid_volume / self.total_ask_volume
        return None

    @property
    def depth_levels(self) -> int:
        """Number of price levels (max of bid/ask sides)."""
        return max(len(self.bids), len(self.asks))

    def summary(self) -> str:
        """One-line summary for logging."""
        spread_str = f"${self.spread:.4f}" if self.spread else "N/A"
        return (
            f"{self.symbol}: bid={self.best_bid} ask={self.best_ask} "
            f"spread={spread_str} levels={self.depth_levels} "
            f"bid_vol={self.total_bid_volume} ask_vol={self.total_ask_volume}"
        )


def parse_schwab_book_message(msg: dict) -> Optional[L2BookSnapshot]:
    """
    Parse a raw schwab-py book update message into L2BookSnapshot(s).
    
    After schwab-py's _BookHandler relabeling, each content item has:
    - 'key': str (symbol)
    - 'BOOK_TIME': int (epoch ms)
    - 'BIDS': list of {BID_PRICE, TOTAL_VOLUME, NUM_BIDS, BIDS: [{EXCHANGE, BID_VOLUME, SEQUENCE}]}
    - 'ASKS': list of {ASK_PRICE, TOTAL_VOLUME, NUM_ASKS, ASKS: [{EXCHANGE, ASK_VOLUME, SEQUENCE}]}
    """
    try:
        content = msg.get("content", [msg])
        if isinstance(content, list):
            snapshots = []
            for item in content:
                snapshot = _parse_single_book(item)
                if snapshot:
                    snapshots.append(snapshot)
            return snapshots[0] if len(snapshots) == 1 else snapshots if snapshots else None
        return _parse_single_book(content)
    except Exception:
        return None


def _parse_single_book(data: dict) -> Optional[L2BookSnapshot]:
    """Parse a single book entry from the message content."""
    symbol = data.get("key") or data.get("SYMBOL")
    if not symbol:
        return None

    # Parse timestamp
    book_time = data.get("BOOK_TIME") or data.get("3")
    if book_time:
        from datetime import timezone
        timestamp = datetime.fromtimestamp(book_time / 1000, tz=timezone.utc)
    else:
        timestamp = now_utc()

    # Parse bid levels
    raw_bids = data.get("BIDS") or data.get("2", [])
    bids = _parse_bid_levels(raw_bids)
    # Sort bids: highest price first (best bid)
    bids.sort(key=lambda l: l.price, reverse=True)

    # Parse ask levels
    raw_asks = data.get("ASKS") or data.get("3", [])
    asks = _parse_ask_levels(raw_asks)
    # Sort asks: lowest price first (best ask)
    asks.sort(key=lambda l: l.price)

    return L2BookSnapshot(
        symbol=symbol,
        timestamp=timestamp,
        bids=bids,
        asks=asks,
        source="schwab",
    )


def _parse_bid_levels(raw_levels: list) -> List[L2PriceLevel]:
    """
    Parse bid-side price levels from schwab-py relabeled message.
    
    After relabeling: {BID_PRICE, TOTAL_VOLUME, NUM_BIDS, BIDS: [{EXCHANGE, BID_VOLUME, SEQUENCE}]}
    Before relabeling (numeric keys): {0: price, 1: volume, 2: num_bids, 3: per_exchange_list}
    """
    levels = []
    for raw in raw_levels:
        if isinstance(raw, dict):
            price = raw.get("BID_PRICE") or raw.get("0", 0)
            volume = raw.get("TOTAL_VOLUME") or raw.get("1", 0)
            num_entries = raw.get("NUM_BIDS") or raw.get("2", 0)
            exchange_data = raw.get("BIDS") or raw.get("3", [])

            exchanges = _parse_exchange_entries(exchange_data, volume_key="BID_VOLUME")

            levels.append(L2PriceLevel(
                price=Decimal(str(price)),
                total_volume=int(volume),
                num_entries=int(num_entries),
                exchanges=exchanges,
            ))
    return levels


def _parse_ask_levels(raw_levels: list) -> List[L2PriceLevel]:
    """
    Parse ask-side price levels from schwab-py relabeled message.
    
    After relabeling: {ASK_PRICE, TOTAL_VOLUME, NUM_ASKS, ASKS: [{EXCHANGE, ASK_VOLUME, SEQUENCE}]}
    Before relabeling (numeric keys): {0: price, 1: volume, 2: num_asks, 3: per_exchange_list}
    """
    levels = []
    for raw in raw_levels:
        if isinstance(raw, dict):
            price = raw.get("ASK_PRICE") or raw.get("0", 0)
            volume = raw.get("TOTAL_VOLUME") or raw.get("1", 0)
            num_entries = raw.get("NUM_ASKS") or raw.get("2", 0)
            exchange_data = raw.get("ASKS") or raw.get("3", [])

            exchanges = _parse_exchange_entries(exchange_data, volume_key="ASK_VOLUME")

            levels.append(L2PriceLevel(
                price=Decimal(str(price)),
                total_volume=int(volume),
                num_entries=int(num_entries),
                exchanges=exchanges,
            ))
    return levels


def _parse_exchange_entries(
    exchange_data: list, volume_key: str = "BID_VOLUME"
) -> List[L2ExchangeEntry]:
    """
    Parse per-exchange entries from a bid or ask level.
    
    After relabeling: [{EXCHANGE, BID_VOLUME|ASK_VOLUME, SEQUENCE}]
    Before relabeling: [{0: exchange, 1: volume, 2: sequence}]
    """
    exchanges = []
    if isinstance(exchange_data, list):
        for entry in exchange_data:
            if isinstance(entry, dict):
                exchanges.append(L2ExchangeEntry(
                    exchange_id=str(entry.get("EXCHANGE") or entry.get("0", "")),
                    volume=int(entry.get(volume_key) or entry.get("1", 0)),
                    sequence=int(entry.get("SEQUENCE") or entry.get("2", 0)),
                ))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                # Fallback for raw list format
                exchanges.append(L2ExchangeEntry(
                    exchange_id=str(entry[0]),
                    volume=int(entry[1]),
                    sequence=int(entry[2]) if len(entry) > 2 else 0,
                ))
    return exchanges
