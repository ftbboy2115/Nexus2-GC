# Findings: Winner-to-Loser Investigation

**Date:** 2026-02-16
**Config:** risk=$2,500, max_shares=10,000, enable_partial_then_ride=True, enable_scaling=True (accidental 1-scale)
**Combined Gap:** -$90,796 across 5 cases

---

## Executive Summary

All 5 cases share **three compounding failure modes** that systematically turn Ross's winners into bot losses:

1. **Immediate 50% scaling** — Every entry is instantly followed by a 50% add before the trade confirms, amplifying all losses by 1.5x
2. **Re-entries into failing trades** — Bot re-enters the same symbol after being stopped out, often with larger size, compounding losses
3. **Wrong entry price/timing vs Ross** — Bot enters at different prices and times than Ross, often chasing breakouts instead of buying dips

---

## Per-Case Breakdown

### 1. LCFY — Bot: -$4,833 vs Ross: +$10,457 (Δ -$15,290)

| Field | Bot | Ross |
|-------|-----|------|
| Entry price | $4.96 | ~$7.50 |
| Entry time | **14:59** (end of day!) | Morning |
| Entry trigger | `whole_half_anticipatory` | PMH break |
| Shares | 5,555 → **8,332** (scaled) | ~10,000 |
| Exit price | $4.38 @ 15:32 | Profitable exit |

**Root Cause:** The bot entered at **2:59 PM** — the stock had already crashed from $7.42 PMH to $4.96. The `whole_half_anticipatory` trigger fired on the $5.00 whole-dollar level during the decline. Ross traded the morning PMH break near $7.50.

**Damage Breakdown:**
- Wrong timing: Bot entered ~6 hours after Ross, during a selloff
- Scaling amplified: 5,555 → 8,332 shares at the wrong price
- Loss: 8,332 × ($4.96 - $4.38) = **-$4,833**

---

### 2. FLYE — Bot: -$3,866 vs Ross: +$4,800 (Δ -$8,666)

| Field | Bot | Ross |
|-------|-----|------|
| Entry price | $7.11 | ~$6.32 |
| Entry time | 09:02 | ~08:50 |
| Entry trigger | `hod_break` | Starter on curl |
| Shares | 877 → **1,315** (scaled) | Variable (add/trim) |
| Exit price | $4.17 @ 11:03 | Profitable exits $7-$8.50 |

