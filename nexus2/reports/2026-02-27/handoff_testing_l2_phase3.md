# Handoff: Testing Specialist — L2 Phase 3 Validation

## Task
Validate the L2 signal module and write comprehensive unit tests.

## Context
- Backend status: `nexus2/reports/2026-02-27/backend_status_l2_phase3.md`
- New file: `nexus2/domain/market_data/l2_signals.py`
- Dependencies: `nexus2/domain/market_data/l2_types.py` (L2BookSnapshot, L2PriceLevel)

## Important: Search Path
Use `C:\Dev\Nexus` for search tools.

---

## Claims to Verify (8 total)

| # | Claim | Verification |
|---|-------|-------------|
| 1 | All signal functions import cleanly | `.venv\Scripts\python -c "from nexus2.domain.market_data.l2_signals import detect_bid_wall, detect_ask_wall, detect_thin_ask, get_spread_quality, get_book_summary; print('PASS')"` |
| 2 | `detect_bid_wall` returns `None` for empty book | Unit test with empty bids/asks |
| 3 | `detect_bid_wall` returns `WallSignal` when volume ≥ threshold | Unit test with 15000 vol, threshold 10000 |
| 4 | `detect_ask_wall` works symmetrically | Same pattern as bid wall but for asks |
| 5 | `detect_thin_ask` identifies thin asks correctly | Book with 2 ask levels (< `min_levels=3`) → returns `ThinAskSignal` |
| 6 | `get_spread_quality` handles empty book | Empty book → `quality="wide"` |
| 7 | `get_spread_quality` classifies tight/normal/wide | ≤10 bps → tight, 10-50 → normal, >50 → wide |
| 8 | `get_book_summary` aggregates all signals | Returns `L2Summary` with all fields populated |

---

## Unit Tests to Write

### `nexus2/tests/unit/market_data/test_l2_signals.py`

**Wall Detection:**
- Empty book → None
- No level exceeds threshold → None
- One level exceeds threshold → returns WallSignal with that level
- Multiple levels exceed threshold → returns the *largest* wall
- Bid wall returns `side="bid"`, ask wall returns `side="ask"`

**Thin Ask:**
- Empty book → None
- Many ask levels → None (not thin)
- Few ask levels in range → ThinAskSignal
- Low total ask volume relative to bids → ThinAskSignal

**Spread Quality:**
- Empty book → quality="wide", spread=0
- Tight spread (≤10 bps) → quality="tight"
- Normal spread (10-50 bps) → quality="normal"
- Wide spread (>50 bps) → quality="wide"
- Imbalance calculation: more bids → positive, more asks → negative
- Equal bids/asks → imbalance ≈ 0

**Book Summary:**
- Aggregates all signal outputs into L2Summary
- Contains wall signals, thin ask, spread quality
- Works with empty book (all None/defaults)

**Also verify existing tests still pass:**
```powershell
.venv\Scripts\python -m pytest nexus2/tests/unit/market_data/ -v --timeout=30 -q
```

---

## Validation Report Format
Same as Phase 1/2 — claims table + test results + overall rating.
