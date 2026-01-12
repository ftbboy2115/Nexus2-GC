# Nexus 2 User Guide

A comprehensive guide to operating the Nexus trading platform.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Dashboard Overview](#dashboard-overview)
3. [NAC (Nexus Automation Controller)](#nac-strategy)
4. [Warrior Strategy](#warrior-strategy)
5. [Scheduler Controls](#scheduler-controls)
6. [Position Management](#position-management)
7. [Risk Settings](#risk-settings)
8. [Discord Alerts](#discord-alerts)
9. [VPS Operations](#vps-operations)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. Start the Backend (VPS)
```bash
cd ~/Nexus2/nexus2
source .venv/bin/activate
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Or use tmux for persistence:
```bash
tmux attach -t nexus  # If session exists
# Or: tmux new -s nexus
```

### 2. Access the Dashboard
- **VPS**: `http://[tailscale-ip]:3000`
- **Local**: `http://localhost:3000`

### 3. Enable Broker
1. Navigate to **Accounts** section
2. Click **Enable Paper** or **Enable Live**
3. Dashboard will show "PAPER MODE" or "LIVE MODE" in the header

### 4. Start Scheduler
1. Click **Start** in the Scheduler Controls card
2. Toggle **Auto-Execute** if you want trades to execute automatically
3. Monitor the **Next Scan** countdown

---

## Dashboard Overview

### Header
| Element | Description |
|---------|-------------|
| Strategy Tab | Switch between NAC and Warrior strategies |
| Mode Indicator | Shows PAPER/LIVE and SIM status |
| Account Selector | Choose Alpaca account |

### Main Cards
| Card | Purpose |
|------|---------|
| **Open Positions** | Current holdings with P/L |
| **Scheduler** | Start/stop, status, next scan |
| **Signals** | Pending trade signals |
| **Diagnostics** | Last scan results, rejections |
| **Quick Actions** | Test buttons, liquidate all |
| **Trade Log** | Historical trades |
| **Trade Events** | Audit trail of all changes |

---

## NAC Strategy

### What is NAC?
**N**exus **A**utomation **C**ontroller is the KK-style swing trading system:
- Scans run every 5 minutes by default (configurable interval)
- EP (Episodic Pivot), Breakout, and HTF setups
- Holds 1-7 days with MA trailing stops

### Scan Frequency
| Setting | Default | Description |
|---------|---------|-------------|
| Interval | 300s (5 min) | Time between scans |
| Active Hours | Market hours | Auto-skips weekends/holidays |

### Exit Rules
| Condition | Action |
|-----------|--------|
| Stop hit | Full exit |
| Day 3+ in profit | 50% partial, stop to breakeven |
| Day 5+ below MA | Full exit (MA trailing) |
| Day 0-4 character change | Full exit if below both 10 & 20 EMA |

### EOD Window
- **3:45 PM - 4:00 PM ET**: MA check runs
- Positions closing below their trailing MA are exited

---

## Warrior Strategy

### What is Warrior?
Ross Cameron-style day trading:
- Low-float momentum stocks
- Gap-and-go, ORB setups
- Intraday only (no overnight holds)

### Exit Rules
| Condition | Action |
|-----------|--------|
| Mental stop (15¢) | Full exit |
| Profit target (2:1 R) | 50% partial, stop to breakeven |
| Candle-under-candle | Full exit (character change) |
| Topping tail (60%+ wick) | Full exit |
| 7:30 PM ET | Force exit (no overnight) |

### Monitor Settings
| Setting | Default | Description |
|---------|---------|-------------|
| `mental_stop_cents` | 15 | Stop distance in cents |
| `profit_target_r` | 2.0 | Take profit at 2:1 R |
| `partial_exit_fraction` | 0.5 | Exit 50% at target |

---

## Scheduler Controls

### Buttons
| Button | Action |
|--------|--------|
| **Start** | Begin scanning loop |
| **Stop** | Pause scanning |
| **Force Scan** | Run scan immediately |
| **Test Discord** | Send test notification |

### Settings
| Setting | Description |
|---------|-------------|
| **Auto-Execute** | Execute trades automatically (vs signals-only) |
| **Interval** | Seconds between scans (default: 300 = 5 min) |
| **Discord Alerts** | Enable/disable notifications |

### Status Indicators
| Field | Meaning |
|-------|---------|
| **Running** | Scheduler is active |
| **Last Run** | Timestamp of last scan |
| **Next Scan** | Countdown to next scan |
| **Orders Filled** | Trades executed today |

---

## Position Management

### Open Positions Table
| Column | Description |
|--------|-------------|
| Symbol | Stock ticker |
| Shares | Position size |
| Entry | Average cost |
| Current | Latest price |
| P/L | Unrealized gain/loss |
| P/L % | Return percentage |
| Stop | Current stop price |
| Days | Days held |

### Actions
- **Export CSV**: Download positions as spreadsheet
- **Click row**: View position details and trade events

### Stop Management
Stops can only be **tightened** (raised for longs). KK rule: never loosen a stop.

---

## Risk Settings

### Position Sizing
| Parameter | Default | Description |
|-----------|---------|-------------|
| `risk_per_trade` | $250 | Fixed dollar risk |
| `max_position_pct` | 30% | Max position as % of account |
| `max_atr_ratio` | 1.0 | Stop must be ≤ 1x ATR |

### Formula
```
Shares = Risk per Trade / (Entry - Stop)
```

### Example
```
Entry: $100
Stop: $95 (tactical stop)
Risk: $250

Shares = $250 / $5 = 50 shares
```

---

## Discord Alerts

### Notification Types
| Type | Content |
|------|---------|
| **Entry** | New position opened |
| **Exit** | Position closed (stop/target) |
| **Partial** | 50% sold at target |
| **Scanner** | New signals detected |

### Setup
1. Create a Discord webhook in your channel
2. Add webhook URL to `.env`:
   ```
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```
3. Enable in dashboard: **Settings > Discord Alerts**

### Test
Click **Test Discord** in Quick Actions to verify connectivity.

---

## VPS Operations

### SSH Access
```bash
ssh root@[tailscale-ip]
```

### Tmux Session
```bash
# Attach to existing session
tmux attach -t nexus

# Detach (keep running)
Ctrl+B, then D

# Kill session
Ctrl+C (x3 for force quit)
```

### Log Viewing
```bash
# Tail backend logs
tail -f ~/Nexus2/nexus2/nexus.log

# View rejection log
cat ~/Nexus2/nexus2/logs/rejections.log | tail -50
```

### Update & Restart
```bash
cd ~/Nexus2
git pull
cd nexus2
source .venv/bin/activate
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

---

## Troubleshooting

### Dashboard Won't Load
1. Check backend is running: `curl http://localhost:8000/health`
2. Check frontend is running: `ps aux | grep next`
3. Verify Tailscale connection

### Scheduler Not Starting
1. Is it a weekend/holiday? Scheduler auto-skips non-trading days
2. Check broker is enabled
3. Look for errors in logs

### No Signals Generated
1. Check FMP API key is valid
2. Review rejection log for skipped stocks
3. Verify scanner settings aren't too strict

### Positions Not Syncing
1. Run manual sync: **Quick Actions > Sync Positions**
2. Check Alpaca API connectivity
3. Verify correct account is selected

### Discord Not Working
1. Test webhook URL manually:
   ```bash
   curl -X POST [webhook_url] -H "Content-Type: application/json" -d '{"content":"test"}'
   ```
2. Check `.env` has correct URL
3. Verify Discord alerts are enabled in settings

---

## API Reference

### Health Check
```
GET /health
```
Returns broker mode, market status, Eastern time.

### Scheduler Control
```
POST /automation/scheduler/start
POST /automation/scheduler/stop
POST /automation/scheduler/force_scan
GET  /automation/scheduler/status
```

### Positions
```
GET  /positions
POST /positions/sync
```

### Settings
```
GET   /automation/scheduler/settings
PATCH /automation/scheduler/settings
```

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+C` | Graceful shutdown (in terminal) |
| `Ctrl+C x3` | Force quit |
| `Ctrl+B, D` | Detach tmux session |

---

*Last updated: January 2026*
