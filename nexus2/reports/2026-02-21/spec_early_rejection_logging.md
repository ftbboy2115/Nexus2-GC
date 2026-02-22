# Technical Spec: Early Rejection Logging

**Date:** 2026-02-21
**Author:** Backend Planner
**For:** Backend Specialist (implementation)
**Request:** Coordinator handoff — `handoff_backend_planner_early_rejection_logging.md`

---

## Summary

The Warrior entry trigger flow has 7 decision points in `check_entry_triggers()` where a "no entry" outcome is reached. Of these, only **1** currently logs to any queryable store (the guard block at line 602+ → `enter_position()` → `check_entry_guards()`). The remaining 6 decision points are either completely silent or emit `logger.info` only — invisible in Data Explorer.

This spec enumerates every "no entry" decision point, categorizes them by analytical value, and proposes a lightweight event type with throttling.

---

## A. Decision Point Inventory

All paths through `check_entry_triggers()` that result in "no entry":

| # | Decision Point | File / Line | Current Logging | Category |
|---|----------------|-------------|-----------------|----------|
| 1 | No quote getter | `warrior_engine_entry.py:347-348` | `return` — silent | LOW |
| 2 | No price returned | `warrior_engine_entry.py:353-354` | `continue` — silent | LOW |
| 3 | Extended stock routed to micro-pullback, but no trigger | `warrior_engine_entry.py:410-419` | `logger.info` when routed; silent when `_check_micro_pullback_pattern` returns None | MEDIUM |
| 4 | Below PMH — no DFL/whole-half/HOD pattern triggered | `warrior_engine_entry.py:516-542` | Each pattern fn returns `None` silently; only `logger.debug` if added | LOW |
| 5 | Above PMH — no PMH break/ORB/pullback/bull-flag/IHS/cup-handle pattern triggered | `warrior_engine_entry.py:544-585` | Each pattern fn returns `None` silently | LOW |
| 6 | VWAP break pattern not triggered | `warrior_engine_entry.py:593-594` | Pattern fn returns `None` silently | LOW |
| 7 | **Candidates exist but best score < MIN_SCORE_THRESHOLD (0.40)** | `warrior_engine_entry.py:613-617` | `logger.info` only — **NO DB write** | **HIGH** |

Additionally, within `check_micro_pullback_entry()` (lines 689-832), there are 5 internal rejection paths:
- Not enough candles (line 724): `logger.info`
- MACD/volume error (line 750): `logger.info`
- MACD too negative (line 759-762): `logger.info`
- Volume not confirming (line 776-783): `logger.info`
- Pullback too deep (lines 825-829): `logger.info`

None of these write to DB.

---

## B. Categorization: What's Worth Logging?

### HIGH Value — Must log to DB

| # | Decision Point | Why It Matters |
|---|----------------|----------------|
| **7** | Below-score rejection | This is the **closest to a trade** the engine gets without entering. A pattern triggered, was scored, but didn't meet quality bar. This is the #1 analytics gap — knowing HOW CLOSE the engine was to entering is crucial for tuning `MIN_SCORE_THRESHOLD` and pattern confidence weights. |

### MEDIUM Value — Should log to DB (with throttling)

| # | Decision Point | Why It Matters |
|---|----------------|----------------|
| **3** | Extended micro-pullback: no trigger | Extended stocks are rare and high-value. Knowing when the engine watched but didn't enter helps evaluate the micro-pullback criteria. Volume is very low (~1-3 per sym per day). |

### LOW Value — NOT recommended for DB (too noisy)

| # | Decision Point | Why It's Noise |
|---|----------------|----------------|
| 1 | No quote getter | Infrastructure state, not a trading decision |
| 2 | No price | Data availability issue |
| 4,5,6 | No pattern triggered | This fires **every cycle** for **every symbol** on the watchlist. In a BATL sim (960 bars × 4 symbols = ~3840 cycles), this would generate ~3500+ "no pattern" events per symbol. Pure noise. |

---

## C. Proposed Schema

### New Event Type

```python
# In TradeEventService class (trade_event_service.py:78)
WARRIOR_TRIGGER_REJECTION = "TRIGGER_REJECTION"  # Pattern scored but below threshold
```

**Rationale:** Do NOT reuse `GUARD_BLOCK`. Guard blocks happen AFTER `enter_position()` is called (score already passed threshold). `TRIGGER_REJECTION` happens BEFORE `enter_position()` — it's a fundamentally different stage in the pipeline.

### New Logging Function

