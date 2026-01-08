# VPS Deployment Guide - Nexus 2

## Overview

| Setting | Value |
|---------|-------|
| Provider | DigitalOcean |
| Plan | Basic ($6/mo) |
| Specs | 1 vCPU, 1GB RAM + 2GB swap |
| Region | NYC1 |
| OS | Ubuntu 24.04 LTS |
| Access | Tailscale VPN only |

---

## Phase 1: Create Droplet (DigitalOcean Console)

1. Log into DigitalOcean
2. Create Droplet:
   - **Region:** NYC1
   - **Image:** Ubuntu 24.04 LTS
   - **Size:** Basic, $6/mo (1GB RAM)
   - **Authentication:** SSH Key (recommended)
3. Note the public IP

---

## Phase 2: Initial Server Setup

```bash
ssh root@<PUBLIC_IP>

# Update system
apt update && apt upgrade -y

# Firewall (allow SSH only initially)
ufw allow OpenSSH
ufw enable
```

---

## Phase 3: Install Dependencies

```bash
# Python 3.12
apt install -y python3.12 python3.12-venv python3-pip

# Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# Git & tmux
apt install -y git tmux htop
```

---

## Phase 4: Clone & Setup

### GitHub Authentication

Create a **Fine-Grained Personal Access Token** at GitHub:
- Settings → Developer settings → Personal access tokens → Fine-grained
- Token name: `nexus-vps`
- Repository access: Only select Nexus2
- Permissions: Contents (Read and write)

### Clone Repository

```bash
git clone https://<USERNAME>:<TOKEN>@github.com/<USERNAME>/Nexus2.git
cd Nexus2
```

### Python Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Create .env File

```bash
nano .env
```

Add your API keys:
```
FMP_API_KEY=your_fmp_key
APCA_API_KEY_ID=your_alpaca_key
APCA_API_SECRET_KEY=your_alpaca_secret
```

### Frontend Setup

```bash
cd nexus2/frontend
npm install
npm run build
```

---

## Phase 5: Add Swap (Prevents OOM)

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## Phase 6: Tailscale VPN (Security)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Follow the auth link, then close public ports:
```bash
sudo ufw delete allow 3000
sudo ufw delete allow 8000
```

Access via Tailscale IP only (e.g., `100.x.x.x`).

---

## Phase 7: Run with tmux

### Backend

```bash
tmux new -s nexus
cd ~/Nexus2
source .venv/bin/activate
uvicorn nexus2.api.main:app --host 0.0.0.0 --port 8000
# Detach: Ctrl+B then d
```

### Frontend

```bash
tmux new -s frontend
cd ~/Nexus2/nexus2/frontend
npm run start
# Detach: Ctrl+B then d
```

### Reattach Later

```bash
tmux attach -t nexus
tmux attach -t frontend
```

---

## Verification

```bash
# Check processes
tmux ls

# Test backend
curl http://localhost:8000/health

# Check memory
free -h

# Force scan test
curl -X POST http://localhost:8000/automation/scheduler/force_scan
```

---

## Access URLs (via Tailscale)

| Service | URL |
|---------|-----|
| Dashboard | http://<TAILSCALE_IP>:3000 |
| API Docs | http://<TAILSCALE_IP>:8000/docs |
| Health | http://<TAILSCALE_IP>:8000/health |

---

## Troubleshooting

### pywin32 Error During pip install
Remove Windows-only packages from requirements.txt:
```bash
# On local machine
(Get-Content requirements.txt) | Where-Object { $_ -notmatch "pywin32" } | Set-Content requirements.txt
git commit -am "fix: Remove Windows packages"
git push
# Then on VPS: git pull && pip install -r requirements.txt
```

### 401 Unauthorized Errors
Check .env file has real API keys, not placeholders.

### OOM Killer
Add more swap or upgrade to $12/mo (2GB RAM).

---

## Future: systemd (Auto-Restart)

See [systemd_services.md](systemd_services.md) for auto-start on boot configuration.
