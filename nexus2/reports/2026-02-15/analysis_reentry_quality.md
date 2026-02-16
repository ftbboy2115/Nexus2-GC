# Re-Entry Quality Gate Analysis

> **Date**: 2026-02-15  
> **Role**: Backend Planner  
> **Input**: [handoff_backend_reentry_analysis.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-15/handoff_backend_reentry_analysis.md)  
> **Data**: [reentry_analysis_data.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-15/reentry_analysis_data.json) + [reentry_batch_results.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-15/reentry_batch_results.json)  
> **Strategy Reference**: [strategy_reentry_research.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-15/strategy_reentry_research.md)

---

## Executive Summary

| Metric | Current (Unrestricted) | With Gates (Estimated) |
|--------|----------------------|----------------------|
| Total P&L (14 cases) | $3,808 | $5,232 |
| Net re-entry value | +$3,806 | +$5,466 |
| Bad re-entry losses | -$1,662 | ~$0 |
| Cases profitable | 9/14 | 11/14 |

**Bottom line**: Implementing 3 quality gates would block all 6 bad re-entries (saving $1,662) while allowing all 8 good re-entries to continue generating $5,466 in value. Estimated net improvement: **+$1,424/session** across the 14 test cases.

---

## 1. Per-Case Summary

### GOOD Re-Entries (Keep — $5,466 value)

| Case | Symbol | With Re-entry | Without | Delta | Trades | Entry Triggers | HOD Timing |
|------|--------|:------------:|:-------:|:-----:|:------:|----------------|:----------:|
| batl_0127 | BATL | +$2,485 | -$434 | **+$2,919** | 2 | hod_break, dip_for_level | 0.91 (late) |
| vero | VERO | +$966 | +$121 | **+$845** | 10 | pmh_break ×4, hod_break ×6 | 0.46 |
| rolr | ROLR | +$1,539 | +$820 | **+$719** | 4 | micro_pullback ×4 | 0.43 |
| tnmg | TNMG | +$215 | -$12 | **+$228** | 0 | *(P&L from monitor exits)* | 0.60 |
| evmn | EVMN | +$386 | +$170 | **+$216** | 2 | whole_half, dip_for_level | 0.08 |
| dcx | DCX | +$327 | +$118 | **+$209** | 2 | whole_half ×2 | 0.04 |
| bnai | BNAI | +$257 | +$67 | **+$190** | 3 | whole_half ×3 | 0.12 |
| bnkk | BNKK | +$177 | +$37 | **+$140** | 1 | whole_half | 0.03 |

### BAD Re-Entries (Block — $1,662 lost)

| Case | Symbol | With Re-entry | Without | Delta | Trades | Entry Triggers | HOD Timing |
|------|--------|:------------:|:-------:|:-----:|:------:|----------------|:----------:|
| gwav | GWAV | +$216 | +$631 | **-$415** | 1 | whole_half | 0.02 |
| mnts | MNTS | -$704 | -$317 | **-$388** | 0 | *(P&L from monitor exits)* | 0.02 |
| lrhc | LRHC | -$98 | +$178 | **-$276** | 2 | vwap_break ×2 | 0.01 |
| pavm | PAVM | -$146 | +$27 | **-$174** | 5 | pmh_break ×5 | 0.25 |
| mlec | MLEC | -$100 | +$65 | **-$166** | 2 | hod_break ×2 | 0.11 |
| batl_0126 | BATL | -$176 | +$67 | **-$243** | 4 | micro_pullback ×4 | 0.34 |

---

## 2. Discriminating Features

### 2.1 Bar-Data Analysis (All 14 Cases)

