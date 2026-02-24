# Validation Report: Momentum Scaling Implementation

**Date:** 2026-02-24  
**Validator:** Audit Validator  
**Reference:** `nexus2/reports/2026-02-24/backend_status_momentum_scaling.md`

---

## Claim Verification Table

| # | Claim | Result | Evidence Summary |
|---|-------|--------|------------------|
| 1 | Momentum settings in `warrior_types.py` | **PASS** | 4 settings (L116-119) + 2 position fields (L211-212) |
| 2 | `check_momentum_add()` with correct criteria | **PASS** | Function at L164-254 with all 6 gates verified |
| 3 | Monitor loop integrates momentum fallback | **PASS** | Import + call at L599-603, gated on `enable_momentum_adds` |
| 4 | `execute_scale_in()` tracks momentum state | **PASS** | L453-459 updates `last_momentum_add_price` + `momentum_add_count` |
| 5 | API fields wired in `warrior_routes.py` | **PASS** | Request (L67-72), GET (L865-870), PUT (L901-912) — 20 matches |
| 6 | Independent counters | **PARTIAL PASS** | Gating is independent; execution has cross-contamination |

---

## Detailed Evidence

### Claim 1: Momentum settings in `warrior_types.py`

**Claim:** Lines 115-118 contain 4 momentum settings, Lines 210-211 contain 2 position fields.

**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_types.py" -Pattern "enable_momentum_adds|momentum_add_interval|momentum_add_size_pct|max_momentum_adds|last_momentum_add_price|momentum_add_count"
```

**Actual Output:**
```
warrior_types.py:116:    enable_momentum_adds: bool = False
warrior_types.py:117:    momentum_add_interval: float = 1.00
warrior_types.py:118:    momentum_add_size_pct: int = 50
warrior_types.py:119:    max_momentum_adds: int = 3
warrior_types.py:211:    last_momentum_add_price: Optional[Decimal] = None
warrior_types.py:212:    momentum_add_count: int = 0
```

**Result:** ✅ **PASS**  
**Notes:** Line numbers shifted by 1 (claim said 115-118, actual is 116-119). All 6 fields confirmed with correct types and defaults.

---

### Claim 2: `check_momentum_add()` function with correct criteria

**Claim:** Function exists with 5 documented trigger gates.

**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "check_momentum_add|trigger.*momentum"
```

**Actual Output:**
```
warrior_monitor_scale.py:155:       "trigger": "pullback",  # Distinguish from momentum adds
warrior_monitor_scale.py:164:async  def check_momentum_add(
warrior_monitor_scale.py:253:       "trigger": "momentum",  # Distinguish from pullback
warrior_monitor_scale.py:453:       if scale_signal.get("trigger") == "momentum":
```

**Code inspection** (lines 164-254) confirmed all gates:

| Gate | Line | Code |
|------|------|------|
| `enable_momentum_adds` | 187-188 | `if not s.enable_momentum_adds: return None` |
| `momentum_add_count >= max_momentum_adds` | 190-191 | `if position.momentum_add_count >= s.max_momentum_adds: return None` |
| Position green | 194-195 | `if current_price <= position.entry_price: return None` |
| Price interval check | 207-211 | `price_move = current_price - reference_price; if price_move < interval: return None` |
| Pending exit | 199-201 | `if monitor._is_pending_exit(symbol): return None` |
| Stop buffer | 216-222 | `if stop_buffer_pct < 1.0: return None` |
| Returns `"trigger": "momentum"` | 253 | Confirmed |

**Result:** ✅ **PASS**  
**Notes:** Function actually has 6 gates (claim documented 5, but also has a stop buffer safety check — this is a bonus, not a deficiency).

---

### Claim 3: Monitor loop integration

**Claim:** `warrior_monitor.py` imports and calls `check_momentum_add()` as fallback after pullback check.

**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor.py" -Pattern "check_momentum_add|momentum_add" -Context 2,3
```

**Actual Output (key lines):**
```
warrior_monitor.py:580:    self.settings.enable_scaling or self.settings.enable_momentum_adds
warrior_monitor.py:598:    # Momentum add check (independent trigger, same execution path)
warrior_monitor.py:599:    if not scale_signal and self.settings.enable_momentum_adds:
warrior_monitor.py:600:        from nexus2.domain.automation.warrior_monitor_scale import check_momentum_add
warrior_monitor.py:601:        scale_signal = await check_momentum_add(
warrior_monitor.py:602:            self, position, Decimal(str(current_price))
warrior_monitor.py:603:        )
```

**Result:** ✅ **PASS**  
**Notes:** Correctly structured as fallback — only checked `if not scale_signal` (L599), meaning pullback check runs first. Also gated on `enable_momentum_adds` (L599) and included in the `should_check_scale` guard (L580).

---

### Claim 4: `execute_scale_in()` tracks momentum state

**Claim:** When `trigger == "momentum"`, updates `last_momentum_add_price` and increments `momentum_add_count`.

**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "last_momentum_add_price|momentum_add_count" -Context 1,2
```

