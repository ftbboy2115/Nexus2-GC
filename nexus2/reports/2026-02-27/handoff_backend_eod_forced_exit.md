# Handoff: Backend Specialist — Warrior EoD Exit Bug Investigation

## Problem
Warrior bot has existing EoD exit logic but it's NOT WORKING:
- **CDIO, Feb 25**: Held overnight despite `force_exit_time_et: "19:30"` 
- **CD, Feb 27 (tonight)**: New trade entered at 7:35 PM despite `trading_window_end: dt_time(19, 30)`

## Existing Logic (Already Implemented)

### Settings (`warrior_types.py`)
- Line 91: `tighten_stop_time_et: str = "18:00"` — Tighten stops to breakeven at 6 PM
- Line 92: `force_exit_time_et: str = "19:30"` — Force exit at 7:30 PM with escalating offset

### Exit Logic (`warrior_monitor_exit.py`)
- Lines 169-265: `_check_after_hours_exit()` — Full escalating exit implementation
  - Checks `enable_after_hours_exit` (default True)
  - At 7:30 PM: Force exit with escalating offset (2% + 2% every 2 min, max 10%)
  - At 6:00 PM: Tighten stop to breakeven if profitable
  - Uses sim clock (Mock Market) or real wall clock

### Entry Window (`warrior_engine_types.py`)
- Line 60: `trading_window_end: dt_time = field(default_factory=lambda: dt_time(19, 30))`

## Important: Search Path
Use `C:\Dev\Nexus` for search tools.

---

## Investigation Tasks

This is a **debugging task**, not new feature work. The logic exists — find out why it didn't fire.

### 1. Why did CD enter at 7:35 PM?
- `trading_window_end` is 7:30 PM. How is it checked?
- Trace from scanner → entry flow: where does `trading_window_end` gate entries?
- **If it's only checked at engine start/stop (not per-entry), that's the bug**

### 2. Why did CDIO hold overnight?
- `_check_after_hours_exit()` should fire at 7:30 PM. Why didn't it?
- Is `enable_after_hours_exit: True` the default? (Yes, line 90)
- Check if the monitor tick was still running at 7:30 PM on Feb 25
- Check if `sim_mode` guard (line 220) might have blocked it

### 3. What about progressive spread tightening?
After fixing the bugs above, also add:
- Progressive spread gates as time deepens into post-market (see phase table below)
- An explicit entry cutoff guard in `check_entry_guards()` (not just engine-level)

### Enhancement: Phase-Based Spread Tightening

| Phase | Window | Stop (already exists) | Spread Gate (NEW) |
|-------|--------|----------------------|-------------------|
| Regular hours | 9:30 AM - 4:00 PM | Normal | Normal spread filter |
| Early post-market | 4:00 PM - 6:00 PM | Normal | Reject if spread > 2% |
| Tighten (6 PM) | 6:00 PM - 7:00 PM | Breakeven (exists) | Reject if spread > 1% |
| Final (7 PM) | 7:00 PM - 7:30 PM | Escalating exit (exists) | No new entries |
| Hard exit | 7:30 PM | Force exit (exists) | No new entries |

### Enhancement: Entry Cutoff Guard

Add to `check_entry_guards()` as FIRST check:
```python
# EoD entry cutoff — block all new entries past cutoff time
current_time = now_et().time()
cutoff = parse_time(settings.eod_entry_cutoff_time)  # default "19:00"
if current_time >= cutoff:
    return (False, f"EoD entry cutoff: {current_time} past {cutoff}")
```

Settings to add:
```python
eod_entry_cutoff_time: str = "19:00"  # Block new entries after 7 PM
eod_phase1_max_spread_pct: float = 2.0  # Post-market spread gate
eod_phase2_max_spread_pct: float = 1.0  # Late post-market spread gate
```

### Design Rules
- **Do NOT use market orders** — use the existing limit order flow for all exits (including forced)
- Use `now_et()` for all time checks
- The existing escalating offset logic is correct — don't replace it
- Entry cutoff goes in `check_entry_guards()`, NOT just engine-level config

## Testable Claims
1. Root cause identified for CDIO overnight hold (Feb 25)
2. Root cause identified for CD entry at 7:35 PM (Feb 27)
3. After fix: entry at 7:05 PM returns `(False, "EoD entry cutoff...")`
4. After fix: `_check_after_hours_exit()` fires correctly at 7:30 PM
5. After fix: spread gates tighten in post-market phases
6. No existing tests broken
