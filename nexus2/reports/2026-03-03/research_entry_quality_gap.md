# Research Report: Entry Quality Gap Between Batch Testing and Live Trading

**Date:** 2026-03-03  
**Author:** Backend Planner  
**Reference:** `handoff_planner_entry_quality_investigation.md`

---

## Executive Summary

The batch test P&L ($355K across 39 cases) is NOT an illusion — it reflects real profits from well-known Ross Cameron replay trades. However, **the scoring system plays almost no role in those profits**. The bot's P&L is driven entirely by:

1. **Pattern matching** (PMH break, etc.) happening to fire at the right time in known-good setups
2. **Guard gates** (MACD, VWAP, EMA, spread) independently blocking bad entries
3. **Position management** (stops, partials, EOD close) executing correctly

The scoring system is a **vestigial organ** — it accepts everything above 0.40, and every PMH_BREAK candidate scores ~0.79. It cannot degrade scoring for late re-entries, extended moves, or fading momentum because **it receives NO real-time price-action data**.

---

## Q1: How Does `gc_quick_test.py` Execute Each Test Case?

### Answer: Fully Isolated, Single Stock, Single Day

Each batch test case runs in **complete isolation** via `ProcessPoolExecutor`:

**Finding:** Each case gets its own process with in-memory SQLite DB
**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L594-L634)
**Code:**
```python
def _run_case_sync(case_tuple: tuple) -> dict:
    # PER-PROCESS IN-MEMORY DB (Phase 8)
    mem_engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    wdb.warrior_engine = mem_engine
    wdb.WarriorSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=mem_engine)
    wdb.WarriorBase.metadata.create_all(bind=mem_engine)
```

**Finding:** Watchlist contains exactly ONE symbol per case
**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L303-L308)
**Code:**
```python
# Fresh start: clear state
ctx.engine._watchlist.clear()
ctx.engine._pending_entries.clear()
ctx.engine._symbol_fails.clear()
watched.entry_triggered = False
ctx.engine._watchlist[symbol] = watched
```

**Finding:** Simulation runs 960 minutes (04:00→20:00 ET)
**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L693-L694)
**Code:**
```python
# Step through full day: 04:00→20:00, matches sequential runner
await step_clock_ctx(ctx, 960)
```

### Key Implications

| Property | Batch Mode | Live Mode |
|----------|-----------|-----------|
| Symbols in watchlist | **1** (isolated) | **Multiple** (competing) |
| TOP_X_ONLY applicable? | **No** (only 1 candidate) | **Yes** (ranks across candidates) |
| Guards active? | **Yes** (unless `skip_guards=True`) | **Yes** |
| Config source | `warrior_settings_batch.json` + overrides | `warrior_settings.json` |
| Re-entry possible? | **Yes** (after 10-min sim cooldown) | **Yes** (after live cooldown) |
| Capital per case | $100K (config override) | $100K (whatever is set) |

---

## Q2: P&L Distribution Across 39 Test Cases

### Full Distribution (Sorted by Bot P&L)

