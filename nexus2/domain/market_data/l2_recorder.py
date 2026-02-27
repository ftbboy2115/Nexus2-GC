"""
L2 Order Book Recorder

Records L2 book snapshots to daily SQLite files for analysis and replay.
Uses a background thread for writes since SQLite is synchronous but the
L2 streamer operates in async context.

File rotation: data/l2/YYYY-MM-DD.db
Table: l2_snapshots

Feature-gated behind L2_ENABLED config flag.
"""

import json
import logging
import queue
import sqlite3
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from nexus2.domain.market_data.l2_types import L2BookSnapshot

logger = logging.getLogger(__name__)

# How often the writer thread flushes queued snapshots to disk
FLUSH_INTERVAL_SECONDS = 5

# Maximum queue size before dropping messages
MAX_QUEUE_SIZE = 10_000

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS l2_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    best_bid REAL,
    best_ask REAL,
    spread REAL,
    bid_levels INTEGER,
    ask_levels INTEGER,
    total_bid_volume INTEGER,
    total_ask_volume INTEGER,
    bid_ask_ratio REAL,
    bids_json TEXT,
    asks_json TEXT
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_l2_symbol_ts ON l2_snapshots (symbol, timestamp);
"""


class L2Recorder:
    """
    Writes L2BookSnapshot objects to daily SQLite databases.
    
    Snapshots are queued and flushed to disk in batches by a background thread.
    Each day gets its own database file: data/l2/YYYY-MM-DD.db
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        flush_interval: float = FLUSH_INTERVAL_SECONDS,
        sample_rate_seconds: int = 1,
    ):
        self._data_dir = data_dir or (
            Path(__file__).parent.parent.parent.parent / "data" / "l2"
        )
        self._flush_interval = flush_interval
        self._sample_rate_seconds = sample_rate_seconds

        # Queue for async→sync bridge
        self._queue: queue.Queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)

        # Sampling: track last write time per symbol to avoid excessive writes
        self._last_write_time: dict[str, float] = {}

        # Writer thread
        self._writer_thread: Optional[threading.Thread] = None
        self._running = False

        # Stats
        self._total_written = 0
        self._total_dropped = 0
        self._current_db_path: Optional[Path] = None

    @property
    def stats(self) -> dict:
        """Recorder statistics."""
        return {
            "running": self._running,
            "total_written": self._total_written,
            "total_dropped": self._total_dropped,
            "queue_size": self._queue.qsize(),
            "current_db": str(self._current_db_path) if self._current_db_path else None,
        }

    def start(self):
        """Start the background writer thread."""
        if self._running:
            logger.warning("[L2Rec] Recorder already running")
            return

        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._writer_loop, daemon=True, name="l2_recorder"
        )
        self._writer_thread.start()
        logger.info("[L2Rec] Recorder started, writing to %s", self._data_dir)

    def stop(self):
        """Stop the background writer thread and flush remaining queue."""
        self._running = False
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=10)
        logger.info(
            "[L2Rec] Recorder stopped. Written: %d, Dropped: %d",
            self._total_written, self._total_dropped,
        )

    def record(self, snapshot: L2BookSnapshot):
        """
        Queue a snapshot for recording.
        
        Applies sample rate filtering to avoid flooding the database.
        Called from the L2 streamer's callback (in the async event loop).
        """
        now = time.time()
        symbol = snapshot.symbol

        # Sample rate throttling
        last_write = self._last_write_time.get(symbol, 0)
        if now - last_write < self._sample_rate_seconds:
            return

        try:
            self._queue.put_nowait(snapshot)
            self._last_write_time[symbol] = now
        except queue.Full:
            self._total_dropped += 1
            if self._total_dropped % 100 == 1:
                logger.warning(
                    "[L2Rec] Queue full, dropped %d snapshots total",
                    self._total_dropped,
                )

    # ---------------------------------------------------------------
    # Writer Thread
    # ---------------------------------------------------------------

    def _writer_loop(self):
        """Background thread that periodically flushes the queue to SQLite."""
        logger.info("[L2Rec] Writer thread started")

        while self._running:
            try:
                self._flush_batch()
            except Exception as e:
                logger.error("[L2Rec] Writer error: %s", e, exc_info=True)

            time.sleep(self._flush_interval)

        # Final flush on shutdown
        try:
            self._flush_batch()
        except Exception as e:
            logger.error("[L2Rec] Final flush error: %s", e, exc_info=True)

        logger.info("[L2Rec] Writer thread exiting")

    def _flush_batch(self):
        """Drain the queue and write all pending snapshots to SQLite."""
        batch = []
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if not batch:
            return

        # Group by date for file rotation
        by_date: dict[str, list] = {}
        for snapshot in batch:
            date_key = snapshot.timestamp.strftime("%Y-%m-%d")
            by_date.setdefault(date_key, []).append(snapshot)

        for date_key, snapshots in by_date.items():
            db_path = self._data_dir / f"{date_key}.db"
            self._write_snapshots(db_path, snapshots)

    def _write_snapshots(self, db_path: Path, snapshots: list):
        """Write a batch of snapshots to the specified SQLite database."""
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(CREATE_TABLE_SQL)
            conn.execute(CREATE_INDEX_SQL)

            rows = []
            for snapshot in snapshots:
                bids_json = json.dumps(
                    [
                        {
                            "price": str(level.price),
                            "volume": level.total_volume,
                            "num_entries": level.num_entries,
                            "exchanges": [
                                {
                                    "exchange": e.exchange_id,
                                    "volume": e.volume,
                                    "sequence": e.sequence,
                                }
                                for e in level.exchanges
                            ],
                        }
                        for level in snapshot.bids
                    ]
                )
                asks_json = json.dumps(
                    [
                        {
                            "price": str(level.price),
                            "volume": level.total_volume,
                            "num_entries": level.num_entries,
                            "exchanges": [
                                {
                                    "exchange": e.exchange_id,
                                    "volume": e.volume,
                                    "sequence": e.sequence,
                                }
                                for e in level.exchanges
                            ],
                        }
                        for level in snapshot.asks
                    ]
                )

                rows.append((
                    snapshot.timestamp.isoformat(),
                    snapshot.symbol,
                    float(snapshot.best_bid) if snapshot.best_bid else None,
                    float(snapshot.best_ask) if snapshot.best_ask else None,
                    float(snapshot.spread) if snapshot.spread else None,
                    len(snapshot.bids),
                    len(snapshot.asks),
                    snapshot.total_bid_volume,
                    snapshot.total_ask_volume,
                    snapshot.bid_ask_ratio,
                    bids_json,
                    asks_json,
                ))

            conn.executemany(
                """INSERT INTO l2_snapshots 
                   (timestamp, symbol, best_bid, best_ask, spread, 
                    bid_levels, ask_levels, total_bid_volume, total_ask_volume, 
                    bid_ask_ratio, bids_json, asks_json) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.commit()
            conn.close()

            self._total_written += len(rows)
            self._current_db_path = db_path

            if len(rows) > 0:
                logger.debug(
                    "[L2Rec] Wrote %d snapshots to %s", len(rows), db_path.name
                )

        except Exception as e:
            logger.error(
                "[L2Rec] Failed to write to %s: %s", db_path, e, exc_info=True
            )
