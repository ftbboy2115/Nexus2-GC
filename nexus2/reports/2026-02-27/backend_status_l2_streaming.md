# Backend Status: L2 Streaming Phase 1

**Date**: 2026-02-27
**Agent**: Backend Specialist
**Status**: ✅ Complete — ready for Testing Specialist validation

---

## Files Created/Modified

### [NEW] `nexus2/adapters/market_data/schwab_l2_streamer.py`
Core async L2 streamer (~400 lines):
- Token bridge: reads Nexus `schwab_tokens.json` → schwab-py `{creation_timestamp, token}` format
- Uses `client_from_access_functions` to avoid file format conflicts with existing `schwab_adapter.py`
- StreamClient lifecycle: create, login, message loop, reconnect
- Dual exchange subscription: subscribes to both NYSE_BOOK and NASDAQ_BOOK per symbol
- Snapshot caching: `get_snapshot(symbol)` returns latest `L2BookSnapshot`
- Callback dispatch: optional `on_update` callback per snapshot
- Reconnection: exponential backoff up to 10 attempts
- Max symbol enforcement via `_max_symbols` parameter

### [NEW] `nexus2/domain/market_data/l2_recorder.py`
SQLite recorder (~240 lines):
- Daily file rotation: `data/l2/YYYY-MM-DD.db`
- Table `l2_snapshots` with summary columns and full bids/asks JSON
- Background writer thread (`queue.Queue` for async→sync bridge)
- Sample rate throttling per symbol (default 1s)
- WAL mode for concurrent read performance
- Batch flush every 5 seconds

### [MODIFIED] `nexus2/domain/market_data/l2_types.py`
Fixed parser to match verified schwab-py field names:
- Bid levels: `BID_PRICE`, `TOTAL_VOLUME`, `NUM_BIDS`, `BIDS` (per-exchange)
- Ask levels: `ASK_PRICE`, `TOTAL_VOLUME`, `NUM_ASKS`, `ASKS` (per-exchange)
- Per-exchange: `EXCHANGE`, `BID_VOLUME`/`ASK_VOLUME`, `SEQUENCE`
- Split `_parse_price_levels` into `_parse_bid_levels` and `_parse_ask_levels`
- Added `_parse_exchange_entries` for dict-based per-exchange data

### [MODIFIED] `nexus2/config.py`
Added:
- `L2_ENABLED` (default `false`)
- `L2_MAX_SYMBOLS` (default `5`)
- `L2_SAMPLE_RATE_SECONDS` (default `1`)

---

## Token Bridge Design Decision

The handoff identified two options for bridging token formats:
- (a) Write a converter that creates a schwab-py compatible temp file
- (b) Use `client_from_access_functions` instead

**Chose option (b)** — `client_from_access_functions` with custom read/write functions. This is cleaner because:
1. No temp file management
2. Token refreshes automatically written back in Nexus format
3. Both `schwab_adapter.py` (REST) and `schwab_l2_streamer.py` (streaming) share the same token file
4. schwab-py's `TokenMetadata` handles age tracking and wrapped writes

---

## Testable Claims

| # | Claim | File:Line | Verification |
|---|-------|-----------|-------------|
| 1 | `l2_types` module imports cleanly | `l2_types.py` | `python -c "from nexus2.domain.market_data.l2_types import parse_schwab_book_message"` |
| 2 | `l2_recorder` module imports cleanly | `l2_recorder.py` | `python -c "from nexus2.domain.market_data.l2_recorder import L2Recorder"` |
| 3 | `schwab_l2_streamer` module imports cleanly | `schwab_l2_streamer.py` | `python -c "from nexus2.adapters.market_data.schwab_l2_streamer import SchwabL2Streamer"` |
| 4 | Config defaults: `L2_ENABLED=False`, `L2_MAX_SYMBOLS=5`, `L2_SAMPLE_RATE_SECONDS=1` | `config.py:69-71` | `python -c "from nexus2 import config; print(config.L2_ENABLED, config.L2_MAX_SYMBOLS, config.L2_SAMPLE_RATE_SECONDS)"` |
| 5 | Parser uses `BID_PRICE` not `PRICE` for bid levels | `l2_types.py:_parse_bid_levels` | `Select-String -Path nexus2\domain\market_data\l2_types.py -Pattern "BID_PRICE"` |
| 6 | Parser uses `ASK_PRICE` not `PRICE` for ask levels | `l2_types.py:_parse_ask_levels` | `Select-String -Path nexus2\domain\market_data\l2_types.py -Pattern "ASK_PRICE"` |
| 7 | Old `_parse_price_levels` function is removed | `l2_types.py` | `Select-String -Path nexus2\domain\market_data\l2_types.py -Pattern "_parse_price_levels"` should return 0 results |
| 8 | Streamer uses `client_from_access_functions` | `schwab_l2_streamer.py:_create_client` | `Select-String -Path nexus2\adapters\market_data\schwab_l2_streamer.py -Pattern "client_from_access_functions"` |
| 9 | Recorder creates `l2_snapshots` table with `bids_json` and `asks_json` columns | `l2_recorder.py:CREATE_TABLE_SQL` | `Select-String -Path nexus2\domain\market_data\l2_recorder.py -Pattern "bids_json"` |
| 10 | No existing production files modified except `config.py` | N/A | Verify no changes to `schwab_adapter.py`, `warrior_engine.py`, etc. |
| 11 | `schwab_adapter.py` is untouched | `schwab_adapter.py` | git diff shows no changes |

---

## Not Implemented (Phase 2 — per handoff)
- Integration with `warrior_engine.py` start/stop lifecycle
- Scanner watchlist → L2 subscription updates
- Dynamic subscription manager
- L2 signal detection (wall detection, thin ask)
