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

**Frontend changes:**
```bash
ssh root@100.113.178.7 "cd ~/Nexus2/nexus2/frontend && npm run build"
```

**Backend changes:** No build step required (Python).

### 3.5. Database Migration (if new columns added)

> [!CAUTION]
> SQLAlchemy `create_all()` does NOT add columns to existing tables.

If the change adds columns to an existing table, run ALTER TABLE:
```bash
ssh root@100.113.178.7 "sqlite3 ~/Nexus2/data/<db>.db 'ALTER TABLE <table> ADD COLUMN <col> <type>;'"
```
Verify schema matches Python model before restart.

### 4. Restart Backend (Primary Method: UI or API)

The server runs via `run_api.sh` wrapper script, which enables graceful restart.

**Option A - From UI:**
Go to **Warrior → 🔧 Server Admin** and click restart.

**Option B - From API:**
```bash
curl -X POST http://100.113.178.7:8000/admin/restart
```

The script handles:
- Graceful shutdown (6x Ctrl+C with pauses)
- 60s API cooldown (FMP rate limit protection)
- Server restart

### 5. Restart Frontend (if needed)
```bash
ssh root@100.113.178.7 "tmux send-keys -t frontend C-c C-c C-c"
ssh root@100.113.178.7 "tmux send-keys -t frontend 'cd ~/Nexus2/nexus2/frontend && npm start' Enter"
```

### 6. Verify Deployment
```bash
ssh root@100.113.178.7 "curl -s http://localhost:8000/health"
```

---

## ⚠️ Never Use
- `scp` for deployment (bypasses version control)
- Direct file edits on VPS (causes git conflicts)

---

## 🔧 Manual Alternative (if run_api.sh not running)

If the server was started directly with uvicorn (not via `run_api.sh`), use this:

**Restart Backend (6x Ctrl+C with pauses + 60s API cooldown):**
```bash
ssh root@100.113.178.7 "cd ~/Nexus2 && git pull && tmux send-keys -t nexus:0 C-c; sleep 1; tmux send-keys -t nexus:0 C-c; sleep 1; tmux send-keys -t nexus:0 C-c; sleep 1; tmux send-keys -t nexus:0 C-c; sleep 1; tmux send-keys -t nexus:0 C-c; sleep 1; tmux send-keys -t nexus:0 C-c && echo 'Waiting 60s for FMP API cooldown...' && sleep 60 && tmux send-keys -t nexus:0 'python -m uvicorn nexus2.api.main:app --host 0.0.0.0 --port 8000' Enter"
```

**To switch to run_api.sh (one-time setup):**
```bash
ssh root@100.113.178.7 "chmod +x ~/Nexus2/run_api.sh"
ssh root@100.113.178.7 "tmux send-keys -t nexus:0 C-c C-c"  # Stop current server
ssh root@100.113.178.7 "tmux send-keys -t nexus:0 './run_api.sh' Enter"
```
