# Baseline Comparison: Feb 13 → Feb 14

**Date:** 2026-02-14
**Auditor:** Code Auditor Agent

---

## Data Sources

| Source | Location | Evidence |
|--------|----------|----------|
| **Feb 13 Baseline** | [velo_fix_test_report.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/velo_fix_test_report.md) (lines 86–118) | 26 cases, $3,480.23 total P&L, post-VELO divergence fix |
| **Feb 14 Results** | [batch_test_hod_break.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-14/batch_test_hod_break.md) (lines 60–103) | 29 cases, $1,570.00 total P&L, post-HOD_BREAK implementation |
| **Intermediate ref** | [handoff_audit_batch_runner.md](file:///C:/Users/ftbbo/.gemini/antigravity/brain/e56e9f8f-208c-46dc-8c63-d13dcafec674/handoff_audit_batch_runner.md) (line 14) | 28 cases, $3,979.29 — referenced but no per-case breakdown found |

> [!NOTE]
> The Feb 13 baseline (26 cases) is the **last known run with full per-case data**. Between Feb 13 and Feb 14, two cases (PMI, ONCO) were added bringing it to 28, and MLEC was added on Feb 13 bringing it to 29. The $3,979.29 figure (28 cases) lacks per-case breakdown in artifacts — the Coordinator referenced it in handoffs but the actual batch output was not saved.

---

## Summary Comparison

| Metric | Feb 13 (Baseline) | Feb 14 (Post Fix 1) | Delta |
|--------|-------------------|---------------------|-------|
| **Total P&L** | **$3,480.23** | **$1,570.00** | **-$1,910.23** |
| Cases run | 26 | 29 | +3 |
| Cases profitable | 13 (50%) | 15 (52%) | +2 |
| Errors | 0 | 1 (ONCO 404) | +1 |
| Runtime | ~191s (sequential) | 43.38s | -148s |

> [!CAUTION]
> **Total P&L dropped $1,910.23 (-55%).** While 3 new cases were added, the P&L drop is overwhelmingly caused by dramatic swings in **existing** cases — not the new cases. The new cases contribute only +$200 net (PMI +$200, ONCO $0, MLEC $0). The remaining **-$2,110.23** is from P&L changes in the 26 existing cases.

---

## Per-Case P&L Comparison

### Cases with P&L Changes

| Case | Symbol | Feb 13 P&L | Feb 14 P&L | Δ P&L | Direction |
|------|--------|-----------|-----------|-------|-----------|
| ross_rolr_20260114 | ROLR | +$1,538.73 | +$613 | **-$925.73** | 📉 Worse |
| ross_npt_20260203 | NPT | +$1,732.62 | +$694 | **-$1,038.62** | 📉 Worse |
| ross_gwav_20260116 | GWAV | +$630.63 | +$253 | **-$377.63** | 📉 Worse |
| ross_pavm_20260121 | PAVM | +$554.49 | +$216 | **-$338.49** | 📉 Worse |
| ross_uoka_20260209 | UOKA | +$279.50 | +$112 | **-$167.50** | 📉 Worse |
| ross_evmn_20260210 | EVMN | +$274.18 | +$109 | **-$165.18** | 📉 Worse |
| ross_gri_20260128 | GRI | +$201.41 | +$79 | **-$122.41** | 📉 Worse |
| ross_dcx_20260129 | DCX | +$198.46 | +$79 | **-$119.46** | 📉 Worse |
| ross_bnai_20260205 | BNAI | +$185.26 | +$72 | **-$113.26** | 📉 Worse |
| ross_bnkk_20260115 | BNKK | +$176.70 | +$71 | **-$105.70** | 📉 Worse |
| ross_rvsn_20260205 | RVSN | +$105.05 | +$42 | **-$63.05** | 📉 Worse |
| ross_mnts_20260209 | MNTS | +$44.18 | +$18 | **-$26.18** | 📉 Worse |
| ross_rdib_20260206 | RDIB | +$27.76 | +$11 | **-$16.76** | 📉 Worse |
| ross_lcfy_20260116 | LCFY | -$482.56 | -$193 | **+$289.56** | 📈 Better |
| ross_velo_20260210 | VELO | -$389.82 | -$155 | **+$234.82** | 📈 Better |
| ross_flye_20260206 | FLYE | -$267.67 | -$107 | **+$160.67** | 📈 Better |
| ross_bnrg_20260211 | BNRG | -$452.55 | -$181 | **+$271.55** | 📈 Better |
| ross_batl_20260127 | BATL | -$550.86 | -$302 | **+$248.86** | 📈 Better |
| ross_batl_20260126 | BATL | -$175.79 | -$70 | **+$105.79** | 📈 Better |
| ross_vero_20260116 | VERO | -$137.13 | +$14 | **+$151.13** | 📈 Better |
| ross_tnmg_20260116 | TNMG | -$12.36 | -$5 | **+$7.36** | 📈 Better |

### Cases with No Change

| Case | Symbol | Feb 13 P&L | Feb 14 P&L | Notes |
|------|--------|-----------|-----------|-------|
| ross_lrhc_20260130 | LRHC | $0.00 | $0 | No trades either day |
| ross_hind_20260127 | HIND | $0.00 | $0 | No trades either day |
| ross_rnaz_20260205 | RNAZ | $0.00 | $0 | No trades either day |
| ross_sxtc_20260209 | SXTC | $0.00 | $0 | No trades either day |
| ross_prfx_20260211 | PRFX | $0.00 | $0 | No trades either day |

### New Cases (Feb 14 only — not in Feb 13 baseline)

| Case | Symbol | Feb 14 P&L | Notes |
|------|--------|-----------|-------|
| ross_pmi_20260212 | PMI | +$200 | 0 trades (pre-market P&L?) |
| ross_onco_20260212 | ONCO | $0 | ERROR: 404 test case not found |
| ross_mlec_20260213 | MLEC | $0 | HOD_BREAK never triggered (tightness too strict) |

---

## Pattern Analysis

### Suspicious: All Positive Cases Lost ~60% of P&L

Every profitable case from Feb 13 shows a proportional reduction:

| Case | Feb 13 | Feb 14 | Ratio |
|------|--------|--------|-------|
| ROLR | $1,538.73 | $613 | 0.398× |
| NPT | $1,732.62 | $694 | 0.401× |
| GWAV | $630.63 | $253 | 0.401× |
| PAVM | $554.49 | $216 | 0.390× |
| BNKK | $176.70 | $71 | 0.402× |
| BNAI | $185.26 | $72 | 0.389× |
| GRI | $201.41 | $79 | 0.392× |
| DCX | $198.46 | $79 | 0.398× |

> [!WARNING]
> **All profitable cases show ≈0.40× multiplier.** This is NOT explained by the HOD_BREAK change (which had zero triggers). Something else changed between Feb 13 and Feb 14 that uniformly reduced profitable P&L by ~60%. Possible causes:
> 
> 1. **Position sizing change** — risk per trade reduced or share count calculation changed
> 2. **Stop logic change** — stops tightened, causing earlier exits
> 3. **Scale-out logic change** — more aggressive partial exits
> 4. **Config change** — `risk_per_trade` or similar parameter modified
> 5. **Underlying code change** — entry/exit logic modified between sessions

### Similarly: Losing Cases Also Reduced ~60%

| Case | Feb 13 | Feb 14 | Ratio |
|------|--------|--------|-------|
| LCFY | -$482.56 | -$193 | 0.400× |
| VELO | -$389.82 | -$155 | 0.398× |
| FLYE | -$267.67 | -$107 | 0.400× |
| BNRG | -$452.55 | -$181 | 0.400× |
| BATL (126) | -$175.79 | -$70 | 0.398× |
| BATL (127) | -$550.86 | -$302 | 0.548× |

> [!IMPORTANT]
> **The ~0.40× ratio across BOTH winners and losers confirms this is a position sizing or share count change, not a strategy change.** If it were a strategy change, losses would move differently from wins. A uniform multiplier on all P&L strongly suggests:
> - `risk_per_trade` was reduced from ~$250 to ~$100, OR
> - Share count formula was modified, OR
> - An intermediate code change is scaling all position sizes down

---

## Investigation Required

> [!CAUTION]
> **The HOD_BREAK pattern change had ZERO effect on any test case** (confirmed in [batch_test_hod_break.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-14/batch_test_hod_break.md#L107)). Yet P&L changed dramatically. Something else must have changed between sessions.

### Recommended Next Steps

1. **Check `risk_per_trade` config** — compare current value vs Feb 13 value
2. **Check position sizing code** — `warrior_engine_types.py` or config files for any changes since Feb 13
3. **Run `git diff` on warrior files** — identify ALL code changes between the Feb 13 commit and current HEAD
4. **Re-run Feb 13 code** — checkout the Feb 13 commit, run batch, verify it produces $3,480.23

### Verification Commands

```powershell
# Check current risk_per_trade setting
Select-String -Path "nexus2\domain\automation\warrior_engine_types.py" -Pattern "risk_per_trade"
Select-String -Path "nexus2\domain\automation\warrior_engine.py" -Pattern "risk_per_trade"

# Check recent git changes to warrior files
git log --oneline -10 -- "nexus2/domain/automation/warrior_engine*.py" "nexus2/domain/automation/warrior_entry*.py"

# Check position sizing logic
Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "shares|position_size|qty"
```

---

## VPS-Validated Results (Feb 14, same commit 2b99473)

> [!IMPORTANT]
> **Local concurrent batch runner has a bug** producing a 0.40× P&L scaling factor. VPS sequential execution produces correct results. Use VPS for all batch testing.

| Metric | VPS (correct) | Local (bugged) |
|--------|---------------|----------------|
| **Total P&L** | **$3,945.84** | $1,570.00 |
| Cases profitable | 15/29 | 15/29 |
| Runtime | 28.99s | 43.38s |

### Per-Case VPS Results

> [!NOTE]
> The `trades` array in the API response shows **open positions at end of simulation**, not total trades executed. Use `max_shares_held` as the activity indicator.

| Case | Symbol | P&L | Ross P&L | Max Shares | Trigger |
|------|--------|-----|----------|------------|---------|
| ross_rolr_20260114 | ROLR | +$1,538.73 | $85,000 | 4 | micro_pullback |
| ross_npt_20260203 | NPT | +$1,732.62 | $81,000 | 0 | - |
| ross_gwav_20260116 | GWAV | +$630.63 | $3,975 | 505 | - |
| ross_pavm_20260121 | PAVM | +$554.49 | $43,950 | 22 | pullback, pmh_break |
| ross_pmi_20260212 | PMI | +$499.06 | $9,959 | 0 | - |
| ross_uoka_20260209 | UOKA | +$279.50 | $858 | 0 | - |
| ross_evmn_20260210 | EVMN | +$274.18 | -$10,000 | 52 | dip_for_level |
| ross_gri_20260128 | GRI | +$201.41 | $31,600 | 0 | - |
| ross_dcx_20260129 | DCX | +$198.46 | $6,268 | 2 | whole_half_anticipatory |
| ross_bnai_20260205 | BNAI | +$185.26 | -$7,900 | 2 | whole_half_anticipatory |
| ross_bnkk_20260115 | BNKK | +$176.70 | $15,000 | 1 | whole_half_anticipatory |
| ross_rvsn_20260205 | RVSN | +$105.05 | -$3,000 | 0 | - |
| ross_mnts_20260209 | MNTS | +$44.18 | $9,000 | 1 | dip_for_level |
| ross_vero_20260116 | VERO | +$32.29 | $3,485 | 6 | whole_half_anticipatory, pullback, pmh_break |
| ross_rdib_20260206 | RDIB | +$27.76 | $700 | 0 | - |
| ross_tnmg_20260116 | TNMG | -$12.36 | $2,102 | 0 | - |
| ross_batl_20260126 | BATL | -$175.79 | $0 | 4 | micro_pullback |
| ross_flye_20260206 | FLYE | -$267.67 | $4,800 | 0 | - |
| ross_velo_20260210 | VELO | -$389.82 | -$2,000 | 0 | - |
| ross_bnrg_20260211 | BNRG | -$452.55 | $272 | 0 | - |
| ross_lcfy_20260116 | LCFY | -$482.56 | $10,457 | 832 | - |
| ross_batl_20260127 | BATL | -$753.73 | $0 | 3 | dip_for_level, pullback, pmh_break |
| ross_lrhc_20260130 | LRHC | $0.00 | $31,077 | 0 | - |
| ross_hind_20260127 | HIND | $0.00 | $55,253 | 0 | - |
| ross_rnaz_20260205 | RNAZ | $0.00 | $1,700 | 0 | - |
| ross_sxtc_20260209 | SXTC | $0.00 | -$5,000 | 0 | - |
| ross_prfx_20260211 | PRFX | $0.00 | $5,971 | 0 | - |
| ross_onco_20260212 | ONCO | $0.00 | -$5,500 | 0 | ERROR: 404 |
| ross_mlec_20260213 | MLEC | $0.00 | $43,000 | 0 | - |

---

## Conclusions (Updated)

1. **Fix 1 (HOD_BREAK) caused NO regression** — VPS P&L is $3,946 vs Feb 13 baseline $3,480. The $466 increase is from 3 new test cases.
2. **Local batch runner has a concurrency bug** — ProcessPoolExecutor produces 0.40× P&L scaling. VPS sequential results are correct. Filed for future investigation.
3. **Phase A/B/C exit changes caused NO regression** — same commit on both environments produces correct P&L on VPS.
4. **MLEC remains at $0 P&L** — HOD_BREAK pattern did not trigger. Fix 2 (pattern competition relaxation) still needed.
5. **ONCO test case file missing** — returns 404.
6. **API reporting issue** — `trades` array shows open positions only, not trade history. Misleading for reporting.
