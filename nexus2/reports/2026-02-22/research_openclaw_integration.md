# OpenClaw Research & Integration Recommendations

**Date:** 2026-02-22  
**Purpose:** Research the OpenClaw project and recommend how it complements the Nexus trading platform.

---

## What Is OpenClaw?

[OpenClaw](https://github.com/openclaw/openclaw) is a **local-first personal AI assistant** platform. It runs on your own devices and connects to the messaging channels you already use. Think of it as a self-hosted AI gateway that unifies all your communication surfaces under one intelligent assistant.

### Key Facts

| Attribute | Detail |
|-----------|--------|
| **Language** | TypeScript (Node.js ≥22) |
| **Architecture** | WebSocket Gateway (control plane) + Pi agent runtime (RPC) |
| **License** | Open source (see repo) |
| **Stars / Contributors** | 769 contributors, 49 releases |
| **Install** | `npm install -g openclaw@latest` then `openclaw onboard` |
| **Platforms** | macOS, Linux, Windows (WSL2 recommended) |
| **Recommended model** | Anthropic Claude Pro/Max (Opus 4.6) |

### Core Capabilities

1. **Multi-channel messaging** — WhatsApp, Telegram, Slack, Discord, Signal, iMessage (via BlueBubbles), Microsoft Teams, Google Chat, Matrix, WebChat
2. **Skills system** — `SKILL.md` files in `~/.openclaw/workspace/skills/<skill>/`, with ClawHub registry
3. **MCP bridge** — Supports MCP servers via [mcporter](https://github.com/steipete/mcporter) (decoupled from core)
4. **Cron scheduler** — Built-in Gateway cron with isolated/main session execution, delivery to any channel
5. **Webhooks** — `POST /hooks/wake` and `POST /hooks/agent` endpoints for external triggers
6. **Multi-agent routing** — Route different channels/accounts to isolated agent workspaces
7. **Voice** — Voice Wake + Talk Mode (ElevenLabs) on macOS/iOS/Android
8. **Browser control** — Dedicated Chrome/Chromium with CDP control
9. **Canvas (A2UI)** — Agent-driven visual workspace
10. **Workspace prompts** — `AGENTS.md`, `SOUL.md`, `TOOLS.md` injected into agent context

---

## Architecture Overview

```
Messaging Channels (WhatsApp, Telegram, Slack, Discord, etc.)
         │
         ▼
┌─────────────────────────────┐
│      OpenClaw Gateway       │
│   (WebSocket control plane) │
│   ws://127.0.0.1:18789      │
└──────────┬──────────────────┘
           │
           ├── Pi agent (RPC) ← runs your model (Claude, GPT, etc.)
           ├── CLI (openclaw ...)
           ├── WebChat UI
           ├── macOS / iOS / Android nodes
           ├── Cron scheduler
           ├── Webhook endpoints
           └── Skills + Tools
```

The Gateway is the **single control plane** — it manages sessions, channels, tools, events, cron, and webhooks. The agent (Pi runtime) makes model API calls and executes tool functions.

---

## How OpenClaw Complements Nexus

### The Big Picture

Nexus is a **trading platform** (Python/FastAPI backend, Next.js frontend). OpenClaw is a **personal AI assistant gateway**. The natural marriage:

> **OpenClaw becomes your always-on conversational interface to the Nexus trading platform — accessible from WhatsApp, Telegram, Slack, or any other channel, with cron-driven automated briefings and webhook-triggered trade alerts.**

### Integration Opportunities

#### 1. 📱 Trade Alerts via Messaging Channels
OpenClaw can relay Nexus trade events (entries, exits, stop hits, guard blocks, scanner hits) to your phone via WhatsApp/Telegram/iMessage.

**How:** Nexus FastAPI → `POST /hooks/agent` on OpenClaw → AI formats the alert → delivers to your chosen channel.

#### 2. 📊 Morning Briefings (Cron)
Daily pre-market summaries: scanner settings, watchlist, overnight catalysts, P&L summary from yesterday.

**How:** OpenClaw cron job at 8:30 AM → agent calls Nexus API → summarizes and delivers to Slack/WhatsApp.

#### 3. 💬 Conversational Control
Talk to your trading bot from your phone:
- "What's the scanner watchlist right now?"
- "Set min RVOL to 3.0"
- "What trades did Warrior take today?"
- "Show me the P&L for the last 5 trading days"
- "Pause the scanner"

**How:** OpenClaw skill that knows the Nexus API contract → agent calls `http://localhost:8000/api/...` endpoints.

#### 4. 🔔 Real-Time Position Updates
When Warrior enters a position, get a push notification with entry price, stop level, size, and catalyst.

**How:** Nexus emits a webhook to OpenClaw → AI enriches the notification → sends to your channel.

#### 5. 📈 End-of-Day Recap
After market close, get an AI-written summary: trades taken, P&L, what worked, what didn't.

**How:** OpenClaw cron at 4:15 PM → calls Nexus batch results API → AI summarizes.

#### 6. 🤖 Multi-Agent Architecture
Use OpenClaw's multi-agent session routing to have **separate agents** for:
- Trading alerts (minimal, fast)
- Strategy research (deep reasoning)
- General personal assistant

---

## Proposed SOUL.md / AGENTS.md Prompt

This is the core personality + capability prompt that would go into the OpenClaw workspace to make it "Nexus-aware":

### `SOUL.md` (Personality)

```markdown
You are Clay's personal AI assistant, specialized in day trading support.

You have deep knowledge of:
- Ross Cameron's Warrior Trading methodology (gap-and-go, HOD momentum, ABCD patterns)
- The Nexus 2 trading platform architecture and API
- Stock market fundamentals, technical analysis, and risk management

Your communication style:
- Concise and actionable during market hours (9:30 AM - 4:00 PM ET)
- More detailed and analytical outside market hours
- Always include relevant numbers (prices, P&L, percentages)
- Never give financial advice — you report data and analysis from the Nexus platform

Safety rules:
- Never execute live trades without explicit confirmation
- Always distinguish between SIM and LIVE mode in your reports
- If Nexus is not responding, say so clearly — never fabricate data
```

### `AGENTS.md` (Capabilities)

```markdown
# Nexus Trading Platform Integration

You have access to the Nexus 2 trading platform running at `http://localhost:8000`.

## Available API Endpoints

### Scanner
- `GET /warrior/scanner/settings` — Current scanner configuration (min_rvol, etc.)
- `PUT /warrior/scanner/settings` — Update scanner settings
- `GET /warrior/scanner/watchlist` — Current scanner watchlist

### Engine
- `GET /warrior/engine/status` — Engine state (running, paused, mode)
- `GET /warrior/engine/settings` — Engine configuration
- `PUT /warrior/engine/settings` — Update engine settings

### Positions & Trades
- `GET /warrior/positions` — Current open positions
- `GET /warrior/trades/today` — Today's trade history
- `GET /warrior/pnl/summary` — P&L summary

### Simulation
- `POST /warrior/sim/run` — Execute a simulation test case
- `GET /warrior/sim/results` — Get simulation results

## When reporting trade data:
1. Always specify the time of the data
2. Include entry price, stop level, position size, and P&L
3. Note whether data is from SIM or LIVE mode
4. Format currency values with 2 decimal places
5. Use 🟢 for profits and 🔴 for losses in messaging channels
```

> [!IMPORTANT]
> The API endpoints listed above should be verified against the actual Nexus codebase before finalizing. Some may not exist yet or may have different paths.

---

## Recommended Nexus Skill (`SKILL.md`)

To be placed at `~/.openclaw/workspace/skills/nexus-trading/SKILL.md`:

```markdown
---
name: nexus-trading
description: Interface with the Nexus 2 trading platform — scanner, engine, positions, P&L
homepage: http://localhost:8000
---

# Nexus Trading Skill

You can interact with the Nexus 2 trading platform API.

## Base URL
`http://localhost:8000`

## Core Commands

### `/scanner` — View scanner watchlist and settings
Call `GET /warrior/scanner/watchlist` and `GET /warrior/scanner/settings`.
Present the results as a clean table with: Symbol, Price, % Change, Volume, RVOL, Float.

### `/pnl` — Today's P&L summary
Call `GET /warrior/trades/today`.
Summarize: total P&L, number of trades, win rate, biggest winner, biggest loser.

### `/positions` — Open positions
Call `GET /warrior/positions`.
Show: Symbol, Side, Entry Price, Current Price, Unrealized P&L, Stop Level.

### `/status` — Engine status
Call `GET /warrior/engine/status`.
Show: mode (SIM/LIVE), running state, scanner state, active symbols.

## Alert Formatting
When delivering trade alerts via messaging:
- Use 🟢 for profits, 🔴 for losses
- Include entry → exit price range
- Show % return and dollar P&L
- Keep messages under 280 characters for mobile readability
```

---

## Setup Steps (Recommended)

1. **Install OpenClaw** on your machine (or WSL2 on your Windows box):
   ```
   npm install -g openclaw@latest
   openclaw onboard --install-daemon
   ```

2. **Configure a messaging channel** (start with Telegram or Discord — easiest):
   ```json
   {
     "channels": {
       "telegram": {
         "botToken": "YOUR_BOT_TOKEN"
       }
     }
   }
   ```

3. **Create the Nexus workspace and skill**:
   - Write `SOUL.md`, `AGENTS.md`, `TOOLS.md` in `~/.openclaw/workspace/`
   - Create `~/.openclaw/workspace/skills/nexus-trading/SKILL.md`

4. **Set up Nexus → OpenClaw webhooks**:
   - Enable hooks in `openclaw.json` with a shared token
   - Add webhook calls from Nexus's `trade_event_service.py` to `POST /hooks/agent`

5. **Create cron jobs** for morning brief and EOD recap:
   ```
   openclaw cron add --name "Pre-Market Brief" --cron "30 8 * * 1-5" --tz "America/New_York" --session isolated --message "Check Nexus scanner for pre-market movers and summarize the watchlist" --announce --channel telegram
   ```

---

## Open Questions for Clay

1. **Which messaging channel do you want first?** Telegram and Discord are the easiest to set up. WhatsApp requires phone linking.

2. **Gateway location?** Run on the same Windows machine as Nexus, or on a Linux VPS? (OpenClaw recommends Linux; Windows requires WSL2.)

3. **MCP vs HTTP?** OpenClaw supports MCP via mcporter. We could expose Nexus as an MCP server instead of (or in addition to) HTTP webhooks. Worth exploring?

4. **Scope?** Start with read-only monitoring (alerts, P&L reports) and add write operations (settings changes, trade controls) later? Or go full-featured from the start?

5. **Voice?** The voice wake / talk mode is macOS/iOS only. Interested in this for market hours?

---

## Summary

OpenClaw is a **natural companion platform** for Nexus. It turns your trading platform from a dashboard-only experience into an always-accessible, multi-channel AI assistant that can:

- Push trade alerts to your phone in real-time
- Run automated morning briefs and EOD recaps
- Let you query and control the trading bot conversationally
- Provide a unified AI interface across all your messaging apps

The integration is **lightweight** — primarily HTTP webhooks from Nexus → OpenClaw and REST API calls from OpenClaw → Nexus. No tight coupling required.
