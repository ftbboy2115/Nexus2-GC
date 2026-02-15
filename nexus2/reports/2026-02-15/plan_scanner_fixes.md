# Scanner Investigation & Fixes — Implementation Plan

**Date**: 2026-02-15
**Coordinator**: Claude (Coordinator Agent)
**Context**: Scanner not finding trades Ross took; timestamps stop at 9:28 AM; massive `gap_too_low` false rejections

---

## Background

The Warrior Scans tab on Data Explorer shows all scan results from Friday 02/13/2026 stopping at **9:28 AM** with nearly everything marked **FAIL** (reasons: `gap_too_low`, `rvol_too_low`, `float_too_high`). A prior multi-agent session on Feb 13 identified the root cause of the `gap_too_low` contradiction (112% gap stock failing as "gap too low") and applied partial fixes in commit `4704a07`. However, the core gap recalculation logic was **not fixed**, and no unit tests for pillar logic exist.

### Key Findings from Research

| Finding | Evidence |
|---------|----------|
| Scanner polls every 5 min via `_scan_loop()` in `warrior_engine.py:359` | `scanner_interval_minutes: int = 5` at `warrior_engine_types.py:78` |
| 9:28 AM = single pre-market scan, then engine stopped/crashed | No subsequent timestamps in Data Explorer |
| Gap recalculated **twice**: once in `scan()` (L656-683), again in `_calculate_gap_pillar()` (L1564) | Both use different data sources |
| `_calculate_gap_pillar()` uses `last_price` (Alpaca live) vs `yesterday_close` (from daily bars) | If stock fades, recalculated gap drops below 4% → `gap_too_low` |
| FMP still used heavily: float shares, former runner, country, catalyst, session OHLCV, previousClose | Should be Polygon-primary per user direction |
| `build_session_snapshot()` gets `yesterday_close` from Polygon/FMP daily bars, `last_price` from Alpaca | Correct approach but gap recalc is fragile |
| No unit tests for any pillar logic (gap, price, float, RVOL, 200 EMA) | Only settings, scoring, Chinese exclusion, momentum override tested |

---

## User Review Required

> [!IMPORTANT]  
> **Gap Recalculation Decision**: The scanner currently rejects stocks whose live price has faded below 4% above yesterday's close, even if they gapped 100%+ at open. This is a critical design decision.

### Option A: Use Opening Gap (Open vs Previous Close) — **RECOMMENDED**
- Gap pillar checks `session_open` vs `yesterday_close` (the ACTUAL gap)
- A stock that gapped 30% but faded to +3% intraday still passes the gap pillar
- **Pro**: Matches Ross's methodology — he watches gappers regardless of intraday fade
- **Pro**: Scanner finds the same stocks Ross is trading
- **Con**: May include stocks that have already lost momentum by the time scanner runs

### Option B: Use Live Price Gap (Current Price vs Previous Close)
- This is what's currently implemented
- **Pro**: Filters out stocks that have already faded (potentially dead plays)
- **Con**: Rejects valid gappers that pulled back (the MGRT 112% bug)
- **Con**: Scanner misses stocks Ross is actively trading

### Option C: Dual-Gate (Recommended Hybrid)
- Pass gap pillar if **EITHER** opening gap ≥ 4% **OR** live gap ≥ 4%
- Store both values for Data Explorer visibility
- **Pro**: Catches both scenarios — strong openers and recovering faders
- **Con**: Slightly more complex logic, but safer

> [!WARNING]
> **FMP Data Provider**: Clay has stated Polygon should be primary wherever possible ($200/mo being paid). Many scanner functions still use FMP directly. This plan includes auditing and migrating where appropriate, but a full migration is a larger effort.

---

## Proposed Changes

### Work Stream 1: Scanner Timing Investigation (Backend Planner/Auditor)

#### [INVESTIGATE] Scanner 9:28 AM Stoppage

- Check VPS server logs from Friday 02/13 for Warrior Engine errors after 9:28 AM
- Determine if engine was started at all, or crashed after first scan
- Check if `is_extended_hours_active()` or market calendar blocked scans
- Check if the scan itself threw an exception (e.g., API timeout) and the error handler's 30-second retry wasn't enough
- **Deliverable**: Root cause report in `nexus2/reports/2026-02-15/investigation_scanner_timing.md`

---

### Work Stream 2: Gap Pillar Fix (Backend Specialist)

#### [MODIFY] [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py)

