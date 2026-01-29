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

**Restart Backend (6x Ctrl+C with pauses + 60s API cooldown):**
```bash
# All-in-one deploy command with proper shutdown and cooldown:
ssh root@100.113.178.7 "cd ~/Nexus2 && git pull && tmux send-keys -t nexus:0 C-c; sleep 1; tmux send-keys -t nexus:0 C-c; sleep 1; tmux send-keys -t nexus:0 C-c; sleep 1; tmux send-keys -t nexus:0 C-c; sleep 1; tmux send-keys -t nexus:0 C-c; sleep 1; tmux send-keys -t nexus:0 C-c && echo 'Waiting 60s for FMP API cooldown...' && sleep 60 && tmux send-keys -t nexus:0 'python -m uvicorn nexus2.api.main:app --host 0.0.0.0 --port 8000' Enter"
```

**Why 60s cooldown?** FMP API may have been hammered before shutdown. The cooldown prevents rate limit issues on restart.

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
