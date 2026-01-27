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

### 4. Restart Services (tmux)

**Session names:** `nexus` (backend), `frontend` (frontend)

**Restart Backend (4x Ctrl+C with pauses - uvicorn requires multiple signals):**
```bash
# Stop the running backend (needs 4 Ctrl+C's with 1s pause between each)
ssh root@100.113.178.7 "tmux send-keys -t nexus C-c; sleep 1; tmux send-keys -t nexus C-c; sleep 1; tmux send-keys -t nexus C-c; sleep 1; tmux send-keys -t nexus C-c"
# Wait 2-3 seconds for process to exit, then restart:
ssh root@100.113.178.7 "tmux send-keys -t nexus 'cd ~/Nexus2 && source .venv/bin/activate && python -m uvicorn nexus2.api.main:app --host 0.0.0.0 --port 8000 2>&1 | tee startup.log' Enter"
```

**Restart Frontend:**
```bash
ssh root@100.113.178.7 "tmux send-keys -t frontend C-c C-c C-c"
ssh root@100.113.178.7 "tmux send-keys -t frontend 'cd ~/Nexus2/nexus2/frontend && npm start' Enter"
```

### 5. Verify Deployment
```bash
ssh root@100.113.178.7 "curl -s http://localhost:8000/health"
```

---

## ⚠️ Never Use
- `scp` for deployment (bypasses version control)
- Direct file edits on VPS (causes git conflicts)
