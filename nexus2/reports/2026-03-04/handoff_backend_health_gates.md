# Backend Specialist Handoff: Wire Health Metrics into Entry Gates

**Date:** 2026-03-04 13:02 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Priority:** HIGH — WB is not yet profitable. Every bad trade prevented matters.  
**Output:** `nexus2/reports/2026-03-04/backend_status_health_gates.md`

---

## Context

Health metrics (EMA 200, room_to_ema_pct, position health indicators) have been **display-only since inception** (Jan 17, 2026). The bot enters trades regardless of what the dashboard health indicators show. This was confirmed via git history.

EMA data was broken (bar reversal bug) until today's fix. Now that EMA data is correct, we can safely gate entries on health metrics.

**Non-negotiable principle:** "Better to not trade than trade blind."

---

## Step 0: Audit ALL Computed Technicals (MANDATORY FIRST STEP)

Before implementing any gates, audit every technical indicator that is computed at entry time. For each, determine:
- Where it's computed
- Whether it gates entries, feeds scoring, or is display-only
- If display-only: should it gate or score entries?

Known indicators to check: **MACD** (status, value, histogram), **VWAP** (above/below), **EMA 9** (above/below), **EMA 200** (value, room_to_ema_pct), **volume expansion**, **position health**.

Report the full matrix in the status report. Then implement gates for the ones that should block bad trades.

---

## Fix: Add Health Check to Entry Guards

**File:** `warrior_entry_guards.py`

### Gate 1: EMA Sanity Check
If the EMA 200 value fails the sanity check (ratio > 100x vs current price), **block entry**. This is a data quality gate — we should never trade on garbage data.

```python
# If EMA data is clearly broken, don't trade
if ema_200 is not None and (ema_200 / current_price > 100 or current_price / ema_200 > 100):
    logger.warning(f"[Entry Guard] {symbol}: EMA sanity check FAILED - EMA=${ema_200:.2f} vs price=${current_price:.2f}")
    return False
```

### Gate 2: Wire Health Into Dynamic Scoring
The dynamic scoring system already exists. Pass the health metrics (room_to_ema_pct, EMA position) into the scoring function so they can penalize unhealthy entries.

**Important:** Do NOT invent thresholds. Check `.agent/strategies/warrior.md` for any EMA-related entry criteria from Ross's methodology. If nothing is documented there, add room_to_ema as a scoring factor (penalty, not hard gate) and let Clay tune the weight.

### Gate 3: Log Health Snapshot at Entry
Regardless of gating, log the health metrics at entry time in the trade event metadata so we can analyze correlations after the fact.

---

## Verification

```powershell
# Batch test — may change results if any cases had broken EMA gating
python scripts/gc_quick_test.py --all --diff
```

## Important
- Do NOT invent numeric thresholds from memory
- Check the strategy file for documented EMA rules
- If no documented rules exist, use scoring penalties not hard blocks (except for Gate 1 which is data quality)
