# Investigation: Entry Guard Regression Root Cause

**Date:** 2026-03-04 19:20 ET  
**Investigator:** Backend Specialist  
**Status:** In-progress — findings with evidence

---

## Question 1: Is BNRG solo P&L actually -$9,704?

**YES — verified via two independent solo runs.**

**Evidence A:** `gc_quick_test.py ross_bnrg_20260211 --trades` (Clay ran at ~18:46 ET):
```
BNRG 2026-02-11 | Bot: $ -9,704.64 | Ross: $    271.74
Entry: $3.4 @ 2026-02-11T08:04:00Z
Exit:  $2.52 @ 2026-02-11T08:14:00Z
Trigger: vwap_break | Exit: technical_stop
Shares: 11028
```

**Evidence B:** `/tmp/dump_guard_blocks.py ross_bnrg_20260211` (Clay ran at ~18:57 ET):
```
Case: ross_bnrg_20260211 | P&L: $-9,704.64
Guard blocks: 0
```

**Both solo runs confirm P&L = -$9,704.64.** The P&L comes from MockBroker (per-process in-memory, `sim_context.py:728-731`), so concurrency cannot affect P&L.

---

## Question 2: Is guard_block_count cross-contaminated?

**PARTIALLY PROVEN — the shared DB path is confirmed, but the 0-vs-64 discrepancy needs explanation.**

### What IS proven (code evidence):

1. **Guard blocks write to shared `nexus.db`:**
   - [trade_event_service.py:1036-1044](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/trade_event_service.py#L1036-L1044): `log_warrior_guard_block()` → `_log_event()`
   - [trade_event_service.py:345](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/trade_event_service.py#L345): `_log_event()` → `with get_session() as db:`
   - [database.py:18-23](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/database.py#L18-L23): `get_session()` → `SessionLocal` bound to file-based `data/nexus.db`

2. **Concurrent runner only replaces warrior_db, NOT nexus.db:**
   - [sim_context.py:608-611](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L608-L611): Only `wdb.warrior_engine` and `wdb.WarriorSessionLocal` are replaced with in-memory
   - `nexus2.db.database.SessionLocal` is NOT replaced → still points to `data/nexus.db`

3. **Guard block READ has no date/run filter:**
   - [sim_context.py:770-774](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L770-L774): Filters only `event_type == "GUARD_BLOCK"` and `symbol == symbol.upper()` — no date, no run_id, no timestamp filter
   - Result: picks up ALL historical blocks for that symbol from every previous run

4. **No cleanup between runs:**
   - Searched for `delete`, `clear`, `truncat` near `GUARD_BLOCK` — no results. Blocks accumulate indefinitely.

5. **DB confirms accumulation:**
   - Clay's query showed **64 BNRG GUARD_BLOCK events** in nexus.db
   - All are `HIGH-VOL RED CANDLE guard` at premarket sim times (06:26, 06:48, 07:00)

### What is NOT explained:

The solo API run returned `guard_blocks: 0` despite 64 blocks existing in nexus.db. Possible causes:
- The spawned subprocess (via `ProcessPoolExecutor(mp_context="spawn")`) creates a fresh Python interpreter where `database.py` re-initializes — it should connect to the same file, but SQLite file locks or WAL mode may prevent reading
- The `except Exception` at [sim_context.py:790-791](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L790-L791) may silently swallow an error

> [!WARNING]
> **I cannot definitively prove the subprocess DB behavior without running Python in the venv.** The exact mechanism needs a test with logging inside the subprocess's guard block read.

---

## Question 3: Baseline vs current P&L in solo runs

**BASELINE is not from a solo run — it's from a concurrent `--all --save` at 14:03:02.**

### Verified baseline data (Clay extracted from `baseline.json`):
```json
{
  "case_id": "ross_bnrg_20260211",
  "total_pnl": 360.50,
  "guard_block_count": 10
}
```

### Current solo run:
```
total_pnl: -9,704.64
guard_blocks: 0 (from API) / 64 (from DB query)
```

### The regression is real: $360.50 → -$9,704.64

The P&L comes from MockBroker which is per-process in-memory (`sim_context.py:728-731`), so the P&L difference is NOT from concurrency — it's from a code change between baseline (14:03) and now. 

**The P&L computation is deterministic and per-process.** Running BNRG solo produces the same -$9,704.64 as the `--all` concurrent run. This means both guard_block_count AND the regression are happening consistently.

### What changed between baseline (14:03) and now?

Changes made today (from conversation history):
1. **~14:42** - Entry guard fixes: PMH derivation, price floor, cooldown unification
2. **~15:45** - My fixes: RVOL bypass removal, falling knife threshold alignment  
3. **~16:55** - EMA fix: bar reversal removal, adjusted=true for Polygon daily bars

The BNRG entry shows: `entry_trigger: vwap_break`, `stop_method: consolidation_low_capped`, entry at $3.40. The baseline doesn't have trade details (no `--trades`), so I can't compare entry prices.

---

## What I Know vs What I Don't Know

| Claim | Status | Evidence |
|-------|--------|----------|
| BNRG P&L = -$9,704.64 solo | ✅ PROVEN | Two independent solo runs |
| Guard blocks write to shared nexus.db | ✅ PROVEN | Code trace: `trade_event_service.py:1036` → `database.py:18-23` |
| Only warrior_db replaced with in-memory | ✅ PROVEN | `sim_context.py:608-611` — no nexus.db replacement |
| Guard block read has no date filter | ✅ PROVEN | `sim_context.py:770-774` |
| 64 BNRG blocks in nexus.db | ✅ PROVEN | Clay's DB query output |
| Subprocess returns 0 blocks from API | ✅ OBSERVED | Two solo runs confirmed |
| WHY subprocess returns 0 | ❌ UNPROVEN | Need venv subprocess test |
| WHICH code change caused BNRG regression | ❌ UNPROVEN | Need to bisect (requires reverting changes) |
| DB blocks ARE from premarket (pre-entry) | ✅ PROVEN | Timestamps: 06:26, 06:48, 07:00; entry at 08:04 |
| Falling knife threshold fix was correct | ✅ PROVEN | Code verified at `warrior_entry_guards.py:352-354` |
| RVOL bypass removal was correct | ✅ PROVEN | RVOL=10.0 in sim (`sim_context.py:283`); gate should be unconditional per warrior.md §8.1 |

## Next Steps

1. **Fix the guard_block_count bug** — add a run_id or date filter, or use per-process storage instead of shared nexus.db
2. **Bisect the BNRG regression** — requires reverting changes one-by-one to find which caused the $360 → -$9,704 swing
3. **Add logging to subprocess guard block read** to explain the 0-vs-64 discrepancy
