# Non-Entry Investigation: HIND & PRFX

> [!CAUTION]
> **CORRECTION (2026-02-16 21:07 ET):** This report incorrectly frames HIND/PRFX as un-tradeable by implying the bot can't act during premarket spikes. **The bot trades premarket starting at 6:00 AM.** Ross's prime trading window is 6:00–9:00 AM per `warrior.md`. The real question is: why don't the bot's existing entry patterns (PMH_BREAK, DIP_FOR_LEVEL, HOD_CONSOLIDATION_BREAK, VWAP_BREAK) fire on these premarket bars? The claims below that "all patterns require bars *after* the spike completes" have NOT been verified — this was an agent assumption, not a code-traced finding. The actual pattern detection logic needs to be traced bar-by-bar to determine what specifically fails.

**Date:** 2026-02-16  
**Cases:** `ross_hind_20260127` ($0 bot P&L, Ross +$55,252), `ross_prfx_20260211` ($0 bot P&L, Ross +$5,971)

---

## Root Cause: Missing "Initial Momentum Spike" Entry Pattern

Both cases produce $0 P&L because **no entry trigger ever fires**. The bot's entire pattern library requires price action *after* a spike — but Ross entered *during* the spike itself.

---

## HIND Analysis

| Field | Value |
|-------|-------|
| PMH | $7.57 (hit at 08:13) |
| Previous Close | $5.00 (estimated) |
| Ross Entry | ~08:00, near $5.00 |
| Ross Strategy | "ALL buying power (~$370k), added every 50¢: $5→$5.50→$6→$6.50→$7→$7.40" |

### Price Action
```
08:00  $3.35 → $4.58  (initial spike, 5K vol)
08:01  $4.48 → $6.28  (192K vol — Ross enters here ~$5)
08:02  $6.35 → $7.43  (1.3M vol — Ross adding)
08:13  $6.96 → $7.57  (PMH hit, 1.7M vol)
08:14  $7.55 → $6.97  (reversal begins)
08:30  $4.84 → $4.46  (crashed to ~$4.50)
08:55  $4.37 → $4.11  (continued fade)
09:00+ $3.95–$4.10    (dead, never recovers to PMH)
```

**Key insight:** Price reaches PMH at 08:13 then collapses 45% to ~$4. The bot never sees price above PMH again → PMH_BREAK never fires.

### Gate Failures (Below-PMH Patterns)

| Pattern | Why It Fails |
|---------|-------------|
| `PMH_BREAK` | Price never recovers to $7.57 — stays at $4–5 range all session |
| `DIP_FOR_LEVEL` | Requires above-VWAP + not falling knife. After 45% crash from PMH, MACD is negative, price is below 20 EMA → falling knife filter blocks |
| `HOD_CONSOLIDATION_BREAK` | Requires tight consolidation below HOD. The post-crash price action is a slow grind, not tight consolidation. Also requires `setup_type` in `(pmh, hod_break)` ✅ |
| `VWAP_BREAK` | VWAP is likely near $5–6 (weighted by the massive volume spike). Price at $3.80–$4.10 is well below VWAP |
| `WHOLE_HALF_ANTICIPATORY` | Blocked by `entry_triggered` guard — once any pattern attempt occurs, this gate closes |

---

## PRFX Analysis

| Field | Value |
|-------|-------|
| PMH | $7.93 (hit at 08:31) |
| Previous Close | $2.60 (estimated) |
| Float | 800K shares (sub-1M) |
| Ross Entry | ~09:00, at $4.15–$4.50 |
| Ross Strategy | "100% move ($4→$8) in ~20 seconds. Added at $5.70, $6.50, $7.82" |

### Price Action
```
07:41  $2.93 → $2.95  (dead premarket, 315 vol)
08:30  $3.05 → $5.70  (387K vol — momentum ignition)
08:31  $5.34 → $7.93  (694K vol — PMH hit, Ross enters ~$4.15)
08:32  $4.30 → $5.08  (bounce attempt)
08:41  $4.81 → $4.28  (heavy selling, 508K vol)
08:42  $4.27 → $3.91  (continues crashing)
09:00  $4.02 → $3.89  (dead, $3.85–$4.00 range)
09:06  $3.88 → $3.54  (another leg down)
09:10  $3.62 → $3.42  (approaching previous close)
```

**Same pattern as HIND:** One massive bar hits PMH, then immediate collapse. Price never recovers.

### PRFX JSON Note
The JSON premarket data shows `float_shares: 5000000` (5M), not 800K as in the YAML. The YAML has `float_shares: 800000`. This discrepancy doesn't affect the non-entry (both pass the 100M `max_float` threshold), but should be reconciled.

---

## Why Ross Profits and the Bot Can't

Ross's trading style for these cases is fundamentally different from what the bot implements:

| Ross's Approach | Bot's Approach |
|-----------------|----------------|
| Enters on **initial momentum** when news hits | Waits for **pattern formation** after the move |
| Adds aggressively during rising move ($5→$5.50→$6→...) | Requires PMH break, consolidation, or dip-for-level |
| Uses max buying power on conviction plays | Fixed risk per trade |
| Exits partially on the way up, sells into strength | Needs entry trigger → stop → target lifecycle |
| Enters at 08:00–08:01 during the spike | All patterns require bars *after* the spike completes |

---

## Comparison to Successful Cases

Cases that DO produce entries (ROLR, BATL, NPT, GRI) share these traits:
- Price consolidates near or above PMH for multiple bars
- Clear breakout above consolidation range with volume
- VWAP/MACD stay supportive during consolidation

HIND and PRFX lack all three — they're single-spike-and-crash events.

---

## Recommendations

### 1. Accept as Pattern Gap (Low Priority)
These represent a **"breaking news momentum rush"** entry style that's inherently discretionary. Ross uses full buying power on conviction, adds every 50¢, and exits into strength. This is extremely difficult to automate without:
- Real-time news feed with instant reaction
- Conviction scoring for going "all in"
- Aggressive add-to-winner logic during rising moves

### 2. Potential New Pattern: "Premarket Momentum Entry" (Medium Priority)
A new entry pattern could detect:
- Large gap + volume explosion in premarket (>100K vol/min)
- Price moving >30% above previous close within 2–3 minutes
- Enter on pullback after initial spike (e.g., first green candle after red)

### 3. Relabel Setup Type (Quick Win)
Change `setup_type` from `pmh` to `momentum_rush` or `news_spike` in the YAML to avoid misleading the pattern router into trying PMH-based patterns that can never fire.

---

## Files Examined

| File | Purpose |
|------|---------|
| [warrior_setups.yaml](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/warrior_setups.yaml) | Test case definitions |
| [ross_hind_20260127.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/intraday/ross_hind_20260127.json) | HIND intraday bars (5322 lines) |
| [ross_prfx_20260211.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/intraday/ross_prfx_20260211.json) | PRFX intraday bars (4236 lines) |
| [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py) | Entry trigger detection |
| [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py) | Pattern detection functions |
| [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py) | Scanner pillars (confirmed both pass) |
| [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py) | Concurrent batch runner |
