# Audit Report: Time Filter Fix in data_routes.py

**Date:** 2026-02-17  
**Auditor:** Code Auditor Agent  
**File:** `nexus2/api/routes/data_routes.py` (1291 lines)  
**Compilation:** ✅ PASS  

---

## A. File Inventory

| Endpoint | Function | Lines | time_from/time_to Params | TZ Pattern |
|----------|----------|-------|--------------------------|------------|
| NAC Trades | `get_nac_trades` | L125–225 | ✅ Added | `EASTERN.localize` + `et_to_utc` |
| NAC Scan History | `get_scan_history` | L232–296 | ⏭️ Skipped (correct) | N/A (date strings) |
| Warrior Scans | `get_warrior_scan_history` | L303–428 | ✅ Pre-existing | `ZoneInfo` + `.replace()` |
| Catalyst Audits | `get_catalyst_audits` | L485–590 | ✅ Pre-existing | `ZoneInfo` + `.replace()` |
| AI Comparisons | `get_ai_comparisons` | L622–721 | ✅ Pre-existing | `ZoneInfo` + `.replace()` |
| Trade Events | `get_trade_events` | L752–837 | ✅ Pre-existing | `ZoneInfo` (UTC→ET in-memory) |
| Warrior Trades | `get_warrior_trades` | L867–986 | ✅ Added | `EASTERN.localize` + `et_to_utc` |
| Quote Audits | `get_quote_audits` | L1038–1129 | ✅ Added | `EASTERN.localize` + `et_to_utc` |
| Validation Log | `get_validation_log` | L1159–1243 | ✅ Added (+ date params) | `EASTERN.localize` + `et_to_utc` |

**Result: All 8 data endpoints verified. NAC Scan History correctly skipped (9th endpoint).**

---

## B. Dependency Graph

```
data_routes.py
  └── imports: nexus2.utils.time_utils (et_to_utc, EASTERN)
  └── local imports per function:
      ├── ZoneInfo("UTC"), ZoneInfo("America/New_York")  ← Warrior Scans, Catalyst, AI Comp, Trade Events
      └── pytz.timezone (via EASTERN)                    ← NAC Trades, Warrior Trades, Quote Audits, Validation Log
```

---

## C. Findings

### Finding 1: Two Inconsistent Timezone Patterns (LOW severity)

**Finding:** The file uses two different approaches for ET→UTC conversion. Three pre-existing endpoints use `ZoneInfo` + `.replace(tzinfo=...)` while four endpoints (including the new fixes) use `pytz.EASTERN.localize()` + `et_to_utc()`.

**File:** `c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\nexus2\api\routes\data_routes.py`

**Code (ZoneInfo pattern — L357-358, Warrior Scans):**
```python
start_time = f"{time_from}:00" if time_from else "00:00:00"
et_start = dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=et_tz)
utc_start = et_start.astimezone(utc_tz)
```

**Code (pytz pattern — L946-948, Warrior Trades):**
```python
start_time = f"{time_from}:00" if time_from else "00:00:00"
et_start = EASTERN.localize(dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S"))
query = query.filter(WarriorTradeModel.entry_time >= et_to_utc(et_start))
```

**Verified with:**
```powershell
Select-String -Path "nexus2\api\routes\data_routes.py" -Pattern "EASTERN.localize|\.replace\(tzinfo=et_tz\)"
```
**Output:**
```
nexus2\api\routes\data_routes.py:183:  et_start = EASTERN.localize(...)
nexus2\api\routes\data_routes.py:190:  et_end = EASTERN.localize(...)
nexus2\api\routes\data_routes.py:358:  et_start = dt.strptime(...).replace(tzinfo=et_tz)
nexus2\api\routes\data_routes.py:368:  et_end = dt.strptime(...).replace(tzinfo=et_tz)
nexus2\api\routes\data_routes.py:543:  et_start = dt.strptime(...).replace(tzinfo=et_tz)
nexus2\api\routes\data_routes.py:552:  et_end = dt.strptime(...).replace(tzinfo=et_tz)
nexus2\api\routes\data_routes.py:673:  et_start = dt.strptime(...).replace(tzinfo=et_tz)
nexus2\api\routes\data_routes.py:682:  et_end = dt.strptime(...).replace(tzinfo=et_tz)
nexus2\api\routes\data_routes.py:947:  et_start = EASTERN.localize(...)
nexus2\api\routes\data_routes.py:954:  et_end = EASTERN.localize(...)
nexus2\api\routes\data_routes.py:1090: et_start = EASTERN.localize(...)
nexus2\api\routes\data_routes.py:1097: et_end = EASTERN.localize(...)
nexus2\api\routes\data_routes.py:1204: et_start = EASTERN.localize(...)
nexus2\api\routes\data_routes.py:1211: et_end = EASTERN.localize(...)
```