**Root Cause:** Bot entered $0.79 higher than Ross on an `hod_break` trigger ($7.11 vs Ross's $6.32 starter). When the stock reversed from ~$8.50 all the way to $4.17, the bot held through a **$2.94/share** drawdown. Ross used multiple add/trim cycles ($7→$7.50→$8→$8.50) and took profits.

**Damage Breakdown:**
- Higher entry: $7.11 vs Ross $6.32 = $0.79 worse per share
- No partial exits: Bot held full 1,315 shares through reversal
- Scaling amplified: 877 → 1,315 shares at wrong price
- Loss: 1,315 × ($7.11 - $4.17) = **-$3,866**

---

### 3. MNTS — Bot: -$7,046 vs Ross: +$9,000 (Δ -$16,046)

| Field | Bot | Ross |
|-------|-----|------|
| Entry 1 | $7.67 x1,381 @ 08:40 (`dip_for_level`) | ~$8.00 dip buy |
| Scale 1 | $7.67 x690 (immediate 50% add) | — |
| **Re-entry** | **$6.90 x5,102 @ 13:08** (`hod_break`) | No re-entry |
| Final exit | **$6.14 x7,173 @ 19:30** (EOD!) | Sold ~$9 |
| Total shares | **7,173** | ~10,000 |

**Root Cause:** First entry at $7.67 was reasonable. But the stock dropped, and the bot **re-entered at 1:08 PM** with 5,102 additional shares at $6.90 on an `hod_break` trigger (HOD at this point was much lower). Then it held **everything until EOD close at $6.14**.

**Damage Breakdown:**
- Entry 1 loss: 2,071 × ($7.67 - $6.14) = -$3,169
- Re-entry loss: 5,102 × ($6.90 - $6.14) = -$3,877
- **Re-entry caused 55% of total loss**
- EOD close at worst price of day

---

### 4. BNRG — Bot: -$4,526 vs Ross: +$272 (Δ -$4,797)

| Field | Bot | Ross |
|-------|-----|------|
| Entry price | **$3.45** | ~$4.00 |
| Entry time | **06:48** | ~07:00 |
| Entry trigger | `dip_for_level` | VWAP reclaim |
| Shares | 8,620 → **12,930** (scaled) | ~10,000 |
| Exit price | $3.10 @ 07:02 | ~$4.03 (near breakeven) |

**Root Cause:** Ross waited for **VWAP reclaim at $4.00** and got out quickly for +$272. The bot entered at $3.45 on a `dip_for_level` trigger — **before VWAP was reclaimed**, 55 cents below Ross's entry. Then immediately scaled to 12,930 shares. The stock dropped to $3.10 within 14 minutes.

**Damage Breakdown:**
- Wrong price: $3.45 vs Ross $4.00 (entered too low, wrong setup)
- Massive sizing: 12,930 shares at $3.45 (low price = huge share count)
- Quick stop: $3.10 was only $0.35 below, but 12,930 × $0.35 = **-$4,526**
- Ross only risked ~$271 on a small, quick scalp

---

### 5. MLEC — Bot: -$2,997 vs Ross: +$43,000 (Δ -$45,997)

| Field | Bot | Ross |
|-------|-----|------|
| Entry 1 | $8.71 x608 @ 08:11 (`hod_break`) + scale x304 | ~$7.90 HOD break |
| Partial sells | $9.44 x456, $8.62 x456 | Sold ~$10.09-$10.14 |
| **Re-entry 2** | **$10.12 x2,083 @ 11:38** + scale x1,041 | No re-entry |
| Sells | $11.00 x1,562, $9.96 x1,562 | — |
| **Re-entry 3** | **$8.76 x4,416 @ 15:39** + scale x2,208 | No re-entry |
| Final exit | **$8.09 x6,624 @ 16:07** | — |
| Total entries | **6** (3 entries + 3 scales) | 1 entry + 1 add |

**Root Cause:** The first entry at $8.71 actually worked — partial exits at $9.44 were profitable. But the bot **re-entered twice more with escalating size**: 2,083 shares at $10.12, then 4,416 shares at $8.76. Each re-entry was scaled 50%. The 3rd entry (6,624 shares at $8.76) was the killer — exited at $8.09 for -$4,435.

**Damage Breakdown:**
- Entry 1 P&L: 608 shares, small profit then small loss ≈ **~net even**
- Entry 2 P&L: 3,124 shares, mixed results ≈ **~net even**
- Entry 3 P&L: 6,624 × ($8.76 - $8.09) = **-$4,435** ← ALL the damage
- **3rd re-entry at 3:39 PM with 6,624 shares caused the entire loss**

---

## Common Patterns Across All 5 Cases

### Pattern 1: Immediate 50% Scaling (ALL 5 cases)

Every single entry is immediately followed by a 50% scale add at the same price and same minute. This happens before the trade has any confirmation.

| Case | Initial Shares | After Scale | Amplification |
|------|---------------|-------------|---------------|
| LCFY | 5,555 | 8,332 | 1.5x |
| FLYE | 877 | 1,315 | 1.5x |
| MNTS | 1,381 | 2,071 | 1.5x |
| BNRG | 8,620 | 12,930 | 1.5x |
| MLEC | 608 | 912 | 1.5x |

**Impact:** All losses are 50% larger than they should be. Without scaling, total losses would be ~-$15,500 instead of -$23,268 — saving ~$7,768.

### Pattern 2: Re-entries Compound Losses (3 of 5 cases)

| Case | Entries | Re-entry % of Loss | Re-entry Timing |
|------|---------|-------------------|-----------------|
| MNTS | 3 | **55%** ($3,877 of $7,046) | 13:08 — 4.5 hrs after entry 1 |
| MLEC | 6 | **100%** (entry 3 at 15:39 caused all loss) | 15:39 — 7.5 hrs after entry 1 |
| LCFY | 2 | 0% (scaling, not re-entry) | — |
| FLYE | 2 | 0% (scaling, not re-entry) | — |
| BNRG | 2 | 0% (scaling, not re-entry) | — |

**Impact:** Without MNTS re-entry and MLEC re-entries 2+3, the combined loss drops from -$23,268 to approximately **-$12,400** — saving ~$10,868.

### Pattern 3: Wrong Entry Price vs Ross

| Case | Bot Entry | Ross Entry | Gap | Direction |
|------|-----------|------------|-----|-----------|
| LCFY | $4.96 | $7.50 | **-$2.54** | Below (crashed) |
| FLYE | $7.11 | $6.32 | +$0.79 | Above (chased) |
| MNTS | $7.67 | $8.00 | -$0.33 | Below (close) |
| BNRG | $3.45 | $4.00 | -$0.55 | Below (wrong setup) |
| MLEC | $8.71 | $7.90 | +$0.81 | Above (late) |

### Pattern 4: Late-Day / EOD Exits

| Case | Exit Time | Context |
|------|-----------|---------|
| MNTS | **19:30** | Held to EOD close — worst price of day |
| MLEC | **16:07** | 3rd re-entry at 15:39, exited 28 min later |
| LCFY | **15:32** | Entered at 14:59, exited 33 min later |

---

## Quantified Impact by Failure Mode

| Failure Mode | Estimated P&L Recovery | Priority |
|-------------|----------------------|----------|
| **Disable accidental scaling** | +$7,768 (est.) | 🔴 HIGH — flip a toggle |
| **Block re-entries into losers** | +$10,868 (est.) | 🔴 HIGH — re-entry quality gate |
| **Fix entry timing/triggers** | +$15,000+ (est.) | 🟡 MEDIUM — requires trigger logic changes |
| **Earlier exits / tighter stops** | +$5,000+ (est.) | 🟡 MEDIUM — stop/trail improvements |

---

## Prioritized Recommendations

### 1. 🔴 Disable Accidental Scaling (Quick Win)
Set `enable_scaling=False` or fix the scaling guard. Every case shows instant 50% scaling with zero confirmation. This is the "accidental 1-scale" mentioned in the handoff.

### 2. 🔴 Re-entry Quality Gate
Block re-entries that:
- Happen >2 hours after the first entry (MNTS 13:08, MLEC 15:39)
- Are into a symbol that already lost money
- Have escalating size (MLEC: 608 → 2,083 → 4,416)

### 3. 🟡 Entry Trigger Accuracy
- LCFY entered on `whole_half_anticipatory` at $5.00 during a crash — this trigger shouldn't fire when price is far below PMH
- BNRG entered on `dip_for_level` before VWAP reclaim — setup mismatch for `vwap_reclaim` case
- FLYE/MLEC entered on `hod_break` above Ross's price — acceptable but suboptimal

### 4. 🟡 Stop/Exit Improvements
- MNTS held to 19:30 EOD — should have been stopped out much earlier
- FLYE held from $7.11 to $4.17 ($2.94 drawdown, 41%) — no trailing stop engaged
- These are partially addressed by the existing Fix 1-4 improvements

---

## Data Source

Full trade data: [data_winner_to_loser.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-16/data_winner_to_loser.json)

Investigation script: [investigate_winner_to_loser.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/scripts/investigate_winner_to_loser.py)
