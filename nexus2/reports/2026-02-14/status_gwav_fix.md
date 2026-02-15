# Status: GWAV Regression Fix

**Date:** 2026-02-14  
**Agent:** Backend Specialist  
**Status:** ✅ COMPLETE — Ready for batch test verification

---

## Change Applied

**File:** [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L997-L1006)  
**Option:** B (selective blocking by guard type)

```diff
 else:
     logger.info(f"[Warrior Entry] {symbol}: {block_reason}")
-    watched.entry_triggered = True
+    # Only permanently block for non-recoverable rejections.
+    # Temporary guards (MACD, VWAP, spread, cooldown) should allow
+    # patterns to retry on the next tick when conditions improve.
+    # Ref: investigation_gwav_regression.md Option B
+    permanent_blocks = {"Blacklisted", "Max fails hit"}
+    if any(pb in block_reason for pb in permanent_blocks):
+        watched.entry_triggered = True
     return
```

---

## Guard Classification

| Guard | Block Reason String | Nature | Sets entry_triggered? |
|-------|-------------------|--------|----------------------|
| Blacklist | `"Blacklisted"` | Permanent | ✅ Yes |
| Max fails | `"Max fails hit - ..."` | Permanent | ✅ Yes |
| MACD gate | `"MACD GATE - ..."` | Temporary | ❌ No |
| Top X picks | `"TOP_X_ONLY - ..."` | Temporary | ❌ No |
| Min score | `"Score X < min Y"` | Temporary | ❌ No |
| Cooldown | `"Re-entry cooldown..."` | Temporary | ❌ No |
| SIM cooldown | `"SIM re-entry cooldown..."` | Temporary | ❌ No |
| Spread | `"REJECTED - spread..."` | Temporary | ❌ No |
| Pending order | `"Pending buy order..."` | Temporary | ❌ No |
| FAIL-CLOSED | `"FAIL-CLOSED - ..."` | Temporary | ❌ No |
| Already holding | `"Already holding..."` | Temporary | ❌ No |

---

## Expected Impact

- **GWAV:** P&L should restore from +$215.91 → ≈+$630.63 (baseline)
- **Other cases:** Any case where temporary guard rejection was permanently killing re-entry should also improve or remain unchanged
- **HOD_BREAK:** Unaffected — already has its own `entry_triggered` exemption at [warrior_entry_patterns.py:1293](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L1293)

## Verification Plan

1. Run GWAV individually — expect P&L ≈ +$630.63
2. Run full 29-case batch — expect total ≈ $3,945, no regressions
3. Confirm HOD_BREAK (MLEC) behavior unchanged