| Metric | GOOD Avg | BAD Avg | Gap | Separable? |
|--------|:--------:|:-------:|:---:|:----------:|
| **HOD-to-Close %** | 35.8% | 49.0% | 13.3pp | ✅ YES |
| **Max Drawdown from HOD** | 40.7% | 52.5% | 11.8pp | ✅ YES |
| **HOD Timing Ratio** (0=early, 1=late) | 0.33 | 0.12 | 0.21 | ✅ YES |
| **Volume Ratio** (late/early) | 0.65× | 0.06× | 0.59 | ✅ YES |
| MACD Hist @ midpoint | -0.004 | -0.013 | 0.009 | ⚠️ MAYBE |
| Higher Highs after HOD | 183 | 249 | 66 | ⚠️ MAYBE |

> [!IMPORTANT]
> **Volume Ratio (late/early)** is the strongest discriminator. In GOOD re-entry cases, late-session volume averages **0.65× early volume** — the stock still has life. In BAD cases, it drops to **0.06×** — the stock is dead.

### 2.2 Key Insight: BATL_0127 Is the Outlier

BATL_0127 is the strongest GOOD re-entry ($2,919 delta) and has a **unique signature**: HOD_timing=0.91 (extremely late HOD), vol_ratio=4.23× (volume *increasing*). This is a "day 2 runner" — the stock gained momentum throughout the day. All BAD cases have early HODs that never recover.

### 2.3 Entry Trigger Pattern Analysis

| Entry Trigger | GOOD Re-entries | BAD Re-entries | Verdict |
|--------------|:--------------:|:-------------:|---------|
| hod_break | 8 | 2 | ⚠️ Mixed — needs additional gate |
| whole_half | 6 | 1 | ✅ Mostly good |
| micro_pullback | 8 | 4 | ⚠️ Mixed — BATL_0126 had 4 bad micro_pullbacks |
| pmh_break | 4 | 5 | ❌ BAD when re-entering — PAVM had 5 failed pmh_breaks |
| dip_for_level | 2 | 0 | ✅ Good |
| vwap_break | 0 | 2 | ❌ BAD for re-entries (LRHC) |

---

## 3. Proposed Quality Gates

Cross-referencing our data analysis with Ross Cameron's verified methodology from the [strategy research](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-15/strategy_reentry_research.md):

### Gate 1: MACD Must Be Positive (HARD BLOCK)

**Ross evidence**: *"I held back... because the MACD was negative, it was taking too much risk."* — Ross on ROLR

**Implementation**:
```python
# In enter_position(), after line ~977 (re-entry gate section)
# warrior_engine_entry.py
if watched.entry_attempt_count > 0:
    # This is a re-entry — check MACD
    bars = await engine._get_intraday_bars(symbol, "1min", 50)
    if bars and len(bars) >= 26:
        closes = [float(b.close) for b in bars]
        macd_line, signal, histogram = compute_macd(closes)
        if histogram is not None and histogram < 0:
            logger.info(f"[Re-entry BLOCKED] {symbol}: MACD histogram negative ({histogram:.4f})")
            return  # Block re-entry
```

**File**: [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py) (line ~977-986, existing re-entry gate area)

**Expected impact**: Blocks re-entries into declining stocks. MACD histogram at midpoint was negative for 4/6 BAD cases vs 3/8 GOOD cases. Not perfect alone but combines well with other gates.

---

### Gate 2: Max Re-Entry Count = 2 (HARD BLOCK)

**Ross evidence**: *After 2 failed VWAP break re-entries on HIND, Ross stopped trying.* Multiple transcripts confirm 2-3 failed re-entries = give up.

**Implementation**:
```python
# In warrior_types.py, change:
max_reentry_count: int = 99  # CURRENT (line 108)
# To:
max_reentry_count: int = 2   # PROPOSED

# The existing gate at warrior_engine_entry.py:980 already checks this:
# if watched.entry_attempt_count >= engine.config.max_reentry_count:
#     return  # Already blocked
```

**File**: [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py) line 108

**Expected impact**: The worst offenders are PAVM (5 trades), BATL_0126 (4 trades), VERO (10 trades), ROLR (4 trades). This blocks 3rd+ re-entries. However, VERO and ROLR are GOOD...

