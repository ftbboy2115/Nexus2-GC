# Warrior Bot Benchmark Tracker

> **Living document.** Updated after each batch run to track iteration-over-iteration performance.
> **Maintained by:** Mock Market Specialist (after each batch run)

---

## Summary Timeline

| Date | Commit | Key Changes | Cases | Profitable | Bot P&L | Ross P&L | Capture % | Runtime | Notes |
|------|--------|-------------|------:|----------:|---------:|---------:|----------:|--------:|-------|
| Feb 14 | — | HOD break pattern (never triggered) | 29 | 15 (52%) | $1,570 | $412,026 | 0.4% | 43s | HOD_BREAK blocked on all cases; $250 risk sizing |
| Feb 16 | — | Ross-level risk sizing ($2K risk) | 29 | 19 (66%) | $53,923 | $412,026 | 13.1% | 35s | Proved scaling is linear (8x risk = 8x P&L) |
| Feb 18 | — | Exit tuning, pattern improvements | 30 | 18 (60%) | $101,256 | $413,626 | 24.5% | 155s | +1 case; big jump from exit logic changes |
| Feb 21 | 3eaacd9 | +5 test cases, trigger rejection logging | 35 | 23 (66%) | $120,889 | $433,000 | 27.9% | 93s | HIND $0→$14K; BCTX 96.7% capture |
| Feb 22 | 654b3f3 | RVOL slider, scanner persistence fix | 35 | 22 (63%) | $119,105 | $433,000 | 27.5% | 322s | BCTX flipped -$156; runtime 3.5x regression |
| Feb 23 | — | GC batch run | 35 | 22 (63%) | $118,983 | $433,000 | 27.5% | 291s | Auto-tracked by GC |
| Feb 27a | 2f3bc93 | ENVB P&L fix, +2 cases, scaling/exit improvements | 37 | 27 (73%) | $383,378 | $446,275 | 85.9% | 58s | 🚀 3x P&L jump; ENVB P&L corrected $0→$12.7K |
| Feb 27b | 2770fb3 | +1 case (BATL red day), catalyst AI fix deployed | 38 | 28 (73.7%) | $391,215 | $439,575 | 89.0% | 78s | New baseline; +$7.8K bot P&L from new case |
| **Mar 1** | **6506aaf** | **Batch settings separation (40K shares, 1min bars)** | **38** | **28 (73.7%)** | **$437,558** | **$439,575** | **99.5%** | **96s** | **🎯 Resolved $139K divergence; VPS=$435,454 (0.5% Δ)** |


---

## Key Metrics Over Time

```
Capture Rate:  0.4% → 13.1% → 24.5% → 27.9% → 27.5% → 85.9% → 89.0% → 99.5% 🎯
Bot P&L:       $1.6K → $53.9K → $101.3K → $120.9K → $119.1K → $383.4K → $391.2K → $437.6K 🎯
Win Rate:      52% → 66% → 60% → 66% → 63% → 73% → 73.7% → 73.7%
Runtime:       43s → 35s → 155s → 93s → 322s → 58s → 78s → 96s ✅
```

---

## Iteration Details

### Feb 14 — HOD Break Pattern Test
- **Risk config:** $250 risk, $5K max capital, 3K max shares
- **Result:** HOD_BREAK pattern had zero triggers across all 29 cases (3% consolidation threshold too tight)
- **Diagnosis:** Pattern requires tight consolidation; MLEC has 17.2% range
- **Report:** [batch_test_hod_break.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-14/batch_test_hod_break.md)

### Feb 16 — Ross-Level Sizing
- **Risk config:** $2,000 risk, $100K max capital, 20K max shares
- **Result:** 8x risk → ~8x P&L, confirming gap is entry timing + trade management, not position sizing
- **Key insight:** Scaling is perfectly linear; the 87% gap to Ross is entry/exit quality
- **Report:** [batch_ross_sizing_test.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-16/batch_ross_sizing_test.md)

### Feb 18 — Exit Logic Tuning
- **Changes:** Trail activation 10¢→15¢, 2-bar candle trail (was 1-bar), CUC skip when green
- **Result:** P&L nearly doubled from $54K → $101K; capture rate 13% → 24.5%
- **Key insight:** Exit timing improvements had massive P&L impact; ROLR captured 72.4%
- **Report:** [batch_test_warrior_sim.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-18/batch_test_warrior_sim.md)

