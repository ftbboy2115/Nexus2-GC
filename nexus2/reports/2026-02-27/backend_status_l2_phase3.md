# Backend Status: L2 Phase 3 — Signal Module

**Date:** 2026-02-27
**Agent:** Backend Specialist
**Status:** ✅ Complete

---

## Files Created

### [NEW] `nexus2/domain/market_data/l2_signals.py`

Pure signal detection module with 4 dataclasses and 5 functions:

| Item | Type | Purpose |
|------|------|---------|
| `WallSignal` | dataclass | Represents a wall (price, volume, side) |
| `ThinAskSignal` | dataclass | Thin ask resistance (levels_count, total_volume, price_range) |
| `SpreadQuality` | dataclass | Book quality (spread, spread_bps, bid/ask depth, imbalance, quality) |
| `L2Summary` | dataclass | Aggregated summary of all signals |
| `detect_bid_wall()` | function | Finds largest bid level exceeding threshold |
| `detect_ask_wall()` | function | Finds largest ask level exceeding threshold |
| `detect_thin_ask()` | function | Identifies thin resistance above best ask |
| `get_spread_quality()` | function | Classifies spread as tight/normal/wide |
| `get_book_summary()` | function | One-call aggregation of all signals |

---

## Design Decisions

- **All thresholds are function parameters** with sensible defaults — no config dependencies
- **Empty-book handling**: all functions return `None` or safe defaults (`SpreadQuality` with `quality="wide"`)
- **Wall detection returns the *largest* wall**, not just the first one found
- **Spread quality uses basis points** with configurable tight (≤10 bps) and wide (>50 bps) thresholds
- **Imbalance formula**: `(bid_depth - ask_depth) / (bid_depth + ask_depth)` — positive = more buyers

---

## Testable Claims

| # | Claim | Verification |
|---|-------|-------------|
| 1 | All signal functions import cleanly | `python -c "from nexus2.domain.market_data.l2_signals import detect_bid_wall, detect_ask_wall, detect_thin_ask, get_spread_quality, get_book_summary"` → no error |
| 2 | `detect_bid_wall` returns `None` for empty book | Create `L2BookSnapshot(symbol="X", timestamp=now, bids=[], asks=[])`, call `detect_bid_wall(book)` → `None` |
| 3 | `detect_bid_wall` returns `WallSignal` when volume ≥ threshold | Create book with bid level `total_volume=15000`, call with `threshold_volume=10000` → `WallSignal(price=..., volume=15000, side="bid")` |
| 4 | `detect_ask_wall` works symmetrically to bid wall | Same test with ask levels → `WallSignal(..., side="ask")` |
| 5 | `detect_thin_ask` identifies thin asks correctly | Book with 2 ask levels in range (< `min_levels=3`) → returns `ThinAskSignal` |
| 6 | `get_spread_quality` handles empty book | Empty book → `SpreadQuality(spread=0, spread_bps=0, quality="wide")` |
| 7 | `get_spread_quality` classifies tight/normal/wide | Spread ≤10 bps → "tight", 10-50 → "normal", >50 → "wide" |
| 8 | `get_book_summary` aggregates all signals | Returns `L2Summary` with all fields populated from individual functions |

**Verified:** Claim #1 passes — `python -c "from nexus2.domain.market_data.l2_signals import ..."` → `All imports OK`