**Conclusion:** Both patterns produce correct results for non-ambiguous times. However, `ZoneInfo.replace()` does NOT handle DST ambiguity (fall-back hour), while `pytz.localize()` does raise `AmbiguousTimeError`. In practice, trading happens 6 AM–4 PM ET so DST ambiguity at 1 AM is irrelevant. The backend agent correctly matched the pre-existing pattern for each endpoint category. **Not a bug, but a consistency smell.**

---

### Finding 2: `time_from`/`time_to` Silently Ignored Without `date_from`/`date_to` (MEDIUM severity)

**Finding:** In all 7 SQL-based endpoints, `time_from` and `time_to` are only wired inside the `if date_from:` and `if date_to:` blocks respectively. If a user sets `time_from=09:00` without setting `date_from`, the time filter is completely ignored with no warning.

**File:** `c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\nexus2\api\routes\data_routes.py`:L180-193 (NAC Trades, representative of all)

**Code:**
```python
if date_from:                                       # <-- time_from only used HERE
    try:
        start_time = f"{time_from}:00" if time_from else "00:00:00"
        et_start = EASTERN.localize(dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S"))
        query = query.filter(NACTradeModel.entry_time >= et_to_utc(et_start))
    except ValueError:
        pass
if date_to:                                         # <-- time_to only used HERE
    try:
        end_time = f"{time_to}:59" if time_to else "23:59:59"
        et_end = EASTERN.localize(dt.strptime(f"{date_to} {end_time}", "%Y-%m-%d %H:%M:%S"))
        query = query.filter(NACTradeModel.entry_time <= et_to_utc(et_end))
    except ValueError:
        pass
```

**Affected endpoints:** NAC Trades (L180), Warrior Scans (L354), Catalyst Audits (L540), AI Comparisons (L670), Warrior Trades (L944), Quote Audits (L1087), Validation Log (L1201).

**Conclusion:** This is arguably correct behavior — a time without a date is semantically incomplete for SQL range queries. The Trade Events endpoint (L781) handles this differently by entering the filter block on `if date_from or date_to or time_from or time_to:`, but that's because it does in-memory string comparison, not SQL datetime math. **This is a design decision, not a bug**, but the frontend should be aware that time-only filtering requires setting a date range.

> [!NOTE]
> The coordinating handoff flagged this as "time_from without date_from" — confirmed: time-only filtering is not supported in SQL endpoints. This is acceptable if the frontend always sends dates with times.

---

### Finding 3: `end_time` Seconds Precision — Off-by-59-seconds (LOW severity)

**Finding:** When `time_to` is set, the end time uses `:59` seconds suffix. `time_to=10:30` becomes `10:30:59`. This means the filter includes records up to `10:30:59` rather than `10:30:00`. While this is arguably "inclusive" behavior, it creates a 59-second over-inclusion at the boundary.

**File:** `c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\nexus2\api\routes\data_routes.py`:L189

**Code (all endpoints use this pattern):**
```python
end_time = f"{time_to}:59" if time_to else "23:59:59"
```

**Conclusion:** This is an intentional design choice for inclusive upper bounds. When `time_to` is NOT set, the default `23:59:59` catches all records in the day. The `:59` suffix for user-provided times ensures that `time_to=10:30` includes all records AT 10:30 (e.g., 10:30:42). **This is correct behavior for HH:MM granularity input.**

---

### Finding 4: Inconsistent Param Descriptions (COSMETIC)

**Finding:** The `time_from`/`time_to` parameter descriptions vary across endpoints. Some say `"Start time (HH:MM)"` and others say `"Start time (HH:MM) in ET"`.

**File:** `c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\nexus2\api\routes\data_routes.py`

| Endpoint | Line | Description |
|----------|------|-------------|
| NAC Trades | L136 | `"Start time (HH:MM) in ET"` |
| Warrior Scans | L309 | `"Start time (HH:MM)"` |
| Catalyst Audits | L491 | `"Start time (HH:MM)"` |
| AI Comparisons | L628 | `"Start time (HH:MM)"` |
| Trade Events | L761 | `"Start time (HH:MM)"` |
| Warrior Trades | L882 | `"Start time (HH:MM) in ET"` |
| Quote Audits | L1048 | `"Start time (HH:MM) in ET"` |
| Validation Log | L1168 | `"Start time (HH:MM) in ET"` |

**Verified with:**
```powershell
Select-String -Path "nexus2\api\routes\data_routes.py" -Pattern "time_from.*Query"
```

