# Handoff: Backend Specialist — Trigger Rejection Logging

**Date:** 2026-02-21
**From:** Coordinator
**To:** Backend Specialist (`@agent-backend-specialist.md`)
**Priority:** HIGH

---

## Objective

Implement the `WARRIOR_TRIGGER_REJECTION` event type so that below-threshold pattern rejections are persisted to the trade_events DB. This is a logging-only change — no behavioral changes to entry logic.

---

## Spec Reference

**Read this FIRST:** `nexus2/reports/2026-02-21/spec_early_rejection_logging.md`

The Backend Planner has already:
- Inventoried all 7 decision points
- Categorized them by value (HIGH/MEDIUM/LOW)
- Designed the event schema and metadata structure
- Identified exact line numbers for all change points
- Estimated volume and assessed risk
- Confirmed same code path for live and sim (Section I)
- Recommended 30-second per-symbol dedup for live mode (Section I)

**Follow the spec. Do not redesign.**

---

## Implementation Checklist

### Required (from spec sections E + I)

1. **Add `WARRIOR_TRIGGER_REJECTION` constant** to `trade_event_service.py` (line ~78)
2. **Add `log_warrior_trigger_rejection()` method** — model on `log_warrior_guard_block()` at lines 993-1029
   - TML file write + `_log_event()` DB write
   - Include dedup: 30-second per-symbol window (see spec Section I)
   - Dedup should use a dict `_trigger_rejection_dedup: Dict[str, datetime]` on the service
3. **Call site at line ~617** in `warrior_engine_entry.py` — the below-score rejection
   - Pass: symbol, best_pattern, best_score, threshold, candidate_count, price, all_candidates
4. **Import** `trade_event_service as tml` if not already imported at the call site

### Optional (lower priority — implement if time allows)

5. **Micro-pullback extended skip logging** at line ~419 (throttled per symbol, spec Change Point #4)

---

## Verification

After implementation:
1. Run the full test suite: `python -m pytest nexus2/tests/ -x -q`
2. Run BATL batch test and confirm TRIGGER_REJECTION events appear in results:
   ```powershell
   python -c "import requests, json; r=requests.post('http://localhost:8000/warrior/sim/run_batch_concurrent', json={'case_ids': ['ross_batl_20260126']}); print(json.dumps(r.json(), indent=2))"
   ```
3. Verify events are in DB (check trade_events table for event_type='TRIGGER_REJECTION')

---

## Deliverable

- Modified files committed
- Status report: `nexus2/reports/2026-02-21/backend_status_trigger_rejection_logging.md`
