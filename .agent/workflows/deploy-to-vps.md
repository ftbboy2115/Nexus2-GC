---
description: Deploy code changes to VPS using git (never use scp)
---

# VPS Deployment Workflow

## Prerequisites
- Changes are committed and pushed to origin

## Steps

### 1. Pull on VPS
```bash
ssh root@100.113.178.7 "cd ~/Nexus2 && git pull"
```

### 2. Clear Python Cache (prevents stale bytecode)
```bash
ssh root@100.113.178.7 "find ~/Nexus2 -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null; echo 'pycache cleared'"
```

### 3. Rebuild if Needed

**Frontend changes:** No build step required — dev server hot-reloads on file changes.
If you need to force a restart, see Step 5.

> [!TIP]
> The frontend runs `next dev` (not `next start`), so `git pull` is usually sufficient
> for frontend changes — the dev server detects file changes automatically.

**Backend changes:** No build step required (Python).

### 3.5. Database Migration (if new columns added)

> [!CAUTION]
> SQLAlchemy `create_all()` does NOT add columns to existing tables.

If the change adds columns to an existing table, run ALTER TABLE:
```bash
ssh root@100.113.178.7 "sqlite3 ~/Nexus2/data/<db>.db 'ALTER TABLE <table> ADD COLUMN <col> <type>;'"
```
Verify schema matches Python model before restart.

### 4. Restart Backend (systemd)

The server runs as a systemd service (`nexus2.service`).

**Option A - From CLI:**
```bash
ssh root@100.113.178.7 "systemctl restart nexus2"
```

**Option B - From UI:**
Go to **Warrior → 🔧 Server Admin** and click restart.
(systemd auto-restarts the process when it exits with code 42)

**Option C - From API:**
```bash
curl -X POST http://100.113.178.7:8000/admin/restart -H "Content-Type: application/json" -d '{"confirmation":"REBOOT","clear_cache":true}'
```

### 5. Restart Frontend (if needed)
```bash
ssh root@100.113.178.7 "fuser -k 3000/tcp 2>/dev/null; sleep 2; screen -wipe 2>/dev/null; screen -dmS frontend bash -c 'cd ~/Nexus2/nexus2/frontend && npx next dev -p 3000 -H 0.0.0.0 > /tmp/frontend.log 2>&1'; sleep 4; tail -5 /tmp/frontend.log"
```

### 6. Verify Deployment
```bash
ssh root@100.113.178.7 "curl -s http://localhost:8000/health"
```

### 7. Check Logs
```bash
ssh root@100.113.178.7 "journalctl -u nexus2 --no-pager -n 50"
```

Or the application log file:
```bash
ssh root@100.113.178.7 "tail -50 ~/Nexus2/data/server.log"
```

---

## ⚠️ Never Use
- `scp` for deployment (bypasses version control)
- Direct file edits on VPS (causes git conflicts)
- `tmux` for backend (use systemd — the backend no longer runs in tmux)

---

## 🔧 Systemd Service Details

**Service file:** `/etc/systemd/system/nexus2.service`

Key behavior:
- `Restart=always` — auto-restarts on crash or `/admin/restart`
- `RestartSec=2` — 2-second delay between restarts
- Auto-starts on VPS reboot (`systemctl enable nexus2`)
- Logs to `journalctl -u nexus2` AND `~/Nexus2/data/server.log`

**Status check:**
```bash
ssh root@100.113.178.7 "systemctl status nexus2 --no-pager"
```

**Stop (without restart):**
```bash
ssh root@100.113.178.7 "systemctl stop nexus2"
```
