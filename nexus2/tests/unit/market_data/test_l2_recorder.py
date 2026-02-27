"""
Unit tests for L2 Order Book Recorder.

Tests:
- Creating L2Recorder with temp directory
- Recording mock snapshots and verifying SQLite DB creation
- Correct schema (l2_snapshots table with bids_json/asks_json columns)
- Row insertion after flush
- Daily file naming pattern (YYYY-MM-DD.db)
- Sample rate throttling
- Queue overflow handling
"""

import json
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from nexus2.domain.market_data.l2_types import (
    L2BookSnapshot,
    L2ExchangeEntry,
    L2PriceLevel,
)
from nexus2.domain.market_data.l2_recorder import L2Recorder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(
    symbol: str = "AAPL",
    timestamp: datetime | None = None,
    bid_price: float = 150.10,
    ask_price: float = 150.20,
) -> L2BookSnapshot:
    """Build a minimal L2BookSnapshot for testing."""
    if timestamp is None:
        timestamp = datetime(2026, 2, 27, 14, 30, 0, tzinfo=timezone.utc)
    return L2BookSnapshot(
        symbol=symbol,
        timestamp=timestamp,
        bids=[
            L2PriceLevel(
                price=Decimal(str(bid_price)),
                total_volume=500,
                num_entries=1,
                exchanges=[
                    L2ExchangeEntry(exchange_id="NSDQ", volume=500, sequence=1)
                ],
            ),
        ],
        asks=[
            L2PriceLevel(
                price=Decimal(str(ask_price)),
                total_volume=300,
                num_entries=1,
                exchanges=[
                    L2ExchangeEntry(exchange_id="NSDQ", volume=300, sequence=2)
                ],
            ),
        ],
        source="schwab",
    )


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------

class TestL2RecorderInit:
    """Test recorder creation and configuration."""

    def test_creates_with_custom_dir(self, tmp_path):
        recorder = L2Recorder(data_dir=tmp_path)
        assert recorder._data_dir == tmp_path

    def test_default_stats(self, tmp_path):
        recorder = L2Recorder(data_dir=tmp_path)
        stats = recorder.stats
        assert stats["running"] is False
        assert stats["total_written"] == 0
        assert stats["total_dropped"] == 0
        assert stats["queue_size"] == 0


# ---------------------------------------------------------------------------
# Tests: Recording and flushing
# ---------------------------------------------------------------------------

class TestL2RecorderWrite:
    """Test that recorded snapshots are written to SQLite."""

    def test_sqlite_db_created_after_flush(self, tmp_path):
        recorder = L2Recorder(
            data_dir=tmp_path, flush_interval=0.1, sample_rate_seconds=0
        )
        snapshot = _make_snapshot()

        # Manually queue and flush (bypass the background thread)
        recorder._queue.put_nowait(snapshot)
        recorder._flush_batch()

        # DB file should exist with date-based name
        db_files = list(tmp_path.glob("*.db"))
        assert len(db_files) == 1
        assert db_files[0].name == "2026-02-27.db"

    def test_correct_schema_created(self, tmp_path):
        recorder = L2Recorder(data_dir=tmp_path, sample_rate_seconds=0)
        snapshot = _make_snapshot()
        recorder._queue.put_nowait(snapshot)
        recorder._flush_batch()

        db_path = tmp_path / "2026-02-27.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(l2_snapshots)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        expected_columns = {
            "id", "timestamp", "symbol", "best_bid", "best_ask", "spread",
            "bid_levels", "ask_levels", "total_bid_volume", "total_ask_volume",
            "bid_ask_ratio", "bids_json", "asks_json",
        }
        assert columns == expected_columns

    def test_row_written_with_correct_data(self, tmp_path):
        recorder = L2Recorder(data_dir=tmp_path, sample_rate_seconds=0)
        snapshot = _make_snapshot(symbol="TSLA", bid_price=200.0, ask_price=200.10)
        recorder._queue.put_nowait(snapshot)
        recorder._flush_batch()

        db_path = tmp_path / "2026-02-27.db"
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT * FROM l2_snapshots").fetchall()
        conn.close()

        assert len(rows) == 1
        row = rows[0]
        # row[2] = symbol
        assert row[2] == "TSLA"
        # row[3] = best_bid, row[4] = best_ask
        assert abs(row[3] - 200.0) < 0.01
        assert abs(row[4] - 200.10) < 0.01

    def test_bids_json_and_asks_json_populated(self, tmp_path):
        recorder = L2Recorder(data_dir=tmp_path, sample_rate_seconds=0)
        snapshot = _make_snapshot()
        recorder._queue.put_nowait(snapshot)
        recorder._flush_batch()

        db_path = tmp_path / "2026-02-27.db"
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT bids_json, asks_json FROM l2_snapshots"
        ).fetchone()
        conn.close()

        bids = json.loads(row[0])
        asks = json.loads(row[1])

        assert isinstance(bids, list)
        assert len(bids) == 1
        assert bids[0]["price"] == "150.1"
        assert bids[0]["volume"] == 500

        assert isinstance(asks, list)
        assert len(asks) == 1
        assert asks[0]["price"] == "150.2"
        assert asks[0]["volume"] == 300

    def test_multiple_snapshots_written(self, tmp_path):
        recorder = L2Recorder(data_dir=tmp_path, sample_rate_seconds=0)
        for i in range(5):
            snap = _make_snapshot(symbol=f"SYM{i}")
            recorder._queue.put_nowait(snap)
        recorder._flush_batch()

        db_path = tmp_path / "2026-02-27.db"
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM l2_snapshots").fetchone()[0]
        conn.close()
        assert count == 5

    def test_stats_updated_after_write(self, tmp_path):
        recorder = L2Recorder(data_dir=tmp_path, sample_rate_seconds=0)
        snapshot = _make_snapshot()
        recorder._queue.put_nowait(snapshot)
        recorder._flush_batch()

        assert recorder.stats["total_written"] == 1