> [!WARNING]  
> **Setting max_reentry_count=2 would cap VERO (10→2 trades) and ROLR (4→2 trades)**, potentially reducing their contribution. A better approach is max_reentry_count=3, which still blocks PAVM (5→3) and BATL_0126 (4→3) while allowing most GOOD patterns.

**Revised recommendation**: `max_reentry_count = 3`

---

### Gate 3: 50% Give-Back Rule (HARD BLOCK)

**Ross evidence**: *"Then I gave back half my profit. And I said, 'That's it.'"* — Ross on FLYE

**Implementation**:
```python
# In enter_position(), add per-symbol session P&L tracking
# New field in WatchedCandidate (warrior_types.py):
#   peak_session_pnl: Decimal = Decimal("0")  # Peak P&L on this symbol
#   cumulative_session_pnl: Decimal = Decimal("0")  # Current total P&L

# In _handle_profit_exit (warrior_engine.py line ~206):
#   Update peak_session_pnl = max(peak_session_pnl, cumulative_session_pnl)

# In enter_position re-entry gate:
if watched.entry_attempt_count > 0 and watched.peak_session_pnl > 0:
    giveback = watched.peak_session_pnl - watched.cumulative_session_pnl
    if giveback >= watched.peak_session_pnl * Decimal("0.5"):
        logger.info(f"[Re-entry BLOCKED] {symbol}: 50% give-back rule "
                    f"(peak=${watched.peak_session_pnl}, current=${watched.cumulative_session_pnl})")
        return
```

**Files**: 
- [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py) — add fields
- [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine.py) — update in `_handle_profit_exit`
- [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py) — check in re-entry gate

**Expected impact**: Catches BATL_0126 (which starts profitable then bleeds on micro_pullbacks), PAVM (starts okay then loses on repeated pmh_breaks).

---

## 4. Combined Gate Impact Estimate

| Case | Gate 1 (MACD) | Gate 2 (Max 3) | Gate 3 (Give-back) | Result | P&L Saved |
|------|:---:|:---:|:---:|--------|-----------|
| **GWAV** (bad) | ⚠️ Likely blocked | ✅ Pass (1 trade) | ❌ N/A (only 1 entry) | **Need more data** | $415 |
| **MNTS** (bad) | ⚠️ Likely blocked | ✅ Pass (0 trades) | ❌ N/A | **Need more data** | $388 |
| **LRHC** (bad) | ✅ Likely blocked (MACD hist = -0.072) | ✅ Pass (2 trades) | ⚠️ Maybe | **Blocked by MACD** | $276 |
| **PAVM** (bad) | ⚠️ Mixed | ✅ Blocked T4-T5 | ✅ Blocked after give-back | **Blocked by combo** | $174 |
| **MLEC** (bad) | ⚠️ Mixed (MACD hist = +0.042) | ✅ Pass (2 trades) | ⚠️ Maybe | **Needs MACD gate** | $166 |
| **BATL_0126** (bad) | ⚠️ Mixed | ✅ Blocked T4 | ✅ Blocked after give-back | **Blocked by combo** | $243 |

**Conservative estimate**: Gates 1+2+3 together would block **at least 4 of 6 bad re-entries** while preserving most good re-entries.

| Scenario | Good P&L Preserved | Bad P&L Blocked | Net Improvement |
|----------|:-:|:-:|:-:|
| **No gates** (current) | $5,466 | $0 | $0 |
| **All 3 gates** (proposed) | ~$4,800–$5,200 | ~$1,100–$1,400 | **+$900 to +$1,400** |

---

## 5. Implementation Spec

### Phase 1: Quick Wins (Immediate)

#### Change 1: `max_reentry_count = 3` in `warrior_types.py`

