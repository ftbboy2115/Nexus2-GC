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

---

## Key Metrics Over Time

```
Capture Rate:  0.4% → 13.1% → 24.5% → 27.9% → 27.5%
Bot P&L:       $1.6K → $53.9K → $101.3K → $120.9K → $119.1K
Win Rate:      52% → 66% → 60% → 66% → 63%
Runtime:       43s → 35s → 155s → 93s → 322s ⚠️
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

> [!WARNING]
> Runtime has regressed from ~35s to 322s over 2 weeks. Needs profiling investigation.