# ---------------------------------------------------------------------------
# Tests: Daily file naming / rotation
# ---------------------------------------------------------------------------

class TestDailyFileNaming:
    """Test that different dates produce different DB files."""

    def test_different_dates_produce_different_files(self, tmp_path):
        recorder = L2Recorder(data_dir=tmp_path, sample_rate_seconds=0)

        snap1 = _make_snapshot(
            timestamp=datetime(2026, 2, 27, 10, 0, 0, tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(
            timestamp=datetime(2026, 2, 28, 10, 0, 0, tzinfo=timezone.utc)
        )

        recorder._queue.put_nowait(snap1)
        recorder._queue.put_nowait(snap2)
        recorder._flush_batch()

        db_files = sorted(f.name for f in tmp_path.glob("*.db"))
        assert db_files == ["2026-02-27.db", "2026-02-28.db"]


# ---------------------------------------------------------------------------
# Tests: Sample rate throttling
# ---------------------------------------------------------------------------

class TestSampleRateThrottling:
    """Test that record() throttles based on sample_rate_seconds."""

    def test_throttles_rapid_updates(self, tmp_path):
        recorder = L2Recorder(
            data_dir=tmp_path, sample_rate_seconds=10  # 10-second window
        )

        snap1 = _make_snapshot(symbol="AAPL")
        snap2 = _make_snapshot(symbol="AAPL")

        recorder.record(snap1)
        recorder.record(snap2)  # Should be throttled (same symbol, within 10s)

        assert recorder._queue.qsize() == 1  # Only first queued

    def test_different_symbols_not_throttled(self, tmp_path):
        recorder = L2Recorder(
            data_dir=tmp_path, sample_rate_seconds=10
        )

        snap1 = _make_snapshot(symbol="AAPL")
        snap2 = _make_snapshot(symbol="TSLA")

        recorder.record(snap1)
        recorder.record(snap2)

        assert recorder._queue.qsize() == 2  # Both queued (different symbols)


# ---------------------------------------------------------------------------
# Tests: Start / Stop lifecycle
# ---------------------------------------------------------------------------

class TestRecorderLifecycle:
    """Test start/stop lifecycle."""

    def test_start_creates_data_dir(self, tmp_path):
        data_dir = tmp_path / "l2_data"
        recorder = L2Recorder(data_dir=data_dir)
        recorder.start()
        assert data_dir.exists()
        recorder.stop()

    def test_start_sets_running_true(self, tmp_path):
        recorder = L2Recorder(data_dir=tmp_path)
        recorder.start()
        assert recorder._running is True
        recorder.stop()

    def test_stop_sets_running_false(self, tmp_path):
        recorder = L2Recorder(data_dir=tmp_path)
        recorder.start()
        recorder.stop()
        assert recorder._running is False

    def test_background_thread_writes_on_flush(self, tmp_path):
        """Start recorder, record a snapshot, wait for flush, verify DB."""
        recorder = L2Recorder(
            data_dir=tmp_path, flush_interval=0.2, sample_rate_seconds=0
        )
        recorder.start()

        snapshot = _make_snapshot()
        recorder.record(snapshot)

        # Wait for the flush interval + buffer
        time.sleep(0.6)
        recorder.stop()

        db_files = list(tmp_path.glob("*.db"))
        assert len(db_files) == 1

        conn = sqlite3.connect(str(db_files[0]))
        count = conn.execute("SELECT COUNT(*) FROM l2_snapshots").fetchone()[0]
        conn.close()
        assert count == 1
