# Research Report: MOBX Entry Bug Investigation

**Date:** 2026-03-04  
**Agent:** Backend Planner  
**Reference:** handoff_planner_mobx_entry_bugs.md

---

## Context

MOBX 2026-03-04 entered two losing trades. Both entries reveal multiple entry guard failures:

| Trade | Entry | Exit | Time | Trigger | P&L |
|-------|-------|------|------|---------|-----|
| 1 | $1.36 | $1.34 | 11:15→11:31 | pmh_break | -$0.20 |
| 2 | $1.37 | $1.35 | 11:33→11:36 | pmh_break | -$0.20 |

Chart PMH was ~$1.70. Entries at $1.36/$1.37 are **20% below true PMH**.

---

## Bug 1: PMH Value Fallback — `session_high` Misused as PMH

### Finding

**File:** [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L559-L566)  
**Lines:** 559-566

```python
# Get pre-market high
pmh = await self._get_premarket_high(candidate.symbol)

self._watchlist[candidate.symbol] = WatchedCandidate(
    candidate=candidate,
    pmh=pmh or candidate.session_high,
)
```

When `_get_premarket_high()` returns `None`, the code falls back to `candidate.session_high`.

### What `session_high` Actually Is

**File:** [polygon_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py#L201):201

```python
"session_high": float(day.get("h", 0) or 0),
```

This is Polygon's **`day.h`** — the **intraday session high**, NOT the pre-market high. For MOBX on 2026-03-04:
- True PMH was ~$1.70 (achieved in pre-market)
- By 11:15, `session_high` would track the HOD (which could have been well below $1.70 after the stock faded)
- If FMP's `get_premarket_high()` failed (e.g., no 30-min bar data for MOBX), the fallback `session_high` would be an ever-updating value, not a true PMH

### Root Cause of FMP PMH Failure

**File:** [fmp_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/fmp_adapter.py#L466-L509):466-509

```python
def get_premarket_high(self, symbol, date=None):
    bars = self.get_intraday_bars(symbol, timeframe="30min", date=date)
    # ... filters bars before 9:30 AM ...
    return max(premarket_highs)
```

FMP uses **30-minute intraday bars**. For a low-float stock like MOBX ($1.36, micro-cap), **FMP may not have 30-min pre-market data** — these bars are sparse for tiny stocks. The function returns `None`, triggering the fallback.

### Clay's Key Insight

> Polygon already has premarket bar data. The PMH can be derived from max(high) of pre-9:30 bars.

This is correct — Polygon's intraday bars include pre-market data. The code is calling FMP (a different provider) for PMH when Polygon bars are already available via `engine._get_intraday_bars()` (which routes to Polygon/Alpaca).

### Second Fallback Also Broken

**File:** [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L624-L629):624-629

```python
# Fallback to quote day_high if FMP fails (less accurate)
if self._get_quote:
    quote = await self._get_quote(symbol)
    if quote:
        return Decimal(str(getattr(quote, 'day_high', 0) or 0))
return None
```

`day_high` from a quote also updates during the session — it's NOT a frozen pre-market high. This fallback is equally wrong.

### Recommended Fix (Priority: **CRITICAL**)

1. **Primary:** Derive PMH from Polygon intraday bars (already available via `engine._get_intraday_bars(symbol, "1min", limit=100)`). Filter for bars before 9:30 AM ET, take `max(high)`.
2. **Remove** the FMP `get_premarket_high()` dependency — it's an unnecessary API call to a different provider.
3. **Remove** the `day_high` quote fallback — it's semantically incorrect for PMH.
4. **If no pre-market bars exist** from any source, log a WARNING and do NOT add to watchlist (fail-closed).

---

## Bug 2: No Price Floor Check at Entry

### Finding

The scanner checks `min_price=$1.50` at scan time (**line 716**):

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L714-L718):714-718

```python
filtered_movers = [
    g for g in all_movers
    if g["price"] >= self.settings.min_price  # $1.50
    and g["price"] <= self.settings.max_price
    and g["change_percent"] >= self.settings.min_gap
]
```

MOBX passed at ~$1.80+ during the scan. By entry time (11:15), price had faded to $1.36 — **below the $1.50 minimum**.

### Entry Path Has NO Price Floor

Verified by reading the complete entry path:

| Function | File | Lines | Price Check? |
|----------|------|-------|-------------|
| `check_entry_triggers()` | warrior_engine_entry.py | 334-720 | ❌ No |
| `enter_position()` | warrior_engine_entry.py | 1056-1613 | ❌ No |
| `check_entry_guards()` | warrior_entry_guards.py | 35-209 | ❌ No |
| `validate_technicals()` | warrior_entry_guards.py | 546-672 | ❌ No (checks VWAP/EMA, not price floor) |
| `calculate_position_size()` | warrior_entry_sizing.py | 95-146 | ❌ No |

**There is zero price floor enforcement between scan and entry.**

### Recommended Fix (Priority: **HIGH**)

Add a price floor check in `check_entry_guards()` (warrior_entry_guards.py), before the MACD gate:

```python
# PRICE FLOOR — scanner min_price must still be respected at entry time
scanner_min_price = engine._get_scanner_setting("min_price", Decimal("1.50"))
if current_price < scanner_min_price:
    reason = f"Below scanner min_price (${current_price:.2f} < ${scanner_min_price:.2f})"
    tml.log_warrior_guard_block(symbol, "price_floor", reason, _trigger, _price, _btime)
    return False, reason
```

**Insertion point:** After line 132 (per-symbol fail limit), before line 139 (MACD gate). This is consistent with the existing guard ordering.

---

## Bug 3: Re-entry Cooldown Failure

### Finding

Trade 1 exited at 11:31. Trade 2 entered at 11:33 — only **2 minutes** later. Expected cooldown: **10 minutes**.

**File:** [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L157-L181):157-181

```python
# RE-ENTRY COOLDOWN (LIVE mode)
if not engine.monitor.sim_mode and symbol in engine.monitor._recently_exited:
    exit_time = engine.monitor._recently_exited[symbol]
    seconds_ago = (now_utc() - exit_time).total_seconds()
    cooldown_minutes = engine.monitor.settings.live_reentry_cooldown_minutes
    cooldown_seconds = cooldown_minutes * 60
    if seconds_ago < cooldown_seconds:
        # ... block ...

# SIM MODE COOLDOWN
if engine.monitor.sim_mode and symbol in engine.monitor._recently_exited_sim_time:
    exit_sim_time = engine.monitor._recently_exited_sim_time[symbol]
    if hasattr(engine.monitor, '_sim_clock') and engine.monitor._sim_clock:
        current_sim_time = engine.monitor._sim_clock.current_time
        minutes_since_exit = (current_sim_time - exit_sim_time).total_seconds() / 60
        cooldown_minutes = engine.monitor._reentry_cooldown_minutes
```

### Hypothesis: Mode Mismatch

The live cooldown guard is gated by `if not engine.monitor.sim_mode`. If the engine is in **paper trading mode** (which IS `sim_mode`), this guard is skipped entirely.

The sim cooldown guard requires **`_recently_exited_sim_time`** to be populated AND a **`_sim_clock`** to be present. In paper trading (Alpaca paper, not historical replay), there may be no `_sim_clock`, causing the sim cooldown to also be skipped.

### Verified Default

**File:** [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L156):156

```python
live_reentry_cooldown_minutes: int = 10
```

Default is 10 minutes. The code logic is correct, but the guard only fires in the right mode.

### Open Questions

1. Was MOBX running in paper (sim_mode=True) or live mode? If paper mode, the live cooldown is skipped.
2. Is `_recently_exited_sim_time` populated for paper trading exits? Need to check [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L1546-L1551):1546-1551.
3. The `_reentry_cooldown_minutes` attribute on the monitor (used in sim path) vs `settings.live_reentry_cooldown_minutes` on settings (used in live path) — are these the same value?

### Recommended Fix (Priority: **HIGH**)

1. **Unify the cooldown logic**: Use `settings.live_reentry_cooldown_minutes` for BOTH live and sim modes (they should have the same behavior).
2. **Paper mode needs `_recently_exited_sim_time`**: Verify that paper trading exits populate this dict. If not, the sim cooldown guard is a no-op in paper mode.
3. **Simplify**: Consider having a single cooldown path that works regardless of mode, using either wall clock or sim clock as appropriate.

---

## Bug 4: Sizing Configuration

### Finding

**File:** [warrior_engine_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_types.py#L87-L96):87-96

```python
# Risk
risk_per_trade: Decimal = Decimal("125")      # $125 per trade
max_positions: int = 10
max_daily_loss: Decimal = Decimal("999999")    # Disabled for testing
max_capital: Decimal = Decimal("5000")          # Max capital per trade
max_stop_pct: float = 0.10                     # 10% max stop distance

# Position Sizing Limits (for testing with small positions)
max_shares_per_trade: Optional[int] = 1        # Hard cap: 1 share
max_value_per_trade: Optional[Decimal] = None  # No $ cap
```

### How 10 Shares Resulted

The **default** `max_shares_per_trade=1` would produce 1 share, not 10. The handoff mentions 10 shares at $1.36, which means persisted settings overrode the default.

**File:** [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L890-L898):890-898

```python
_warrior_engine = WarriorEngine()
# Load persisted settings
settings = load_warrior_settings()
if settings:
    apply_settings_to_config(_warrior_engine.config, settings)
```

### Sizing Calculation

**File:** [warrior_entry_sizing.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_sizing.py#L95-L146):95-146

```python
risk_per_share = entry_decimal - mental_stop_decimal
shares = int(engine.config.risk_per_trade / risk_per_share)
max_shares = int(engine.config.max_capital / entry_decimal)
shares = min(shares, max_shares)
if engine.config.max_shares_per_trade is not None:
    shares = min(shares, engine.config.max_shares_per_trade)
```

With `risk_per_trade=$125`, `entry=$1.36`, `stop~$1.22` (10% below):
- `risk_per_share = $0.14`
- `shares = 125/0.14 = 892`
- `max_shares = 5000/1.36 = 3676`
- If `max_shares_per_trade=10`, final shares = 10 ✓

### Recommended Action (Priority: **LOW — Informational**)

Verify the persisted `max_shares_per_trade` value by checking the live settings endpoint:
```
GET /warrior/engine/status → config.max_shares_per_trade
```

This is working as configured. The bug is that 10 shares of a $1.36 stock produces tiny $13.60 positions with $0.20 losses — the sizing is dominated by the hard cap, not risk math.

---

## Bug 5: Dynamic Scoring Did Not Block Entry

### Finding

Entry metadata shows: VWAP $1.36, MACD 0.005 (flat), above EMA9 ($1.34). The scoring system penalized but did **not block** entry.

### Score Composition (Phase 2.1 Weights)

**File:** [warrior_entry_scoring.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_scoring.py#L245-L345):245-345

The scoring system uses 55% static / 45% dynamic weights. Dynamic factors include:

| Factor | MOBX Value | Score Effect |
|--------|-----------|-------------|
| MACD histogram | 0.005 (flat) | ~0.5 (neutral) |
| EMA trend | above EMA9 ($1.34) but likely below EMA20 | "weakening" → 0.5 |
| VWAP distance | $1.36 at VWAP (0% distance) | ~0.5 (neutral borderline) |
| Volume expansion | `None` (not wired) | Ignored (neutral default) |
| Re-entry count | 0 (first entry) then 1 (second) | 1.0 → 0.7 |
| Price extension | 20% below PMH (if PMH was wrong, this could be positive) | depends on incorrect PMH |

### Why Scoring Didn't Block

1. **MACD was technically positive** (0.005 > 0), so MACD gate passed. The `macd_histogram_tolerance` is `-0.02` — MOBX's 0.005 is above this.
2. **VWAP was at entry price** ($1.36), so not below VWAP → validate_technicals() passed.
3. **EMA9 was below entry** ($1.34 < $1.36), so the EMA check passed.
4. The **minimum score threshold** is `0.40`. With scanner score=8 and moderate dynamic factors, the total score likely exceeded 0.40.

### The Real Problem

Dynamic scoring doesn't have a **"price has collapsed since scan"** signal. The PMH bug (Bug 1) masked this: if the system thought PMH was ~$1.36 (from the wrong fallback), then price **at** PMH looks like a valid breakout.

With correct PMH ($1.70), the `price_extension_pct` would be **-20%** (20% below PMH), which would correctly produce a very low score from `compute_extension_score()`.

### Recommended Fix (Priority: **MEDIUM — Dependent on Bug 1**)

Fixing Bug 1 (correct PMH) will naturally fix this: the extension score would correctly penalize entries far below PMH. No additional scoring changes needed if PMH is correct.

---

## Fix Priority Summary

| Priority | Bug | Impact | Fix Complexity |
|----------|-----|--------|---------------|
| 🔴 CRITICAL | #1: PMH fallback to session_high | Wrong PMH → all PMH-based entries are unreliable | Medium — derive PMH from Polygon intraday bars |
| 🟠 HIGH | #2: No price floor at entry | Entries below scanner min_price | Easy — add 5-line guard in `check_entry_guards()` |
| 🟠 HIGH | #3: Cooldown mode mismatch | Paper mode skips both cooldown paths | Medium — unify cooldown logic |
| 🟡 MEDIUM | #5: Dynamic scoring masked by wrong PMH | Extension score neutral when it should be heavily negative | Dependent on Bug 1 fix |
| ⚪ LOW | #4: Sizing configuration | Working as configured, produces tiny positions on cheap stocks | Informational only |

---

## Change Surface (for Backend Specialist)

### Files Requiring Modification

| # | File | Change | Template |
|---|------|--------|----------|
| 1 | `warrior_engine.py` | Rewrite `_get_premarket_high()` to use Polygon bars | Existing `_get_intraday_bars()` call pattern |
| 2 | `warrior_engine.py:565` | Remove `session_high` fallback, handle None with fail-closed | — |
| 3 | `warrior_entry_guards.py:132-138` | Add price floor guard after fail limit check | Existing guard pattern (lines 96-132) |
| 4 | `warrior_entry_guards.py:157-181` | Unify live/sim cooldown to work in paper mode | Existing sim cooldown pattern |

### Files NOT Requiring Modification

- `warrior_entry_scoring.py` — scoring is correct given correct PMH
- `warrior_entry_sizing.py` — working as configured
- `warrior_engine_types.py` — defaults are reasonable