```
log_warrior_trigger_rejection(
    symbol: str,
    best_pattern: str,        # e.g., "PMH_BREAK"
    best_score: float,        # e.g., 0.35
    threshold: float,         # MIN_SCORE_THRESHOLD (currently 0.40)
    candidate_count: int,     # how many patterns triggered
    price: float,             # current price at rejection time
    all_candidates: dict,     # {pattern_name: score} for all candidates
)
```

### Metadata Structure

```json
{
    "best_pattern": "PMH_BREAK",
    "best_score": 0.35,
    "threshold": 0.40,
    "gap_to_threshold": 0.05,
    "candidate_count": 2,
    "price": 4.85,
    "all_candidates": {
        "PMH_BREAK": 0.35,
        "ABCD": 0.28
    }
}
```

### For Medium-Value: Extended Micro-Pullback Skip

Reuse `TRIGGER_REJECTION` with a different `best_pattern` value:

```json
{
    "best_pattern": "MICRO_PULLBACK_SKIP",
    "best_score": 0.0,
    "threshold": 0.0,
    "candidate_count": 0,
    "price": 8.50,
    "reason": "MACD too negative (-0.0234 < -0.02)"
}
```

---

## D. Volume Estimate

### Below-Score Rejection (HIGH priority)

**Per-sim-run estimate:**
- BATL test case: ~960 bars × ~4 symbols on watchlist
- A pattern _triggers_ (non-None return) roughly 5-15% of cycles (only when price is near a level, breaking PMH, etc.)
- Of those, ~30-60% may be below threshold (the rest either enter or hit guards)
- **Estimated: 50-200 events per sim run**

This is **well within acceptable range** for DB writes. No throttling needed.

### Micro-Pullback Skip (MEDIUM priority)

- Extended stocks are rare (>100% gap). Maybe 0-1 per day.
- When present, micro-pullback checks fire every cycle (~960 times for that symbol).
- Internal skips (MACD neg, volume not confirming, etc.) might fire 20-50 times per sim.
- **Estimated: 0-50 events per sim run** (only when extended stock is on watchlist)

**Recommendation:** Throttle per symbol — log first occurrence of each rejection reason, then suppress until the reason changes.

### No-Pattern Events (LOW priority — NOT recommended)

- ~3000-4000 per symbol per sim run
- **Way too noisy for DB.** These should remain as `logger.debug` at most.

---

## E. Implementation Sketch

### Change Surface

| # | File | Change | Location | Template |
|---|------|--------|----------|----------|
| 1 | `trade_event_service.py` | Add `WARRIOR_TRIGGER_REJECTION` constant | Line 78 (after `WARRIOR_GUARD_BLOCK`) | Follow `WARRIOR_GUARD_BLOCK` pattern |
| 2 | `trade_event_service.py` | Add `log_warrior_trigger_rejection()` method | After `log_warrior_guard_block()` (~line 1030) | Model on `log_warrior_guard_block()` |
| 3 | `warrior_engine_entry.py` | Call `log_warrior_trigger_rejection()` at below-score rejection | Lines 613-617 | N/A — insert call |
| 4 | `warrior_engine_entry.py` *(optional)* | Log micro-pullback extended skip with throttle | Lines 416-419 | Throttle pattern |

### Change Point #1: New Event Type Constant

**File:** `nexus2/domain/automation/trade_event_service.py`
**Location:** Line 78 (after `WARRIOR_GUARD_BLOCK`)
**Current Code:**
```python
    WARRIOR_GUARD_BLOCK = "GUARD_BLOCK"  # Entry blocked by guard (position, macd, cooldown, etc.)
    WARRIOR_REENTRY_ENABLED = "REENTRY_ENABLED"  # Re-entry enabled after profit exit (Phase 11 C4)
```
**Approach:** Add `WARRIOR_TRIGGER_REJECTION = "TRIGGER_REJECTION"` between these two lines.

### Change Point #2: New Logging Method

**File:** `nexus2/domain/automation/trade_event_service.py`
**Location:** After `log_warrior_guard_block()` (after line 1029)
**Template:** `log_warrior_guard_block()` at lines 993-1029
**Approach:** Create `log_warrior_trigger_rejection()` that:
1. Writes to TML file (same as guard block)
2. Calls `_log_event()` with `position_id="TRIGGER_REJECTION"`, `event_type=self.WARRIOR_TRIGGER_REJECTION`
3. Includes all candidate scores in metadata

### Change Point #3: Call Site — Below-Score Rejection

