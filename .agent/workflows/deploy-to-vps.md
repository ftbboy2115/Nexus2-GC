---
description: Deploy code changes to VPS using git (never use scp)
---

# VPS Deployment Workflow

## Prerequisites
- Changes are tested locally
- No uncommitted changes that shouldn't be deployed

## Steps

### 1. Stage and Commit Changes
```powershell
git add <files>
git commit -m "type(scope): description"
```

### 2. Push to Origin
```powershell
git push
```

### 3. Pull on VPS
```bash
ssh root@100.113.178.7 "cd ~/Nexus2 && git pull"
```

### 4. Rebuild if Needed

**For Frontend changes:**
```bash
ssh root@100.113.178.7 "cd ~/Nexus2/nexus2/frontend && npm run build"
```

**For Backend changes:**
No build step required (Python).

### 5. Restart Services

**Frontend only:**
```bash
ssh root@100.113.178.7 "pm2 restart nexus-frontend"
```

**Backend only:**
```bash
ssh root@100.113.178.7 "pm2 restart nexus-api"
```

**Both:**
```bash
ssh root@100.113.178.7 "pm2 restart all"
```

### 6. Verify Deployment
- Check startup logs: `ssh root@100.113.178.7 "tail -f ~/Nexus2/startup.log"`
- Verify health: `curl http://100.113.178.7:8000/health`

---

## ⚠️ Never Use
- `scp` for deployment (bypasses version control)
- Direct file edits on VPS (causes git conflicts)
