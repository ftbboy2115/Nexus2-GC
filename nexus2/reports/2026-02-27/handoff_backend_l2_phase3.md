# Handoff: Backend Specialist — L2 Phase 3 (Signal Module)

## Task
Create the L2 signal detection module that analyzes order book snapshots to identify trading-relevant patterns (walls, thin asks, spread quality).

## Dependencies (from Phase 1-2)
- `nexus2/domain/market_data/l2_types.py` — `L2BookSnapshot`, `L2PriceLevel`
- `nexus2/adapters/market_data/schwab_l2_streamer.py` — `get_snapshot(symbol)` returns latest book
- Real data exists: `data/l2/2026-02-27.db` with 970 rows across 5 symbols (ALBT, ALOY, BATL, CD, EDSA)

## Important: Search Path
Use `C:\Dev\Nexus` for search tools.

---

## [NEW] `nexus2/domain/market_data/l2_signals.py`

Pure functions that take an `L2BookSnapshot` and return signal results. No side effects, no state — just analysis.

### Functions to Implement

#### 1. `detect_bid_wall(book: L2BookSnapshot, threshold_volume: int = 10_000) -> Optional[WallSignal]`
A bid wall is a single bid level with unusually large volume, suggesting strong support.
- Scan bid levels for any with `total_volume >= threshold_volume`
- Return `WallSignal(price, volume, side="bid")` for the largest wall found, or `None`

#### 2. `detect_ask_wall(book: L2BookSnapshot, threshold_volume: int = 10_000) -> Optional[WallSignal]`
Same logic for ask side — large ask volume suggests resistance.

#### 3. `detect_thin_ask(book: L2BookSnapshot, price_range_pct: float = 0.5, min_levels: int = 3) -> Optional[ThinAskSignal]`
Thin ask = very little resistance above current price — stock can move up easily.
- Look at ask levels within `price_range_pct` of best ask
- If < `min_levels` levels or total volume is low relative to bid volume
- Return `ThinAskSignal(levels_count, total_volume, price_range)` or `None`

#### 4. `get_spread_quality(book: L2BookSnapshot) -> SpreadQuality`
Assess overall book quality for trading:
- `spread`: bid-ask spread in dollars
- `spread_bps`: spread in basis points
- `bid_depth`: total bid volume across all levels
- `ask_depth`: total ask volume across all levels
- `imbalance`: (bid_depth - ask_depth) / (bid_depth + ask_depth) — positive = more buyers
- `quality`: "tight" / "normal" / "wide" based on spread_bps thresholds

#### 5. `get_book_summary(book: L2BookSnapshot) -> L2Summary`
One-call summary combining all signals:
- Best bid/ask/spread
- Wall signals (bid and ask)
- Thin ask signal
- Spread quality
- Useful for logging and dashboard display

### Data Classes

```python
@dataclass
class WallSignal:
    price: Decimal
    volume: int
    side: str  # "bid" or "ask"
    
@dataclass
class ThinAskSignal:
    levels_count: int
    total_volume: int
    price_range: Decimal
    
@dataclass
class SpreadQuality:
    spread: Decimal
    spread_bps: float
    bid_depth: int
    ask_depth: int
    imbalance: float
    quality: str  # "tight", "normal", "wide"

@dataclass
class L2Summary:
    symbol: str
    timestamp: datetime
    best_bid: Optional[Decimal]
    best_ask: Optional[Decimal]
    spread: Optional[Decimal]
    bid_wall: Optional[WallSignal]
    ask_wall: Optional[WallSignal]
    thin_ask: Optional[ThinAskSignal]
    spread_quality: SpreadQuality
```

### Design Notes
- All threshold values should be params with sensible defaults — we'll tune after seeing real market-hours data
- Functions should handle empty books gracefully (return `None` or default values)
- All functions are pure — no imports of config, no side effects
- Use `L2BookSnapshot` properties (`best_bid`, `best_ask`, `spread`) where available

---

## Constraints
- **No engine integration yet** — signals are standalone functions, not wired into entry decisions
- **No config dependencies** — thresholds are function params, not config values
- **Implementation only, no tests** — Testing Specialist will validate independently

## Testable Claims (document in status report)
1. All signal functions import cleanly
2. `detect_bid_wall` returns `None` for empty book
3. `detect_bid_wall` returns `WallSignal` when volume exceeds threshold
4. `detect_ask_wall` works symmetrically
5. `detect_thin_ask` identifies thin asks correctly
6. `get_spread_quality` handles empty book
7. `get_spread_quality` classifies spreads as tight/normal/wide
8. `get_book_summary` aggregates all signals