**File:** `nexus2/domain/automation/warrior_engine_entry.py`
**Location:** Lines 613-617
**Current Code:**
```python
                else:
                    logger.info(
                        f"[Warrior Entry] {symbol}: Best candidate {winner.pattern.name} "
                        f"BELOW THRESHOLD ({winner.score:.3f} < {MIN_SCORE_THRESHOLD})"
                    )
```
**Approach:** Add import of `trade_event_service` and call `log_warrior_trigger_rejection()` after the `logger.info`:
```python
                else:
                    logger.info(
                        f"[Warrior Entry] {symbol}: Best candidate {winner.pattern.name} "
                        f"BELOW THRESHOLD ({winner.score:.3f} < {MIN_SCORE_THRESHOLD})"
                    )
                    tml.log_warrior_trigger_rejection(
                        symbol=symbol,
                        best_pattern=winner.pattern.name,
                        best_score=winner.score,
                        threshold=MIN_SCORE_THRESHOLD,
                        candidate_count=len(candidates),
                        price=float(current_price),
                        all_candidates={c.pattern.name: c.score for c in candidates},
                    )
```

**Import needed:** Add at top of `check_entry_triggers()` or module-level:
```python
from nexus2.domain.automation.trade_event_service import trade_event_service as tml
```

### Change Point #4 (Optional): Micro-Pullback Extended Skip

**File:** `nexus2/domain/automation/warrior_engine_entry.py`
**Location:** Lines 416-419 (inside extended stock routing)
**Approach:** After `_check_micro_pullback_pattern` returns None, log with throttling:
```python
                if micro_trigger:
                    await enter_position(engine, watched, current_price, micro_trigger)
                else:
                    # Log first skip per symbol (throttled)
                    if not getattr(watched, '_micro_skip_logged', False):
                        tml.log_warrior_trigger_rejection(
                            symbol=symbol,
                            best_pattern="MICRO_PULLBACK_SKIP",
                            best_score=0.0,
                            threshold=0.0,
                            candidate_count=0,
                            price=float(current_price),
                            all_candidates={},
                        )
                        watched._micro_skip_logged = True
                continue
```

**Note:** This is optional and lower priority than Change Point #3.

---

## F. Wiring Checklist

- [ ] Add `WARRIOR_TRIGGER_REJECTION` constant to `TradeEventService`
- [ ] Add `log_warrior_trigger_rejection()` method to `TradeEventService`
- [ ] Import `trade_event_service as tml` in `warrior_engine_entry.py`
- [ ] Call `tml.log_warrior_trigger_rejection()` at line ~617 (below-score rejection)
- [ ] (Optional) Add throttled micro-pullback skip logging at line ~419
- [ ] Verify events appear in Data Explorer → Trade Events tab
- [ ] Run batch sim (e.g., BATL) and confirm TRIGGER_REJECTION events are persisted
- [ ] Verify no performance regression in batch runs

---

## G. Risk Assessment

### Low Risk
- **DB volume:** 50-200 events per sim run is trivial. No indexing/performance concern.
- **No behavioral change:** Logging only — no changes to entry logic, scoring, or guards.
- **Pattern follows existing template:** `log_warrior_guard_block()` already does exactly this pattern.

### Watch For
- **Import circularity:** `warrior_engine_entry.py` already imports from `trade_event_service` indirectly via `check_entry_guards()`. Adding a direct import should be safe, but verify.
- **Sim clock timestamps:** Ensure `_get_event_timestamp()` returns sim time for these events (it should — it checks `is_sim_mode()` and falls back to wall clock).
- **Batch concurrency:** `trade_event_service` uses `ContextVar` for sim mode detection, which is safe for concurrent batch runs. No concern here.

### Not In Scope
- Logging "no pattern triggered" cycles (LOW value, too noisy)
- Changing existing `logger.info` calls (leave them for log-level debugging)
- Adding UI components to display trigger rejections (separate frontend task)

---

## H. Existing Pattern Analysis (Template)

The closest existing implementation to follow is `log_warrior_guard_block()`:

| Pattern | Function | File | Lines | Key Features |
|---------|----------|------|-------|--------------|
| Guard Block | `log_warrior_guard_block()` | `trade_event_service.py` | 993-1029 | TML file + DB write, `position_id="GUARD_BLOCK"`, metadata includes guard_name, trigger_type, price |

The new `log_warrior_trigger_rejection()` should mirror this exactly, with:
- `position_id="TRIGGER_REJECTION"` (not a real position)
- Same dual-write pattern (TML file + `_log_event()`)
- Richer metadata (all candidate scores, threshold gap)