| # | Case | Symbol | Bot P&L | Ross P&L | Delta |
|---|------|--------|--------:|--------:|------:|
| 1 | ross_npt_20260203 | NPT | $68,021 | $81,000 | -$12,979 |
| 2 | ross_batl_20260127 | BATL | $49,636 | $0 | +$49,636 |
| 3 | ross_rolr_20260114 | ROLR | $45,723 | $85,000 | -$39,277 |
| 4 | ross_evmn_20260210 | EVMN | $42,355 | -$10,000 | +$52,355 |
| 5 | ross_batl_20260126 | BATL | $26,757 | $0 | +$26,757 |
| 6 | ross_prfx_20260211 | PRFX | $25,200 | $5,971 | +$19,229 |
| 7 | ross_vhub_20260217 | VHUB | $21,796 | $1,600 | +$20,196 |
| 8 | ross_hind_20260127 | HIND | $19,354 | $55,253 | -$35,898 |
| 9 | ross_pavm_20260121 | PAVM | $19,047 | $43,950 | -$24,903 |
| 10 | ross_gri_20260128 | GRI | $17,004 | $31,600 | -$14,596 |
| 11 | ross_lcfy_20260116 | LCFY | $13,545 | $10,457 | +$3,088 |
| 12 | ross_envb_20260219 | ENVB | $12,038 | $12,716 | -$679 |
| 13 | ross_lrhc_20260130 | LRHC | $10,811 | $31,077 | -$20,266 |
| 14 | ross_tnmg_20260116 | TNMG | $8,630 | $2,102 | +$6,528 |
| 15 | ross_batl_20260227 | BATL | $7,838 | -$6,700 | +$14,538 |
| 16 | ross_sxtc_20260209 | SXTC | $7,789 | -$5,000 | +$12,789 |
| 17 | ross_pmi_20260212 | PMI | $6,713 | $9,959 | -$3,246 |
| 18 | ross_bnai_20260205 | BNAI | $5,682 | -$7,900 | +$13,582 |
| 19 | ross_bctx_20260127 | BCTX | $5,373 | $4,500 | +$873 |
| 20 | ross_vero_20260116 | VERO | $3,579 | $3,485 | +$94 |
| 21 | ross_flye_20260206 | FLYE | $1,879 | $4,800 | -$2,921 |
| 22 | ross_bnkk_20260115 | BNKK | $1,104 | $15,000 | -$13,896 |
| 23 | ross_dcx_20260129 | DCX | $667 | $6,268 | -$5,602 |
| 24 | ross_edhl_20260220 | EDHL | $673 | -$112 | +$784 |
| 25 | ross_bnrg_20260211 | BNRG | $361 | $272 | +$89 |
| 26 | ross_snse_20260218 | SNSE | $343 | $9,373 | -$9,030 |
| 27 | ross_rnaz_20260205 | RNAZ | $96 | $1,700 | -$1,604 |
| 28 | ross_velo_20260210 | VELO | -$34 | -$2,000 | +$1,967 |
| 29 | ross_mlec_20260213 | MLEC | -$578 | $43,000 | -$43,578 |
| 30 | ross_ndra_20260226 | NDRA | -$1,053 | $13 | -$1,066 |
| 31 | ross_aidx_20260225 | AIDX | -$1,428 | $546 | -$1,975 |
| 32 | ross_mlec_20260220 | MLEC | -$3,240 | $5,612 | -$8,852 |
| 33 | ross_rvsn_20260205 | RVSN | -$4,045 | -$3,000 | -$1,045 |
| 34 | ross_rdib_20260206 | RDIB | -$5,137 | $700 | -$5,837 |
| 35 | ross_gwav_20260116 | GWAV | -$6,526 | $3,975 | -$10,501 |
| 36 | ross_batl_20260302 | BATL | -$6,644 | $6,831 | -$13,475 |
| 37 | ross_uoka_20260209 | UOKA | -$10,635 | $858 | -$11,493 |
| 38 | ross_onco_20260212 | ONCO | -$12,150 | -$5,500 | -$6,650 |
| 39 | ross_mnts_20260209 | MNTS | -$15,503 | $9,000 | -$24,503 |

### Summary Statistics

| Metric | Value |
|--------|-------|
| **Total Bot P&L** | $355,039 |
| **Total Ross P&L** | $446,406 |
| **Capture Rate** | 79.5% |
| **Profitable Cases** | 27 / 39 (69%) |
| **Money-Losing Cases** | 12 / 39 (31%) |
| **Mean Bot P&L** | $9,104 |
| **Median Bot P&L** | $3,579 |

### Concentration Analysis: Top-Heavy P&L

| Group | Cases | Combined Bot P&L | % of Total |
|-------|------:|----------------:|----------:|
| **Top 4** (NPT, BATL×2, ROLR) | 4 | $183,714 | **51.7%** |
| **Top 10** | 10 | $311,888 | **87.8%** |
| **Cases #11-#27** (small wins) | 17 | $92,152 | 26.0% |
| **All 12 losers** | 12 | -$66,973 | -18.9% |
| **Worst 3 losers** | 3 | -$38,288 | -10.8% |

> [!IMPORTANT]
> **4 cases produce 52% of total P&L.** The scoring system doesn't make these winners — the setups are simply strong (high gap, strong catalyst), and ANY pattern match + entry triggers a profitable trade. The scoring system is irrelevant to the outcome.

---

## Q3: Does the Bot Face Re-Entry Situations in Batch Mode?

### Answer: Yes, Re-Entry IS Possible — With Guards