### Feb 21 — New Test Cases + Trigger Logging
- **Changes:** +5 test cases (BCTX, SNSE, ENVB, MLEC Feb 20, EDHL), trigger rejection logging
- **Result:** HIND went from $0 to +$14,110 (biggest single-case improvement); BCTX at 96.7% capture
- **Key insight:** Code changes between Feb 18-21 enabled HIND entry; risk management turned 4 Ross losers into wins
- **Report:** [batch_benchmark_current_logic.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-21/batch_benchmark_current_logic.md)

### Feb 22 — RVOL Slider + Scanner Persistence
- **Changes:** RVOL configurable slider, scanner settings persistence (was in-memory only)
- **Result:** Slight regression — BCTX flipped from +$4,353 to -$156; 1 fewer profitable case
- **⚠️ Runtime regression:** 322s (was 93s) — needs investigation
- **Open question:** Did scanner persistence or trigger rejection DB writes cause the slowdown?

### Feb 27 — ENVB P&L Fix + New Baseline
- **Changes:** ENVB ross_pnl corrected from null→$12,716 (confirmed by Clay from video). +2 test cases (AIDX, NDRA). Multiple code improvements since Feb 23 (scaling v2, exit tuning, 10s bar pipeline, entry pattern updates).
- **Result:** 🚀 Bot P&L tripled: $119K → $383K. Capture rate 27.5% → 85.9%. Win rate 63% → 73%.
- **Runtime:** 58s (was 291s) — massive improvement, down to 1.6s/case avg.
- **Key insight:** Combined effect of many incremental improvements between Feb 23-27 produced a step-change in performance.
- **Data quality audit:** All 35 POLYGON_DATA cases have ross_pnl values. 1 NEEDS_VIDEO_CHECK (VELO), 12 TRANSCRIPT_PARTIAL, 20 missing data_quality field.

---

## Per-Case Stability Tracker

Cases that have changed direction or significantly shifted P&L between runs:

| Symbol | Feb 14 | Feb 16 | Feb 18 | Feb 21 | Feb 22 | Trend |
|--------|-------:|-------:|-------:|-------:|-------:|-------|
| HIND | $0 | $0 | $0 | +$14,110 | +$14,110 | 📈 Fixed in Feb 21 |
| BCTX | — | — | — | +$4,353 | -$156 | ⚠️ Flipped Feb 22 |
| VERO | +$14 | +$4,358 | +$19,072 | +$19,072 | +$19,072 | 📈 Stable top performer |
| ROLR | +$613 | +$10,610 | +$61,566 | +$61,566 | +$61,566 | 📈 Stable top performer |
| MNTS | +$18 | -$5,635 | -$6,544 | -$7,046 | -$4,320 | ⚠️ Unstable |

---

## Known Gaps (by P&L impact)

| Priority | Gap | Est. P&L Recovery | Affected Cases |
|----------|-----|------------------:|----------------|
| 1 | **Scaling/adds on strength** | +$100K+ | NPT, PAVM, MLEC, HIND, LRHC, ROLR |
| 2 | **Entry pattern coverage** | +$60K+ | HIND (partial), PRFX, VHUB |
| 3 | **Entry/exit timing** | +$40K+ | LCFY, MNTS, FLYE, SNSE |
| 4 | **MACD gate too strict on fast movers** | +$15K+ | SNSE, MLEC Feb 13 |

---

## Runtime History

| Date | Cases | Runtime | Per-Case Avg | Notes |
|------|------:|--------:|-------------:|-------|
| Feb 14 | 29 | 43s | 1.5s | Baseline |
| Feb 16 | 29 | 35s | 1.2s | Fastest ever |
| Feb 18 | 30 | 155s | 5.2s | ⚠️ 4x jump vs Feb 16 |
| Feb 21 | 35 | 93s | 2.7s | Improved vs Feb 18 |
| Feb 22 | 35 | 322s | 9.2s | ⚠️ Investigate regression |
| Feb 23 | 35 | 291s | 8.3s | ⚠️ Needs investigation |
| Feb 27a | 37 | 58s | 1.6s | ✅ Resolved — back to baseline |
| Feb 27b | 38 | 78s | 2.1s | ✅ Stable |
| **Mar 1** | **38** | **96s** | **2.5s** | ✅ Batch settings separation; VPS 1150s (NAC scanner contention) |
