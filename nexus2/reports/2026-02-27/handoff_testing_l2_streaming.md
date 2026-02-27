# Handoff: Testing Specialist — L2 Streaming Validation

## Task
Independently validate the Backend Specialist's L2 streaming implementation (Phase 1). Verify all 11 claims below by running the exact commands and reporting PASS/FAIL with actual output.

## Context
- Backend status report: `nexus2/reports/2026-02-27/backend_status_l2_streaming.md`
- Files created: `schwab_l2_streamer.py`, `l2_recorder.py`
- Files modified: `l2_types.py`, `config.py`
- The backend specialist chose `client_from_access_functions` (option b) for the schwab-py token bridge

## Important: Search Path
Use `C:\Dev\Nexus` for `Select-String` and search tools (symlink to actual path with spaces).

---

## Claims to Verify

### Import Tests (Claims 1-3)

| # | Claim | Command |
|---|-------|---------|
| 1 | `l2_types` imports cleanly | `.venv\Scripts\python -c "from nexus2.domain.market_data.l2_types import parse_schwab_book_message; print('PASS')"` |
| 2 | `l2_recorder` imports cleanly | `.venv\Scripts\python -c "from nexus2.domain.market_data.l2_recorder import L2Recorder; print('PASS')"` |
| 3 | `schwab_l2_streamer` imports cleanly | `.venv\Scripts\python -c "from nexus2.adapters.market_data.schwab_l2_streamer import SchwabL2Streamer; print('PASS')"` |

### Config Tests (Claim 4)

| # | Claim | Command |
|---|-------|---------|
| 4 | Config defaults: `L2_ENABLED=False`, `L2_MAX_SYMBOLS=5`, `L2_SAMPLE_RATE_SECONDS=1` | `.venv\Scripts\python -c "from nexus2 import config; print(config.L2_ENABLED, config.L2_MAX_SYMBOLS, config.L2_SAMPLE_RATE_SECONDS)"` |

### Parser Verification (Claims 5-7)

| # | Claim | Command |
|---|-------|---------|
| 5 | Parser uses `BID_PRICE` for bid levels | `Select-String -Path C:\Dev\Nexus\nexus2\domain\market_data\l2_types.py -Pattern "BID_PRICE"` |
| 6 | Parser uses `ASK_PRICE` for ask levels | `Select-String -Path C:\Dev\Nexus\nexus2\domain\market_data\l2_types.py -Pattern "ASK_PRICE"` |
| 7 | Old `_parse_price_levels` is removed | `Select-String -Path C:\Dev\Nexus\nexus2\domain\market_data\l2_types.py -Pattern "_parse_price_levels"` — should return 0 results |

### Architecture Verification (Claims 8-9)

| # | Claim | Command |
|---|-------|---------|
| 8 | Streamer uses `client_from_access_functions` | `Select-String -Path C:\Dev\Nexus\nexus2\adapters\market_data\schwab_l2_streamer.py -Pattern "client_from_access_functions"` |
| 9 | Recorder table has `bids_json` and `asks_json` columns | `Select-String -Path C:\Dev\Nexus\nexus2\domain\market_data\l2_recorder.py -Pattern "bids_json"` |

### No-Collateral-Damage Tests (Claims 10-11)

| # | Claim | Command |
|---|-------|---------|
| 10 | No existing production files modified except `config.py` | `git diff --name-only HEAD` — should only show `config.py` as modified (plus new untracked files) |
| 11 | `schwab_adapter.py` is untouched | `git diff nexus2/adapters/market_data/schwab_adapter.py` — should return empty |

---

## Additional Functional Tests to Write

Beyond the claim verification, write and run these unit tests:

### `nexus2/tests/unit/test_l2_types.py`
- Parse a mock schwab-py book message into `L2BookSnapshot`
- Verify bids sorted highest-price-first
- Verify asks sorted lowest-price-first
- Verify `best_bid`, `best_ask`, `spread` computed properties
- Verify `bid_ask_ratio` calculation
- Verify empty book returns `None` for optional properties

### `nexus2/tests/unit/test_l2_recorder.py`
- Create `L2Recorder` with temp directory
- Call `record()` with mock snapshot
- Verify SQLite DB is created with correct schema
- Verify rows written after flush
- Verify daily file naming pattern

---

## Validation Report Format

```markdown
## Validation Report: L2 Streaming Phase 1

### Claims Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | [claim] | PASS/FAIL | [command + output] |

### Unit Tests
| Test File | Tests Run | Passed | Failed |
|-----------|-----------|--------|--------|
| test_l2_types.py | X | X | X |
| test_l2_recorder.py | X | X | X |

### Overall Rating
- **HIGH**: All claims verified, tests pass
- **MEDIUM**: Minor issues
- **LOW**: Major issues (requires rework)
```