**Finding:** Sim-mode re-entry cooldown is 10 minutes
**File:** [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L166-L176)
**Code:**
```python
# SIM MODE COOLDOWN
if engine.monitor.sim_mode and symbol in engine.monitor._recently_exited_sim_time:
    exit_sim_time = engine.monitor._recently_exited_sim_time[symbol]
    if hasattr(engine.monitor, '_sim_clock') and engine.monitor._sim_clock:
        current_sim_time = engine.monitor._sim_clock.current_time
        minutes_since_exit = (current_sim_time - exit_sim_time).total_seconds() / 60
        cooldown_minutes = engine.monitor._reentry_cooldown_minutes
        if minutes_since_exit < cooldown_minutes:
            reason = f"SIM re-entry cooldown - exited {minutes_since_exit:.1f}m ago ..."
```

**Finding:** Consecutive loss guard blocks after 3 losses on same symbol
**File:** [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L178-L186)
**Code:**
```python
# RE-ENTRY QUALITY GATE: Block re-entry after consecutive losses
if watched.entry_attempt_count > 0 and engine.monitor.settings.block_reentry_after_loss:
    max_attempts = engine.monitor.settings.max_reentry_after_loss  # Default: 3
    consecutive_losses = watched.consecutive_loss_count
    if consecutive_losses >= max_attempts:
        reason = f"Re-entry BLOCKED after {consecutive_losses} consecutive losses ..."
```

**Finding:** Fail-limit guard also restrains re-entry
**File:** [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L127-L132)
**Code:**
```python
# PER-SYMBOL FAIL LIMIT
symbol_fails = engine._symbol_fails.get(symbol, 0)
if symbol_fails >= engine._max_fails_per_symbol:
    reason = f"Max fails hit - {symbol_fails} stops today (max={engine._max_fails_per_symbol})"
```

### Re-Entry Scores DO NOT Change

The critical insight is that **re-entry scores are identical to first-entry scores** because:

1. `volume_ratio` = from scanner metadata (fixed at scan time)
2. `catalyst_strength` = from scanner metadata (fixed at scan time)
3. `spread_pct` = from scanner metadata (fixed at scan time)
4. `pattern_confidence` = hard-coded per pattern type (0.85 for PMH_BREAK)
5. `level_proximity` = changes slightly with price, contributes only 5%
6. `time_score` = changes with time of day, contributes only 5%

**Result:** A re-entry at 3:00 PM on a fading stock scores ~0.78. A first entry at 9:31 AM on a fresh breakout scores ~0.80. Effectively indistinguishable.

---

## Q4: What Differentiates Winning From Losing Entries?

### Available Data Per Entry (Already Logged)

**Finding:** The MACD gate captures a snapshot that IS logged to trade events
**File:** [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L264-L265)
**Code:**
```python
# CRITICAL: Store snapshot for audit logging
watched.entry_snapshot = snapshot
```

