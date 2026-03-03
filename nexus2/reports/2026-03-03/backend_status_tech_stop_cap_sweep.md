# Backend Status: Tech Stop Cap Sweep

**Agent:** Backend Specialist  
**Date:** 2026-03-03  
**Baseline:** $355,039 (39 cases, saved in baseline.json)

---

## Result: ❌ ALL CAP VALUES NET NEGATIVE — Cap Disabled

| Cap | Total P&L | Net Change | Improved | Regressed |
|-----|-----------|------------|----------|-----------|
| 10% | $233,234 | **-$121,805** | 12 | 27 |
| 15% | $276,816 | **-$78,223** | 13 | 26 |
| 20% | $275,628 | **-$79,411** | 14 | 25 |
| 25% | $262,029 | **-$93,010** | 11 | 28 |

**Best**: 15% cap (-$78K), **Worst**: 10% cap (-$122K). None are acceptable.

## Why the Cap Hurts

The cap tightens stops on **all** trades where the technical stop exceeds the threshold — not just bag-hold cases. This causes premature stop-outs on trades where the wide technical stop was *correct* and profitable.

### Top Regressions (15% cap)

| Case | Old P&L | New P&L | Change | Analysis |
|------|---------|---------|--------|----------|
| NPT | $68,021 | $45,361 | **-$22,660** | Wide stop was correct — stock pulled back then ran |
| TNMG | $8,630 | -$9,384 | **-$18,014** | Capped stop caused early exit on volatile pullback |
| ROLR | $45,723 | $35,862 | **-$9,862** | Tighter stop cut the run short |
| PRFX | $25,200 | $16,800 | **-$8,400** | Same pattern — stop too tight for the range |
| PAVM | $19,047 | $11,051 | **-$7,996** | Lost momentum opportunity |

### Top Improvements (15% cap)

| Case | Old P&L | New P&L | Change | Analysis |
|------|---------|---------|--------|----------|
| MLEC | -$578 | $18,164 | **+$18,743** | Cap prevented bag-hold, caught re-entry |
| MNTS | -$15,503 | -$3,860 | **+$11,643** | The original bug case — cap saves $11.6K |
| ONCO | -$12,150 | -$3,400 | **+$8,750** | Another wide-stop bag-hold prevented |
| EVMN | $42,355 | $49,552 | **+$7,197** | Tighter stop triggered better re-entry |
| UOKA | -$10,635 | -$7,090 | **+$3,545** | Partial bag-hold reduction |

### The Fundamental Problem

The cap helps **6-8 bag-hold cases** but hurts **25+ winning trades**. The wide technical stop (candle low) is Ross Cameron's actual methodology — it gives trades room to work through normal volatility. A blanket percentage cap removes this room, converting winners into losers.

## Implementation

### Code Changes Made

1. **`warrior_types.py:66`** — Added `tech_stop_max_pct: float = 0.0` setting (disabled)
2. **`warrior_monitor.py:420-430`** — Added cap logic in `_create_new_position()`:
   - After `technical_stop` is calculated from `support_level`, checks if stop distance exceeds `tech_stop_max_pct`
   - If exceeded, clamps `technical_stop` to `entry_price * (1 - cap)`
   - Logs WARNING with original and capped values
   - Guard: `tech_stop_max_pct = 0` disables the cap entirely

### Setting: Disabled (0.0)

Per handoff instructions: *"If NO cap value is net positive, report findings and leave the cap disabled."*

The setting is tunable via the `WarriorMonitorSettings` dataclass and can be re-enabled for future testing via API.

## Recommendation

Instead of a blanket percentage cap, consider **targeted approaches** for the bag-hold cases:
1. **Smarter consolidation window** — Skip sparse premarket bars (MNTS had 200-share bars setting the low)
2. **Volume-weighted candle low** — Ignore bars with trivially low volume when computing the consolidation low
3. **Dynamic cap tied to volatility** — Use ATR-based cap instead of fixed percentage
4. **Entry quality gate** — Block entries where the consolidation range is too wide relative to price

These approaches would fix the bag-hold cases without globally tightening stops on winning trades.

## Raw Data

Full per-case breakdown: [`sweep_tech_stop_cap_raw.json`](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-03-03/sweep_tech_stop_cap_raw.json)
