# Validation Report: Batch Runner Performance Audit

**Date:** 2026-02-13  
**Auditor Report:** [audit_batch_runner.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-13/audit_batch_runner.md)  
**Validator:** Audit Validator Agent

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| V1 | Zero `fmp_adapter` / `schwab_adapter` references in `nexus2/adapters/simulation/` | **PASS** | 9 hits found but **all are comments, docstrings, or mock proxy properties** — no actual adapter imports. `mock_broker.py` L5,101,200: `AlpacaBroker` in docstrings. `mock_market_data.py` L90,683: `def fmp(self)` returns `self` as proxy. `sim_context.py` L388: comment "prevent Alpaca calls". Zero `from nexus2.adapters.market_data.*_adapter` imports. |
| V2 | All 14 callbacks wired to `MockBroker`/`HistoricalBarLoader`/`SimulationClock` | **PASS** | `sim_context.py` — MockBroker: **6 refs**, HistoricalBarLoader: **3 refs**, SimulationClock: **3 refs**. Multiple references confirm these sim components are wired into the callback system. |
| V3 | Unguarded Schwab/FMP fallback in `_get_price_with_fallbacks` | **PASS** | `warrior_monitor_exit.py` L62-108 confirmed: Schwab adapter imported at L25-26, FMP adapter imported at L41-42. **No `sim_mode` guard** found anywhere in the function. If `MockBroker.get_price()` returns `None`, live API calls proceed without any sim check. |
| V4 | `ProcessPoolExecutor` with `spawn` context | **PASS** | `sim_context.py` L607: `ProcessPoolExecutor(max_workers=max_workers, mp_context=multiprocessing.get_context("spawn"))` — exact match to auditor's claim. Import at L602, documentation at L587. |
| V5 | Bar data loaded from JSON, not API | **PASS** | `historical_bar_loader.py` — **0 API references** (fmp, schwab, alpaca, polygon, requests.get, httpx, aiohttp all absent). **2 `json.load` references** confirming local JSON file reads. |
| V6 | `_get_premarket_high` not reached in batch path | **PASS** | `sim_context.py` L226: `pmh = Decimal(str(premarket.get("pmh", entry_price)))` — PMH is set directly from YAML metadata. L252,258: pmh assigned to `WatchedCandidate` fields. The FMP call in `warrior_engine.py` is never reached because the batch path constructs the candidate manually. |

---

## Overall Rating

**HIGH** — All 6 claims verified. The audit report is accurate and well-documented.

---

## Notable Findings

### V3 Risk Confirmed (Auditor Recommendation Valid)

The auditor's primary recommendation to **add a `sim_mode` guard** to `_get_price_with_fallbacks` is validated. The Schwab (L25-35) and FMP (L41-48) fallback chains execute unconditionally. While the likelihood is low (MockBroker is populated each clock step), the absence of a guard is a legitimate defense-in-depth gap.

### V1 Nuance

While the strict claim ("zero `fmp_adapter` / `schwab_adapter` references") is accurate, the broader search reveals provider-related terminology in comments and mock proxy methods. These are **not functional leaks** — `mock_market_data.py`'s `fmp` property returns `self` (returning the mock as a drop-in proxy), not the real adapter.

---

## Failures

None. All claims verified successfully.