---

## I. Live vs Sim Behavior

### Q1: Does the below-score rejection at lines 613-617 fire during live trading?

**Yes — identical code path.** `check_entry_triggers()` is a pure function of the `WarriorEngine` instance. It contains **zero** sim/live branching in the entry decision logic.

**Evidence:**

The only `sim_only` check in the entire function is at line 363-364:
```python
is_sim = getattr(engine.config, 'sim_only', False)
if not is_sim:
    # ... phantom quote sanity check (prevents inflated API quotes)
```
This is an **infrastructure guard** (validates quote data quality) — it has nothing to do with pattern scoring or entry decisions. The below-score rejection at lines 613-617 executes identically regardless of mode.

**Call sites (all invoke the same `check_entry_triggers()`):**

| Mode | Call Site | File / Line | Frequency |
|------|----------|-------------|-----------|
| **LIVE** | `_watch_loop()` → `_check_entry_triggers()` | `warrior_engine.py:628` | Every **5 seconds** during extended hours (4AM–8PM ET) |
| **Batch SIM** | `step_clock_ctx()` | `sim_context.py:139` | Every **bar step** (960 steps for full-day sim) |
| **Single SIM** | `step_clock()` | `warrior_sim_routes.py:1202` | Every **bar step** (API-controlled) |

### Q2: Expected volume of TRIGGER_REJECTION events in a live trading session

**Calculation:**

```
Trading window:     9:30 AM – 11:30 AM ET (2 hours)
Extended hours:     4:00 AM – 8:00 PM ET (16 hours)
Polling interval:   5 seconds
Watchlist size:     Typically 2-5 symbols (post-scan)

Cycles per hour:    720 (3600s / 5s)
Total cycles:       720 × 2h = 1,440   (trading window only)
                    720 × 16h = 11,520  (full extended hours)

Pattern trigger rate:  ~5-15% of cycles (pattern functions return non-None)
Below-threshold rate:  ~30-60% of triggered patterns

Per symbol, trading window:
  1,440 × 10% trigger × 40% below threshold ≈ 58 events

Per symbol, full day:
  11,520 × 10% × 40% ≈ 461 events
```

**Estimated live volume:** **50-500 TRIGGER_REJECTION events per symbol per day**

With a typical 3-symbol watchlist: **150-1,500 total events per live session**

This is manageable for the DB but warmer than sim (which runs 960 steps total, not 11,520). The difference is that live polling runs continuously at 5s intervals, while sim steps only when bars change.

### Q3: Should we gate this differently for live vs sim?

**Recommendation: No separate gating needed, but add per-symbol deduplication.**

The logging function should include a **dedup window** to prevent the same pattern/score from generating redundant events:

| Scenario | Without Dedup | With Dedup (30s window) |
|----------|---------------|-------------------------|
| SIM (960 steps) | 50-200 events | 50-200 events (no change — each step is a new bar) |
| LIVE (11,520 cycles) | 150-1,500 events | **30-100 events** (many cycles see same price/pattern) |

**Implementation:** Track `(symbol, pattern_name, score_bucket)` with a 30-second cooldown. In live mode, many consecutive 5-second polls will see the exact same price and produce the same rejection — deduplication collapses these.

```python
# In check_entry_triggers(), before calling log_warrior_trigger_rejection:
_last_rejection: Dict[str, float] = {}  # module-level: symbol → timestamp

# Dedup: skip if same symbol was rejected < 30s ago with same pattern
dedup_key = f"{symbol}_{winner.pattern.name}"
now = time.time()
if dedup_key not in _last_rejection or (now - _last_rejection[dedup_key]) > 30:
    tml.log_warrior_trigger_rejection(...)
    _last_rejection[dedup_key] = now
```

**Why NOT a config toggle:**
- Adding a `log_trigger_rejections_in_live` toggle would create another setting to document, test, and maintain.
- The dedup window handles the volume concern without any user-facing config.
- Guard blocks (`log_warrior_guard_block()`) have no sim/live toggle — they fire in both modes. Trigger rejections should be consistent.

### Summary

| Question | Answer |
|----------|--------|
| Same code path? | **Yes** — zero sim/live branching in entry logic |
| Fires in live? | **Yes** — every 5s poll cycle |
| Live volume? | **150-1,500 events/day** (without dedup) → **30-100 events/day** (with 30s dedup) |
| Separate gating? | **No** — use per-symbol dedup window (30s) instead of a config toggle |