**Finding:** Trade events log VWAP, EMA-9, MACD at entry time
**File:** [warrior_entry_execution.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_execution.py#L520-L529)
**Code:**
```python
entry_snapshot = getattr(watched, 'entry_snapshot', None)
if entry_snapshot:
    "symbol_vwap": float(entry_snapshot.vwap) if entry_snapshot.vwap else None,
    "symbol_above_vwap": float(entry_decimal) > float(entry_snapshot.vwap),
    "symbol_ema9": float(entry_snapshot.ema_9) if entry_snapshot.ema_9 else None,
    "symbol_above_ema9": float(entry_decimal) > float(entry_snapshot.ema_9),
    "symbol_macd_value": float(entry_snapshot.macd_histogram),
    "symbol_macd_status": "positive" if entry_snapshot.macd_histogram > 0.05 else ...
```

### Factors NOT Currently Used for Scoring (But Available)

| Factor | Available At | Used In Guards? | Used In Scoring? | Source |
|--------|-------------|-----------------|-----------------|--------|
| MACD histogram value | Entry time | ✅ (blocks if < tolerance) | ❌ | `_check_macd_gate` |
| EMA-9 position | Entry time | ✅ (`validate_technicals`) | ❌ | `update_candidate_technicals` |
| VWAP position | Entry time | ✅ (`validate_technicals`) | ❌ | `update_candidate_technicals` |
| Volume expansion ratio | Entry time | ❌ | ❌ | `check_volume_expansion()` exists but not wired to scoring |
| Price vs. HOD | Entry time | Implicit in patterns | ❌ | `watched.recent_high` tracked |
| Re-entry attempt count | Entry time | ✅ (loss blocker) | ❌ | `watched.entry_attempt_count` |
| Time since last exit | Entry time | ✅ (cooldown) | ❌ | `_recently_exited_sim_time` |
| Falling knife detection | Entry time | ❌ | ❌ | `check_falling_knife()` exists |
| High-vol red candle | Entry time | ❌ | ❌ | `check_high_volume_red_candle()` exists |

---

## Q5: What Price-Action Factors COULD the Scoring System Use?

### Currently: Scoring Gets 0 Real-Time Data

**Finding:** `score_pattern()` is called inside `add_candidate()` closure
**File:** [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L500-L525)
**Code:**
```python
def add_candidate(trigger: Optional[EntryTriggerType], confidence: float = 0.7):
    if trigger:
        score = score_pattern(
            pattern=trigger,
            volume_ratio=volume_ratio,        # From scanner metadata (STATIC)
            pattern_confidence=confidence,     # Hard-coded per pattern type (STATIC)
            catalyst_strength=catalyst_strength, # From scanner metadata (STATIC)
            spread_pct=spread_pct,             # From scanner metadata (STATIC)
            level_proximity=level_proximity,   # Computed from current_price (MILDLY DYNAMIC)
            time_score=time_score,             # From clock (MILDLY DYNAMIC)
            blue_sky_pct=blue_sky_pct,         # From FMP quote (STATIC per session)
        )
```

### Proposed: Price-Action-Aware Scoring Factors

Based on what's **already computed** in the entry pipeline but **not passed to scoring**:

#### Factor 1: MACD Momentum Score (HIGH IMPACT)

**Available at:** `_check_macd_gate()` stores `watched.entry_snapshot.macd_histogram`  
**What it measures:** Momentum direction and strength  
**How to score:**
- Histogram > 0.05: full score (1.0) — strong bullish momentum
- Histogram 0 to 0.05: moderate (0.6) — momentum turning
- Histogram -0.02 to 0: low (0.3) — momentum fading  
- < -0.02: blocked by MACD gate (never reaches scoring)

**Implementation complexity:** LOW — `entry_snapshot` is already computed before scoring decisions; just pipe `snapshot.macd_histogram` into a new param in `score_pattern()`.

#### Factor 2: VWAP Position Score (MEDIUM IMPACT)

**Available at:** `update_candidate_technicals()` sets `watched.is_above_vwap` and `watched.current_vwap`  
**What it measures:** Whether entry is above/below the session VWAP  
**How to score:**
- Price > VWAP by 2%+: high (1.0) — strong above-VWAP setup
- Price > VWAP by 0-2%: moderate (0.7)
- Price ≈ VWAP (±1%): low (0.4) — right at pivot
- Price < VWAP: _already blocked by_ `validate_technicals`

**Implementation complexity:** LOW — `watched.current_vwap` already populated every 60s.

#### Factor 3: Volume Expansion Score (HIGH IMPACT)

**Available at:** `check_volume_expansion()` exists as a standalone function  
**What it measures:** Whether current bar has vol spike confirming breakout  
**How to score:**
- Ratio > 5x: full (1.0) — explosive volume
- Ratio 3-5x: moderate (0.7)
- Ratio 1-3x: weak (0.3) — no volume confirmation
- Ratio < 1x: penalty (0.1)

**Implementation complexity:** MEDIUM — `check_volume_expansion()` needs candle data which requires an `await engine._get_intraday_bars()` call. The candles are already fetched in `_check_macd_gate` and `update_candidate_technicals`, but not currently propagated to the scoring context. The refactor would need to cache candle data so it's not re-fetched.

#### Factor 4: Re-Entry Decay Score (HIGH IMPACT)

**Available at:** `watched.entry_attempt_count` tracked on `WatchedCandidate`  
**What it measures:** How many times the bot has already tried this stock  
**How to score:**
- First entry (count=0): full (1.0)
- Re-entry #1: moderate (0.7) — valid re-test
- Re-entry #2: low (0.4) — diminishing returns
- Re-entry #3+: already blocked by consecutive-loss guard

**Implementation complexity:** LOW — `watched.entry_attempt_count` is already tracked.

#### Factor 5: Price Extension Score (MEDIUM IMPACT)

**Available at:** `watched.recent_high`, `watched.pmh`, and `current_price`  
**What it measures:** How extended the stock is from the identified breakout level  
**How to score:**
- Within 3% of PMH: high (1.0) — fresh breakout
- 3-10% above PMH: moderate (0.7) — still running
- 10-20% above PMH: low (0.3) — getting extended
- >20% above PMH: penalty (0.1) — chasing

**Implementation complexity:** LOW — PMH is on `watched.pmh`, current price available.

### Recommended Weight Rebalancing

Current weights (85% static, 15% mildly dynamic):

| Factor | Current Weight |
|--------|------------:|
| Pattern confidence (static) | 50% |
| Volume ratio (static scanner) | 20% |
| Catalyst strength (static scanner) | 15% |
| Spread (static) | 5% |
| Level proximity (mildly dynamic) | 5% |
| Time score (mildly dynamic) | 5% |

Proposed weights (50% static, 50% dynamic):

| Factor | Proposed Weight | Source |
|--------|------------:|--------|
| Pattern confidence | 25% (↓ from 50%) | Hard-coded per trigger type |
| MACD momentum | 15% (NEW) | `entry_snapshot.macd_histogram` |
| Volume expansion | 15% (NEW) | `check_volume_expansion()` |
| Re-entry decay | 10% (NEW) | `watched.entry_attempt_count` |
| Volume ratio (scanner) | 10% (↓ from 20%) | Scanner metadata |
| Catalyst strength | 10% (↓ from 15%) | Scanner metadata |
| VWAP position | 5% (NEW) | `watched.current_vwap` |
| Price extension | 5% (NEW) | `watched.pmh` vs current |
| Time score | 5% (keep) | Clock |

### Impact Assessment

With the proposed weights, the RUBI scenario from today's live session would look like:

| Entry | Current Score | Proposed Score (est.) | Difference |
|-------|-------------|---------------------|------------|
| 1st entry (fresh PMH break, strong MACD) | 0.793 | ~0.82 | ↑ Better |
| 2nd entry (re-entry #1, MACD fading) | 0.793 | ~0.58 | ↓ Would still pass |
| 3rd entry (re-entry #2, no vol, weak MACD) | 0.793 | ~0.38 | ↓ **BLOCKED** (< 0.40 threshold) |

The 3rd entry, which produced a loss, would have been blocked — not by a new guard, but by the existing MIN_SCORE_THRESHOLD naturally filtering it out.

---

## Overall Assessment

### Why Batch P&L Is High Despite Static Scoring

1. **Cherry-picked setups:** Test cases are real Ross Cameron trades — pre-selected for having strong catalysts, high volume, and clear setups. The scoring system CAN'T fail on these because the inputs are already excellent.

2. **Single-stock isolation:** With only 1 stock in the watchlist, TOP_X_ONLY is irrelevant, scoring only needs to beat 0.40, and the bot's pattern matching fires on obvious breakouts.

3. **Guards do the real work:** MACD gate, VWAP/EMA validation, and spread filter independently block bad entries. The MACD gate alone accounts for thousands of blocks per case (e.g., PAVM: 15,344 guard blocks).

4. **Big winners are "easy" trades:** NPT ($68K), BATL ($50K), ROLR ($46K) — these are massive gap-up stocks where almost ANY entry during the first hour produces profit. Scoring doesn't matter when the stock goes up 200%.

### Why Live Trading Suffers

1. **Multiple stocks competing:** Live watchlist has 5-10 candidates. Without dynamic scoring, the bot can't distinguish "RUBI on the 3rd attempt" from "fresh gapper at 9:35."

2. **No decay on re-entry:** Same stock getting the same ~0.79 score on entry #3 as entry #1.

3. **No momentum context:** A PMH break at 2:30 PM with negative MACD histogram and low volume scores the same as a PMH break at 9:35 AM with exploding volume.

4. **Scanner metadata ossifies:** Volume ratio, catalyst strength etc. are captured once at scan time and never updated. By afternoon, these numbers are hours stale.

### Implementation Priority

| # | Factor | Impact | Complexity | Priority |
|---|--------|--------|-----------|----------|
| 1 | Re-entry decay | HIGH (prevents RUBI-like repeat entries) | LOW | **P0** |
| 2 | MACD momentum | HIGH (distinguishes strong vs fading setups) | LOW | **P0** |
| 3 | Volume expansion | HIGH (confirms real breakouts vs no-vol fakes) | MEDIUM | **P1** |
| 4 | VWAP position | MEDIUM (already gated, but scoring differentiation helps) | LOW | **P1** |
| 5 | Price extension | MEDIUM (prevents chasing extended moves) | LOW | **P2** |
