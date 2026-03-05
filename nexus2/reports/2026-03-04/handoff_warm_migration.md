# Warm Handoff: Workspace Migration (2026-03-04)

**From:** Antigravity session at old workspace (`C:\Users\ftbbo\Nextcloud4\...`)  
**To:** New Antigravity session at `C:\Dev\Nexus`

---

## What Just Happened

Projects moved from `C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\` to `C:\Dev\`. Encrypted `.env` backups added via `age`. All repos pushed.

## Current State (as of 2026-03-04 23:00 ET)

### Batch Test Baseline
- **P&L:** $382,890 | **Capture:** 84.2% | **Fidelity:** 50.0% | **Cases:** 40
- Baseline saved at 14:03 ET (before entry guard improvements)
- Entry guard improvements add +$17,443 net on top of baseline

### Today's Shipped Commits (Nexus)
1. `ef205b5` — Bar timestamp for PMH premarket filtering
2. `195be81` — EMA bar reversal + sanity check + adjusted=true
3. `8fc09cb` — Falling knife all patterns + vol avg fix + RVOL bypass removal + guard block tracking
4. `cbddd4d` — Per-process guard block tracking (infrastructure fix)
5. `dec7e30` — VCIG test case + mock market rules
6. `c0f8c04` — Reports, test cases, transcript (82 files)
7. `0246f41` — Encrypted .env backup (age)

### Open Items
| Item | Priority | Status |
|------|----------|--------|
| NPT regression (-$5,614) | Low | From earlier changes, not entry guards. Uninvestigated. |
| BCTX regression (-$504) | Low | Minor, same cause as NPT. |
| EMA 9 hard gate may over-block | Medium | Strategy says "NOT Used: EMA crossovers" but we have a hard gate. May be blocking good trades. |
| L2 gate defaults to log_only | Low | Platform has L2, not used in entry decisions. |
| Volume expansion scoring dead | Medium | 4% of score always neutral. |
| `gc_quick_test.py` cannot be run by agents | Infrastructure | Requires Clay's uvicorn server. All specialist handoffs must warn agents not to run it. |

### Key Files
- **Strategy file:** `.agent/strategies/warrior.md` — ground truth for Ross Cameron methodology
- **Technical audit:** `nexus2/reports/2026-03-04/research_technical_indicators_audit.md`
- **Validation:** `nexus2/reports/2026-03-04/validation_technical_indicators_audit.md`
- **GC persistent agents plan:** `nexus2/reports/2026-03-04/plan_gc_persistent_agents.md`

### Lesson Learned
The `guard_block_count` in batch tests was cross-contaminated via shared `nexus.db` in `ProcessPoolExecutor`. This wasted ~3 hours of investigation across 4 agent rounds. Fixed in `cbddd4d`.
