# Server Admin Card Improvements

Improve the Server Admin card to show deployment info, better memory stats, and pycache status.

## Proposed Changes

### Backend (`health.py`)

#### [MODIFY] [health.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/health.py)

1. **Git commit timestamp** — Add `commit_date` field using `git log -1 --format=%ci`
2. **Total system memory** — Add `memory_total_mb` using `psutil.virtual_memory().total`
3. **Pycache status** — Add `pycache_cleared` bool: check if any `__pycache__` dirs exist under `nexus2/` (if none exist, cache was recently cleared)

Update `HealthResponse` schema to include new fields.

#### [MODIFY] [schemas.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/schemas.py)

Add fields: `commit_date`, `memory_total_mb`, `pycache_cleared`

---

### Frontend (`AdminCard.tsx`)

#### [MODIFY] [AdminCard.tsx](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/frontend/src/components/warrior/AdminCard.tsx)

1. **Commit info row** — Show `v0.2.0-abc1234 (Feb 26, 1:30 PM)` format
2. **Memory display** — Change from `Memory: 133.7 MB` → `Memory: 133.7 / 1024 MB`
3. **Copy/paste button** — Include pycache status: `Pycache: cleared ✅` or `Pycache: present ⚠️`

---

### Additional Recommendations

4. **Last deploy time** — Use `commit_date` as proxy for "when was this code deployed"
5. **Python version** — Add `sys.version` to health for debugging environment issues
6. **Settings sync status** — Show whether `warrior_monitor_settings.json` has been modified since commit (flags stale/out-of-sync settings like we just discovered)

> [!IMPORTANT]
> Items 4-6 are suggestions. Clay should decide which to include.

## Verification Plan

### Browser Test
1. Start the server locally
2. Navigate to the Warrior dashboard → Server Admin card
3. Verify: commit hash + timestamp visible, memory shows used/total, copy button includes pycache status

### API Test
```powershell
Invoke-RestMethod http://localhost:8000/health | ConvertTo-Json
```
Verify new fields (`commit_date`, `memory_total_mb`, `pycache_cleared`) are present.