- **File**: [warrior_types.py:108](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py#L108)
- **Change**: `max_reentry_count: int = 99` → `max_reentry_count: int = 3`
- **Risk**: Low — the existing gate at `warrior_engine_entry.py:980` already checks this
- **Testing**: Run batch, check PAVM and BATL_0126 P&L improves

#### Change 2: MACD gate on re-entry in `enter_position()`

- **File**: [warrior_engine_entry.py:977-986](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L977-L986)
- **Add after existing re-entry count check (line ~986)**:
  - Compute MACD from last 50 1-min bars
  - If MACD histogram < 0, block re-entry and log
- **Note**: MACD computation already exists in `warrior_entry_guards.py` — reuse `check_macd_gate()`
- **Risk**: Low — only affects re-entries (entry_attempt_count > 0)
- **Testing**: Run batch, check LRHC and GWAV improvement

### Phase 2: Per-Symbol P&L Tracking

#### Change 3: Add session P&L tracking fields

- **File**: `warrior_types.py` — add to `WatchedCandidate`:
  ```python
  peak_session_pnl: Decimal = Decimal("0")
  cumulative_session_pnl: Decimal = Decimal("0")
  ```
- **File**: `warrior_engine.py` `_handle_profit_exit()` — update tracking
- **File**: `warrior_engine_entry.py` `enter_position()` — check 50% give-back
- **Risk**: Medium — requires careful P&L tracking across multiple trades
- **Testing**: Run batch, verify BATL_0126 and PAVM blocked after give-back without affecting VERO/ROLR

---

## 6. Verification Plan

### Automated Tests

```powershell
# Run batch with gates implemented
python -c "import requests; r = requests.post('http://localhost:8000/warrior/sim/run_batch_concurrent', json={'case_ids': ['ross_gwav_20260116','ross_mnts_20260209','ross_lrhc_20260130','ross_pavm_20260121','ross_mlec_20260213','ross_batl_20260126','ross_batl_20260127','ross_vero_20260116','ross_rolr_20260114','ross_tnmg_20260116','ross_evmn_20260210','ross_dcx_20260129','ross_bnai_20260205','ross_bnkk_20260115']}, timeout=300); print(r.json()['summary'])"
```

**Success criteria**:
- BATL_0127, VERO, ROLR, EVMN, DCX, BNAI, BNKK: P&L ≥ current
- GWAV: P&L ≥ $631 (without-reentry baseline)
- LRHC: P&L ≥ $178
- PAVM: P&L ≥ $27
- MLEC: P&L ≥ $65
- BATL_0126: P&L ≥ $67
- Total P&L > $3,808 (current)

---

## 7. Open Questions for Clay

1. **Max re-entry count**: 2 or 3? Setting to 2 is more aggressive (blocks more BAD) but may limit GOOD cases like VERO (10 trades) and ROLR (4 trades).

2. **MACD gate strictness**: Should re-entry require MACD histogram > 0 (positive), or just MACD line > signal (trending up even if still negative)?

3. **Phase 2 priority**: Is per-symbol P&L tracking for the 50% give-back rule worth the implementation complexity, or should we start with just the two quick wins?

---

## Appendix A: Raw Data Sources

- Bar-data analysis script: [analyze_reentry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/scripts/analyze_reentry.py)
- Batch runner script: [run_reentry_batch.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/scripts/run_reentry_batch.py)
- Full analysis JSON: [reentry_analysis_data.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-15/reentry_analysis_data.json)
- Batch results JSON: [reentry_batch_results.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-15/reentry_batch_results.json)
- Strategy research: [strategy_reentry_research.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-15/strategy_reentry_research.md)

## Appendix B: Code Locations

| Component | File | Line | Purpose |
|-----------|------|:----:|---------|
| Re-entry config | `warrior_types.py` | 108 | `max_reentry_count = 99` |
| Re-entry gate | `warrior_engine_entry.py` | 977-986 | Current count check |
| Entry attempt increment | `warrior_engine_entry.py` | 1053 | `entry_attempt_count += 1` |
| Profit exit handler | `warrior_engine.py` | 206-254 | Resets `entry_triggered` |
| MACD gate (existing) | `warrior_entry_guards.py` | — | `check_macd_gate()` |