**Conclusion:** The newly added endpoints (NAC Trades, Warrior Trades, Quote Audits, Validation Log) say `"in ET"` while the pre-existing ones don't. All endpoints DO treat time as ET, so the new descriptions are more accurate. **Cosmetic inconsistency — the older endpoints should also say `"in ET"` for clarity.**

---

### Finding 5: Trade Events UTC→ET Conversion — Correct Implementation

**Finding:** The Trade Events endpoint (the original bug) correctly parses UTC timestamps and converts them to ET before comparison.

**File:** `c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\nexus2\api\routes\data_routes.py`:L789-798

**Code:**
```python
try:
    # Parse UTC timestamp and convert to ET for comparison
    utc_str = created.replace("T", " ").rstrip("Z")[:19]
    utc_dt = dt.strptime(utc_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=utc_tz)
    et_dt = utc_dt.astimezone(et_tz)
    entry_date = et_dt.strftime("%Y-%m-%d")
    entry_time = et_dt.strftime("%H:%M")
except (ValueError, IndexError):
    entry_date = created[:10]
    entry_time = created[11:16]
```

**Conclusion:** ✅ Correct. The `rstrip("Z")[:19]` handles both `2026-02-17T14:28:00Z` and `2026-02-17T14:28:00` formats. The fallback in `except` preserves old behavior for malformed timestamps. The conversion from UTC to ET is mathematically correct via `ZoneInfo("America/New_York")`.

---

### Finding 6: No Input Validation on `time_from`/`time_to` Format (LOW severity)

**Finding:** There is no validation that `time_from`/`time_to` match the expected `HH:MM` format. Malformed inputs like `"8:00"`, `"abc"`, or `"08:00:00"` are passed through.

**File:** All endpoints — the format string `f"{time_from}:00"` is used directly.

**Code (L182, representative):**
```python
start_time = f"{time_from}:00" if time_from else "00:00:00"
et_start = EASTERN.localize(dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S"))
```

**Analysis of malformed inputs:**
| Input | Resulting string | `strptime` result |
|-------|-----------------|-------------------|
| `"08:00"` (valid) | `"08:00:00"` | ✅ Parses correctly |
| `"8:00"` (single digit) | `"8:00:00"` | ✅ `strptime %H:%M:%S` accepts this |
| `"abc"` | `"abc:00"` | ❌ `ValueError` → caught by `except`, filter skipped silently |
| `"08:00:00"` (with seconds) | `"08:00:00:00"` | ❌ `ValueError` → caught by `except`, filter skipped silently |
| `""` (empty string) | `":00"` | ❌ `ValueError` → caught by `except`, filter skipped silently |

**Conclusion:** Invalid inputs fail safely (caught by `except ValueError: pass`) — the filter is simply not applied. This is acceptable but not ideal — the user gets no feedback that their time filter was ignored. **Not a bug, but could benefit from a 422 validation error for bad format.**

---

## D. Refactoring Recommendations

| Priority | Issue | Files | Recommended Action | Effort |
|----------|-------|-------|--------------------|--------|
| 1 | Timezone pattern inconsistency | data_routes.py | Standardize ALL endpoints on `EASTERN.localize` + `et_to_utc` (matches project convention in `time_utils.py`) | S |
| 2 | Param description inconsistency | data_routes.py | Add `"in ET"` to all 4 pre-existing endpoints' `time_from`/`time_to` descriptions | S |
| 3 | Extract shared time filter helper | data_routes.py | The pattern `start_time = f"{time_from}:00" if time_from else "00:00:00"` + `EASTERN.localize(...)` is repeated 14x — extract a `_build_utc_range(date_from, date_to, time_from, time_to)` helper | M |
| 4 | Input format validation | data_routes.py | Add regex check `HH:MM` before creating the datetime — return 400/422 on bad format | S |

---

## E. Overall Assessment

| Category | Rating | Notes |
|----------|--------|-------|
| **Correctness** | ✅ PASS | UTC→ET conversion correct. All timezone math is sound. |
| **Completeness** | ✅ PASS | All 8 data endpoints verified. NAC Scan History correctly skipped. |
| **Regressions** | ✅ NONE | Existing date-only filtering unaffected (defaults `00:00:00` / `23:59:59`). |
| **Edge Cases** | ⚠️ MINOR | `time_from` without `date_from` silently no-ops. Malformed time silently no-ops. Both acceptable. |
| **Architecture** | ⚠️ MINOR | Two TZ patterns, repeated code. Non-blocking. |

### Verdict: **PASS** — The fix is correct and complete. All claimed changes are implemented. No regressions detected. Minor cleanup opportunities identified for future work.
