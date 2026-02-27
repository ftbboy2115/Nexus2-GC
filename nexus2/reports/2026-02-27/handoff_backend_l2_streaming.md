# Handoff: L2 Streaming Backend Implementation

## Task
Implement Schwab Level 2 order book streaming for the Warrior bot. Phase 1 focuses on plumbing: streamer, recorder, and config.

## Plan Reference
Full plan: `plan_schwab_l2_streaming.md` (in coordinator's brain artifacts)
Research report: `nexus2/reports/2026-02-27/research_l2_data_availability.md`

---

## Verified Facts

**schwab-py 1.5.1 installed** — confirmed via pip output.

**StreamClient L2 API** (verified via `dir(s.StreamClient)`):
- `nasdaq_book_subs(symbols)` / `nasdaq_book_unsubs(symbols)` / `nasdaq_book_add(symbols)`
- `nyse_book_subs(symbols)` / `nyse_book_unsubs(symbols)` / `nyse_book_add(symbols)`
- `add_nasdaq_book_handler(handler)` / `add_nyse_book_handler(handler)`
- `BookFields`: `SYMBOL`, `BIDS`, `ASKS`, `BOOK_TIME`

**Client creation** (verified in `schwab/auth.py:389-416`):
```python
schwab.auth.client_from_token_file(token_path, api_key, app_secret, asyncio=True)
```
Creates auto-refreshing async client from token file.

**StreamClient creation** (verified in `schwab/streaming.py:101-137`):
```python
schwab.streaming.StreamClient(client, account_id=None)
```

**Existing config** (verified in `nexus2/config.py:56-57`):
```python
SCHWAB_CLIENT_ID = get_env("SCHWAB_CLIENT_ID")
SCHWAB_CLIENT_SECRET = get_env("SCHWAB_CLIENT_SECRET")
```

**Existing token file** at `data/schwab_tokens.json` — custom format:
```json
{"access_token": "...", "refresh_token": "...", "expiry": "...", "refresh_token_obtained": "..."}
```
schwab-py expects different format (`{"creation_timestamp": ..., "token": {...}}`). **Bridge needed.**

**l2_types.py already created** at `nexus2/domain/market_data/l2_types.py` by coordinator. Review and adjust as needed.

---

## Open Questions (Investigate Before Implementing)

1. **Token format bridge**: How exactly does schwab-py's `__token_loader` expect the JSON? Read `schwab/auth.py` lines 39-45 to confirm, then decide: (a) write a converter that creates a schwab-py compatible temp file, or (b) use `client_from_access_functions` instead.

2. **Account number**: `StreamClient` can optionally take `account_id`. Check if L2 streaming requires it. Try with `account_id=None` first. If needed, add `SCHWAB_ACCOUNT_NUMBER` to config.

3. **Concurrent symbol limit**: Unknown. Start with 5 as default, test during market hours to find the actual limit. Log errors clearly when subscription fails.

4. **Message format**: The exact shape of BIDS/ASKS sub-fields (PRICE, TOTAL_VOLUME, NUM_ENTRIES, DATA_LIST) needs verification from actual messages. The parser in `l2_types.py` handles both relabeled and numeric key formats as a safety net.

---

## Files to Create/Modify

### [NEW] `nexus2/adapters/market_data/schwab_l2_streamer.py`
Core async streaming service. Key responsibilities:
- Create schwab-py client from existing tokens (bridge format)
- Create StreamClient, log in to WebSocket
- Subscribe/unsubscribe to `nasdaq_book` + `nyse_book` for given symbols
- Cache latest `L2BookSnapshot` per symbol
- Emit callbacks on updates (for recorder and future signals)
- Handle reconnects and auth refresh
- Track `_subscribed_symbols: Set[str]`
- `is_connected` property

### [NEW] `nexus2/domain/market_data/l2_recorder.py`
SQLite recorder:
- Daily file rotation: `data/l2/YYYY-MM-DD.db`
- Table: `l2_snapshots(id, timestamp, symbol, side, price, volume, num_entries, exchange_data)`
- Batch writes via background thread (SQLite is sync, streaming is async)
- `queue.Queue` for async→sync bridge
- Flush every 5 seconds

### [MODIFY] `nexus2/config.py`
Add:
```python
L2_ENABLED = get_env("L2_ENABLED", "false").lower() == "true"
L2_MAX_SYMBOLS = int(get_env("L2_MAX_SYMBOLS", "5"))
L2_SAMPLE_RATE_SECONDS = int(get_env("L2_SAMPLE_RATE_SECONDS", "1"))
```

### [REVIEW] `nexus2/domain/market_data/l2_types.py`
Already created by coordinator. Review the `parse_schwab_book_message` function — it handles both relabeled and numeric field names but needs verification against actual Schwab messages.

> [!NOTE]
> **Testing will be handled by a separate Testing Specialist** after this implementation is complete. Do NOT write tests — focus on implementation only. Document any testable claims in your completion report so the Testing Specialist knows what to verify.

---

## Integration Points (Phase 2 — not this handoff)
- Wire into `warrior_engine.py` start/stop lifecycle
- Update L2 subscriptions from scanner watchlist in `_run_scan()`
- Build subscription manager for dynamic rotation

---

## Constraints
- **Feature flag**: Everything behind `L2_ENABLED` (default False)
- **No existing code changes** except `config.py` — all new files
- **Don't touch** `schwab_adapter.py` — the REST adapter stays as-is
- **Windows environment** — use PowerShell syntax
- **Search paths**: Use `C:\Dev\Nexus` for grep/search tools
