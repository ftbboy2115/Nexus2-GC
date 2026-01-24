---
description: Deploy code changes to VPS using git (never use scp)
---

# VPS Deployment Workflow

## Prerequisites
- Changes are committed and pushed to origin
- No uncommitted changes that shouldn't be deployed

## Steps

### 1. Pull on VPS
```bash
ssh root@100.113.178.7 "cd ~/Nexus2 && git pull"
```

### 2. Rebuild if Needed

**For Frontend changes:**
```bash
ssh root@100.113.178.7 "cd ~/Nexus2/nexus2/frontend && npm run build"
```

**For Backend changes:**
No build step required (Python).

### 3. Restart Services (tmux)

**View running sessions:**
```bash
ssh root@100.113.178.7 "tmux list-sessions"
```

**Restart Backend:**
```bash
# Attach to the nexus-api session and restart
ssh -t root@100.113.178.7 "tmux attach -t nexus-api"
# Then Ctrl+C to stop, up arrow to rerun, Ctrl+B D to detach
```

**Alternative - Kill and restart in one command:**
```bash
ssh root@100.113.178.7 "tmux send-keys -t nexus-api C-c && sleep 1 && tmux send-keys -t nexus-api 'cd ~/Nexus2 && source .venv/bin/activate && python -m uvicorn nexus2.api.main:app --host 0.0.0.0 --port 8000 2>&1 | tee startup.log' Enter"
```

**Restart Frontend:**
```bash
ssh root@100.113.178.7 "tmux send-keys -t nexus-frontend C-c && sleep 1 && tmux send-keys -t nexus-frontend 'cd ~/Nexus2/nexus2/frontend && npm start' Enter"
```

### 4. Verify Deployment
- Check startup logs: `ssh root@100.113.178.7 "tail -f ~/Nexus2/startup.log"`
- Verify health: `curl http://100.113.178.7:8000/health`

---

## ⚠️ Never Use
- `scp` for deployment (bypasses version control)
- Direct file edits on VPS (causes git conflicts)
