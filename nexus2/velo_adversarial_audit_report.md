# Adversarial Audit: VELO Trace Claims

**Auditor**: Code Auditor (Adversarial Role)  
**Date**: 2026-02-12  
**Mission**: Attempt to DISPROVE each claim B1-B4. If unable to disprove, explain why it holds.

---

## Executive Summary

Claims B1, B2, and B3 are **CONFIRMED** (cannot be disproved). Claim B4 is **PARTIALLY DISPROVEN** — the backend agent's *explanation* of the timing mechanism is imprecise and speculative. The actual root cause is simpler than described.

> [!IMPORTANT]
> **Critical finding**: The $13.44 price exists in the VELO historical bar data at time **19:16** (after-hours bar). It is NOT a stale/wrong-time price. The batch runner simply never reaches this bar because it only steps 502 minutes (to ~12:22), while the GUI steps 960 minutes (to ~20:00). The divergence is a **clock range difference**, not a timing desync or stale price issue.

---

## Claim B1: "sim_get_price never fires (0 traces)"

### Verdict: ✅ CONFIRMED — Cannot Disprove

**Attack vector**: Was the trace placed in the wrong function? Could there be multiple price callbacks?

**Analysis**:

1. The `sim_get_price` callback is defined at [warrior_sim_routes.py L860-871](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L860-L871) and wired via `set_callbacks(get_price=sim_get_price)` at L997.

2. This sets `monitor._get_price = sim_get_price`.

3. `_get_price` is only called from one place: `_get_price_with_fallbacks` at [warrior_monitor_exit.py L79](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L79).

4. `_get_price_with_fallbacks` is only called from `evaluate_position` at L932 — but **only in the `else` branch** when `prefetched_price` is `None` or `0`.

5. `_check_all_positions` (L540-596) always pre-fetches prices via `_get_prices_batch` before calling `_evaluate_position`. So `prefetched_price` is always populated with a valid price → L927-928 uses it directly → `_get_price_with_fallbacks` is never reached → `sim_get_price` is never called.

**Why it holds**: The price resolution path is `_get_prices_batch` → `broker.get_price()`, which completely bypasses both `sim_get_price` and `_get_price_with_fallbacks`. The trace was placed correctly; the function genuinely never fires because the prefetched_price path at L927-928 handles all cases.

### Verification

```powershell
# Confirm prefetched_price bypass (L927-928)
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "prefetched_price is not None" | Select-Object LineNumber, Line

# Confirm _get_prices_batch populates prices before evaluate_position
Select-String -Path "nexus2\domain\automation\warrior_monitor.py" -Pattern "_get_prices_batch|_evaluate_position" | Select-Object LineNumber, Line
```

---

## Claim B2: "_get_price_with_fallbacks never fires (0 traces)"

### Verdict: ✅ CONFIRMED — Cannot Disprove

**Attack vector**: How does `evaluate_position` get a price if `_get_price_with_fallbacks` never fires?

**Analysis**:

The answer is definitively at [warrior_monitor_exit.py L927-932](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L927-L932):

```python
# L927-932 of evaluate_position
if prefetched_price is not None and prefetched_price != 0:
    current_price = Decimal(str(prefetched_price))           # ← ALWAYS takes this path
else:
    current_price = await _get_price_with_fallbacks(...)      # ← NEVER reached
```

`_check_all_positions` at L560-562 always pre-fetches:
```python
if self._get_prices_batch:
    prices = await self._get_prices_batch(symbols)
```

And passes it at L574:
```python
signal = await self._evaluate_position(position, current_price)
```

Where `current_price = prices.get(position.symbol)` at L573.

Since `_get_prices_batch` calls `broker.get_price()` which returns a float from `_current_prices` dict, and `set_price` is always called before `_check_all_positions` in `step_clock` (L1192 before L1225), the price is always non-None, non-zero → `_get_price_with_fallbacks` never fires.

**Why it holds**: The architectural design means prefetched_price always has a valid value. The claim is correct.

### Verification

```powershell
# Confirm the branching logic
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "prefetched_price" | Select-Object LineNumber, Line

# Confirm _check_all_positions passes price to _evaluate_position
Select-String -Path "nexus2\domain\automation\warrior_monitor.py" -Pattern "prices.get|_evaluate_position" | Select-Object LineNumber, Line
```

---

## Claim B3: "step_clock uses _get_prices_batch which calls broker.get_price() directly"

### Verdict: ✅ CONFIRMED — Cannot Disprove

**Attack vector**: Does `_get_prices_batch` actually exist at L1213-1223? Is it a hardcoded call or a wired callback?

**Analysis**:

1. At [warrior_sim_routes.py L1214-1223](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1214-L1223), `step_clock` defines a **fallback** `sim_get_prices_batch` that calls `broker.get_price(s)` directly.

2. However, this fallback only fires if `engine.monitor._get_prices_batch` is `None`. In practice, `load_historical_test_case` already wires `sim_get_prices_batch` at L873-881 via `set_callbacks` at L998.