**`_calculate_gap_pillar()` (L1553-1583)**:
- Add `session_open` to `EvaluationContext` (populated from `build_session_snapshot()`)
- Calculate *opening gap* = `(session_open - yesterday_close) / yesterday_close * 100`
- Calculate *live gap* = `(last_price - yesterday_close) / yesterday_close * 100` (current behavior)
- Pass gap pillar if **either** gap ≥ `min_gap` (Option C - pending Clay's decision)
- Store both `opening_gap_pct` and `live_gap_pct` on context for logging/telemetry
- Update `scan_logger` to show both values in REJECT messages

**`_evaluate_symbol()` (around L847)**:
- Populate `ctx.session_open` from `snapshot["session_open"]`

**`EvaluationContext` (L414-482)**:
- Add `session_open: Optional[Decimal] = None`
- Add `opening_gap_pct: Optional[float] = None`

**`_write_scan_result_to_db()` (L521-562)**:
- Log both gap values in telemetry for Data Explorer transparency

---

### Work Stream 3: FMP→Polygon Data Provider Audit (Code Auditor)

#### [INVESTIGATE] FMP Usage Across Scanner

Audit every FMP call in the scanner to determine which can be replaced with Polygon:

| Current FMP Usage | Polygon Alternative? | Priority |
|-------------------|---------------------|----------|
| `_get_float_shares()` — FMP shares-float API | ❌ Polygon doesn't have float data | Keep FMP |
| `_is_former_runner()` — FMP daily bars | ✅ Polygon daily bars (already used for EMA) | Migrate |
| `_get_country()` — FMP profile | ❌ Polygon has limited profiles | Keep FMP |
| Catalyst headlines — FMP news | ❓ Polygon has news API too | Investigate |
| `build_session_snapshot()` — FMP quote for session OHLCV | ✅ Polygon snapshot API | Migrate |
| `previousClose` in scan() gap recalc (L668) | ✅ Polygon previous close | Migrate |
| ETF symbol list | ❌ FMP has comprehensive ETF list | Keep FMP |

- **Deliverable**: Audit report in `nexus2/reports/2026-02-15/audit_fmp_scanner_usage.md`

---

### Work Stream 4: Scanner Unit Tests (Testing Specialist)

#### [NEW] [test_warrior_scanner_pillars.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/unit/scanners/test_warrior_scanner_pillars.py)

New test file covering each pillar in isolation:

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestGapPillar` | gap passes when ≥ 4%, gap fails when < 4%, opening gap captures faded stock, live gap captures fresh mover, both values logged | Gap recalculation bug |
| `TestPricePillar` | passes in range [$1.50-$40], rejects below min, rejects above max | Price boundaries |
| `TestFloatPillar` | passes < 100M, rejects > 100M, None float passes (skip), ideal flag set < 20M | Float logic |
| `TestRvolPillar` | passes ≥ 2x, rejects < 2x, pre-market projection, regular hours projection | RVOL time adjustment |
| `TestEma200` | passes when price above, rejects when price just below ceiling, None EMA passes | EMA resistance |
| `TestBorrowDisqualifiers` | high float > 100M rejected, ETB + float > 35M rejected | Borrow logic |

**Test approach**: Mock `EvaluationContext` with controlled values, call pillar method directly, assert result.

---

## Verification Plan

### Automated Tests

```powershell
# Run new pillar tests
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
python -m pytest nexus2/tests/unit/scanners/test_warrior_scanner_pillars.py -v

# Run existing scanner tests (regression check)
python -m pytest nexus2/tests/unit/scanners/test_warrior_scanner.py -v

# Run scan diagnostic on test cases (validates gap fix with real data)
python -m nexus2.cli.scan_diagnostic --all-test-cases
```

### Manual Verification

1. **Data Explorer check**: After deploying gap fix to VPS, wait for next scan cycle. Check Warrior Scans tab — `gap_too_low` rejections should show both opening gap and live gap values. Stocks with high opening gaps should no longer be rejected just because live price faded.

2. **Scanner timing**: After deploying, verify scan timestamps continue past 9:30 AM into regular market hours.

---

## Agent Assignments (Multi-Agent)

| Agent | Work Stream | Dependency |
|-------|-------------|------------|
| **Backend Specialist** | WS2: Gap pillar fix + EvaluationContext changes | After Clay approves Option A/B/C |
| **Code Auditor** | WS3: FMP→Polygon usage audit | Independent |
| **Testing Specialist** | WS4: Pillar unit tests | After WS2 complete |
| **Backend Planner** | WS1: Scanner timing investigation | Independent, can run on VPS logs |

> [!NOTE]
> WS1 (timing investigation) requires VPS access to check server logs. This may need Clay to provide log output or SSH access.