**Actual Output (execution path, L452-459):**
```python
# Update momentum tracking if this was a momentum add
if scale_signal.get("trigger") == "momentum":
    position.last_momentum_add_price = price
    position.momentum_add_count += 1
    logger.info(
        f"[Warrior Momentum] {symbol}: Momentum add #{position.momentum_add_count} tracked "
        f"at ${price:.2f}"
    )
```

**Result:** ✅ **PASS**  
**Notes:** Tracking is correctly gated on `trigger == "momentum"` at L453. Both fields updated.

---

### Claim 5: API fields wired in `warrior_routes.py`

**Claim:** All 5 fields in request model, GET response, and PUT handler.

**Verification Command:**
```powershell
Select-String -Path "nexus2\api\routes\warrior_routes.py" -Pattern "enable_momentum_adds|momentum_add_interval|enable_improved_scaling|momentum_add_size_pct|max_momentum_adds"
```

**Actual Output:** 20 matches across all three locations:

| Location | Lines | Fields Found |
|----------|-------|-------------|
| Request model | 67-72 | All 5 fields with `Optional` types + `Field` descriptions |
| GET response | 865-870 | All 5 fields read from `s.*` settings |
| PUT handler | 901-912 | All 5 fields with `hasattr`/`is not None` pattern |

**Result:** ✅ **PASS**  
**Notes:** Clean implementation. Request model uses `Optional[T] = Field(None, ...)` pattern. PUT handler uses `hasattr + is not None` guard (same pattern as existing fields).

---

### Claim 6: Independent counters

**Claim:** Momentum adds use `momentum_add_count`/`max_momentum_adds` independently from pullback's `scale_count`/`max_scale_count`.

**Verification:**

**Gating logic — INDEPENDENT ✅**

| Function | Gate | Line | Counter Used |
|----------|------|------|-------------|
| `check_scale_opportunity()` | Max check | 52 | `position.scale_count >= s.max_scale_count` |
| `check_momentum_add()` | Max check | 190 | `position.momentum_add_count >= s.max_momentum_adds` |

The gating logic correctly uses separate counters.

**Execution logic — CROSS-CONTAMINATION ⚠️**

At `warrior_monitor_scale.py:380`:
```python
position.scale_count += 1  # Line 380 — runs for ALL triggers
```

This line is **BEFORE** the momentum-specific block (L453-455), and it runs unconditionally for both pullback AND momentum adds. This means:
- **Momentum adds increment BOTH `scale_count` AND `momentum_add_count`**
- Pullback adds only increment `scale_count`

**Impact:** If `max_scale_count = 2` and a position takes 2 momentum adds, pullback scaling will be blocked because `scale_count` will be 2 ≥ `max_scale_count`. The momentum counter is independent for its own gating, but the shared `scale_count` bump creates an asymmetric dependency.

**Additional finding:** `check_momentum_add()` line 252 also sets `"scale_count": position.scale_count + 1` in the returned signal dict. This value is informational (used in logging), but it further indicates the counters are entangled rather than fully independent.

**Result:** ⚠️ **PARTIAL PASS**  
**Notes:** This may be intentional as a global "total adds" safety cap, or it may be a bug. Either way, the claim of "independent counters" is only true at the gating level, not at the execution level.

---

## Overall Quality Rating

**MEDIUM** — All primary implementation claims verified. One design concern (scale_count cross-contamination at L380) requires clarification on intent.

### Summary
- **5 of 6 claims: PASS**
- **1 claim: PARTIAL PASS** (Claim 6 — independent gating confirmed, but shared `scale_count` increment in `execute_scale_in()` creates cross-contamination)

### Recommended Action
Coordinator should clarify whether the `scale_count` bump at L380 is:
1. **Intentional** — acts as a global "total adds" safety cap across both types → document as design decision
2. **Bug** — momentum adds should NOT bump `scale_count` → fix by moving L380 inside an `else` block or `if trigger != "momentum"` guard