3. Both implementations are **functionally identical**: they call `sim_broker.get_price(s)` → `MockBroker._current_prices.get(symbol)`.

4. The monitor's `_check_all_positions` at L560-562 calls `self._get_prices_batch(symbols)` — whichever callback is wired.

5. `MockBroker.get_price()` at [mock_broker.py L167-169](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/mock_broker.py#L167-L169) is a simple dict lookup: `self._current_prices.get(symbol)`.

**Why it holds**: The claim is correct. Both step_clock and the monitor use `_get_prices_batch` → `broker.get_price()` → dict lookup. The `sim_get_price` callback is completely bypassed.

### Verification

```powershell
# Verify both sim_get_prices_batch definitions
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "sim_get_prices_batch" | Select-Object LineNumber, Line

# Verify broker.get_price is a dict lookup
Select-String -Path "nexus2\adapters\simulation\mock_broker.py" -Pattern "_current_prices.get" | Select-Object LineNumber, Line
```

---

## Claim B4: "The divergence is just timing — monitor fires more in GUI"

### Verdict: ⚠️ PARTIALLY DISPROVEN — The conclusion is correct but the explanation is wrong

**Attack vector**: If both paths use `broker.get_price()`, they should see the same price at the same sim clock time. How can the same sim clock time produce different prices?

### What the backend agent claims (IMPRECISE):

> "The monitor background loop sees stale broker prices from a different simulated time"  
> "When the user steps quickly through multiple minutes, step_clock may have already set the broker price for minute 09:40, but the monitor loop sees the price from minute 09:36"

### Why this explanation is WRONG:

The "stale price" theory requires the monitor to fire between two `step_clock` iterations and see a price from a "wrong" sim time. But consider:

1. **`step_clock` is an HTTP endpoint** — it processes ALL steps in a single request. In the GUI path, calling `step_clock(minutes=960)` runs a `for` loop from step 0 to 959 in one `async` call.

2. Within each step, the sequence is: `set_price` (L1192) → `check_entry_triggers` (L1205) → `_check_all_positions` (L1225). This is a single async chain.

3. The monitor loop fires every `check_interval_seconds` (2s wall clock). Between any two `step_clock` steps in the same HTTP request, the CPU is yielded (`await`), allowing the asyncio event loop to run other tasks — including `_monitor_loop`.

4. **BUT**: The monitor's `_check_all_positions` calls `broker.get_price()` which returns whatever price was last set by `set_price` during the current loop iteration. This price IS the correct price for the current sim time because `set_price` just ran.

### The ACTUAL root cause is simpler:

> [!CAUTION]
> **The $13.44 DOES exist in the VELO historical bar data at time 19:16** (after-hours). It is NOT a stale or wrong-time price!

| Bar Time | Close Price | Location in JSON |
|----------|-------------|------------------|
| 18:55 | $13.52 | L4243 |
| 19:12 | $13.43 | L4251 |
| **19:16** | **$13.44** | **L4260** |
| 19:17 | $13.40 | L4267 |
| 19:52 | $13.49 | L4275 |
| 19:56 | $13.46 | L4283 |

**The divergence has TWO components:**

#### Component 1: Clock range difference (PRIMARY)

- **Batch**: Steps `bar_count + 30 = 472 + 30 = 502` minutes from 04:00, reaching approximately **12:22**.
- **GUI**: Steps 960 minutes from 04:00, reaching approximately **20:00**.
- The batch NEVER reaches the after-hours bars (17:xx-19:xx) where VELO declines from ~$14 to ~$13.4.
- The GUI DOES reach these bars and sets `broker.set_price("VELO", 13.44)` at sim time 19:16.
- If the position is still open at 19:16, `_check_all_positions` at L1225 will see $13.44 and trigger the stop.

This is a **sim clock range** difference, not a timing/stale price issue.

#### Component 2: Monitor background loop (SECONDARY)

The monitor running concurrently MAY add extra `_check_all_positions` calls (399 vs 203 evaluations), but these don't change the price — they see the same `broker.get_price()` that `step_clock` just set. The extra evaluations just mean more frequent checks, not different prices.

**However**, there IS a real interference risk: if the monitor fires `_check_all_positions` during an `await` yield point within `step_clock`, AND an entry was just created, the monitor could trigger a duplicate evaluation. The dual-entry evidence (second ENTRY 29 seconds after the first) suggests this IS happening.

### What ACTUALLY happens in the GUI:

1. `step_clock(960)` starts processing bars from 04:00
2. Around 09:01-09:02, an entry is triggered at $14.90
3. As `step_clock` advances through bars, it reaches afternoon and after-hours bars
4. The after-hours bars have VELO declining: $14→$13.80→$13.60→$13.44
5. When `step_clock` reaches a bar where `broker.get_price("VELO") <= position.current_stop`, the stop fires
6. In the batch path, `step_clock` only reaches 12:22. At 12:22, VELO is still well above the stop. The batch then EOD-closes at the last available price.

### What ACTUALLY happens in the batch:

1. `step_clock(502)` processes bars from 04:00 to ~12:22
2. At 12:22, VELO is still around $14.98 (well above stop)
3. After stepping completes, the batch force-closes at L1504-1532 using `broker._current_prices.get(symbol)` which is the $14.98 from the last step
4. P&L is modest positive: +$21.36

### Dual entry issue (the REAL extra problem)

The dual entry (two ENTRY events 29 seconds apart) IS evidence of monitor loop interference:

1. `step_clock` creates entry at sim time 09:01 → `_pending_entries` cleared after instant fill
2. Monitor loop fires between `step_clock` steps → another `check_entry_triggers` or `_check_all_positions` runs while `step_clock` is yielding
3. The second invocation COULD re-trigger entry logic if conditions still hold and `_pending_entries` was already cleared

With doubled shares (356 instead of 178), the stop-loss P&L doubles from ~$195 to ~$390.

### Verdict on B4

| Sub-claim | Status | Evidence |
|-----------|--------|----------|
| "Monitor fires more in GUI" | ✅ CONFIRMED | 399 vs 203 evaluate_position calls |
| "GUI sees stale broker prices from a different simulated time" | ❌ DISPROVEN | The $13.44 IS a real after-hours bar at 19:16 in the bar data |
| "Batch stops monitor at L1406" | ✅ CONFIRMED | L1405-1406 explicitly stops monitor |
| "Divergence is just timing" | ⚠️ PARTIALLY DISPROVEN | Primary cause is sim clock range (502 vs 960 mins), not timing desync |

---

## The Critical Question Answered: Where is $13.44?

> **$13.44 IS in the VELO historical bar data** at time **19:16** (after-hours), line 4260 of `ross_velo_20260210.json`.

This is:
- ❌ NOT a premarket bar (premarket bars are $13.55-$13.87)
- ❌ NOT from live API contamination
- ✅ An **after-hours bar** (19:16) from VELO's actual Feb 10 trading
- ✅ Reachable by the GUI (which steps to 20:00) but NOT by the batch (which stops at ~12:22)

The after-hours price decline: $14.98 (12:22) → $13.44 (19:16) is VELO giving back its intraday gains in the extended session. The batch runner holds to EOD close ($14.98), while the GUI replays into the after-hours session where the price collapses.

---

## Previous Report Errors

The two prior reports contain factual errors that should be corrected:

| Report | Error | Reality |
|--------|-------|---------|
| `velo_divergence_audit_report.md` (M2) | "Live API price fallback in sim... $13.x live prices instead of $15.x historical" | 0 traces of fallback firing. Price comes from broker dict, not live APIs. |
| `velo_trace_verification_report.md` (Q3) | "VELO premarket prices are in the $13.x range... monitor fires and sees the old premarket price" | $13.44 is NOT a premarket price. It's an after-hours bar at 19:16. |
| `velo_trace_verification_report.md` (Q3) | "broker price hasn't been updated to post-entry levels" | The broker price IS updated correctly — step_clock sets it to $13.44 at sim time 19:16 as expected. |
| `velo_divergence_audit_report.md` (Q1) | "Live Schwab/FMP/Alpaca contamination" | Fully disproven by 0 trace hits on all fallback paths. |

---

## Recommended Fix (REVISED)

The fix should address BOTH problems:

### Fix 1: Limit sim clock range to market hours (PRIMARY)

The GUI path replays into after-hours, which produces unrealistic exits. The batch runner already implicitly avoids this by only stepping `bar_count + 30` minutes. The GUI should either:

**(a)** Stop stepping at market close (16:00), or  
**(b)** Skip after-hours bars in `get_price_at`, or  
**(c)** Match the batch stepping strategy.

### Fix 2: Stop the monitor during historical replay (SECONDARY)

This is still correct and important for preventing dual entries and extra evaluations:

```python
# In load_historical_test_case, after L858
if engine.monitor._running:
    await engine.monitor.stop()
```

### Priority

Fix 1 is the **primary** fix because it addresses the root cause (GUI replaying into after-hours where the stock gives back all gains). Fix 2 is **defense-in-depth** against the dual-entry issue.

---

## Verification Commands

```powershell
# Find $13.44 in VELO bar data
Select-String -Path "nexus2\tests\test_cases\intraday\ross_velo_20260210.json" -Pattern "13.44" | Select-Object LineNumber, Line

# Confirm the after-hours bar time
Get-Content "nexus2\tests\test_cases\intraday\ross_velo_20260210.json" | Select-String -Pattern "19:16" -Context 0,6

# Confirm batch steps bar_count + 30
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "bar_count \+ 30" | Select-Object LineNumber, Line

# Confirm monitor.stop() in batch but NOT in load_historical
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "monitor.stop" | Select-Object LineNumber, Line
```
