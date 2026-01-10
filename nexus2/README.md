# Nexus 2

A modular trading platform for KK-style momentum trading.

## Architecture

This is a **Modular Monolith** with strict bounded contexts:

```
nexus2/
├── domain/           # Domain logic (pure Python, no dependencies)
│   ├── scanner/      # Scanner criteria, quality scoring
│   ├── setup_detection/  # EP, HTF, flag detection
│   ├── risk/         # Position sizing, stops, open heat
│   ├── orders/       # Order lifecycle
│   ├── positions/    # Position tracking
│   └── market_regime/  # Bull/bear detection
├── adapters/         # External integrations
│   ├── market_data/  # FMP, Alpaca, etc.
│   ├── broker/       # Paper/live trading
│   └── notifications/  # Discord, email
├── cli/              # Command-line tools
├── api/              # FastAPI routes
├── settings/         # User-configurable settings
└── tests/            # Test suites
```

## Prerequisites

- **Python 3.10+** (tested on 3.14)
- **Node.js 18+** (for frontend)
- **API Keys:**
  - [Financial Modeling Prep](https://financialmodelingprep.com/) (FMP) - market data
  - [Alpaca](https://alpaca.markets/) - paper/live trading (optional for SIM mode)
  - Discord webhook URL (optional - for trade alerts)

## Quick Start

### 1. Clone and Setup Backend

```powershell
# Windows (PowerShell)
git clone https://github.com/ftbboy2115/Nexus2.git
cd Nexus

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

```bash
# Linux/Mac
git clone https://github.com/ftbboy2115/Nexus2.git
cd Nexus
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```powershell
# Copy example config
Copy-Item .env.example .env  # Windows
# cp .env.example .env       # Linux/Mac

# Edit .env with your keys
```

**Required `.env` settings:**
```env
FMP_API_KEY=your_fmp_key_here
APCA_API_KEY_ID=your_alpaca_key_here
APCA_API_SECRET_KEY=your_alpaca_secret_here
TRADING_MODE=PAPER
```

> Aliases also accepted: `ALPACA_KEY`/`ALPACA_SECRET` or `FMP_KEY`

**Optional settings:**
```env
DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
```

### 3. Start Backend

```powershell
uvicorn nexus2.api.main:app --reload
```

API available at: http://localhost:8000  
Swagger docs at: http://localhost:8000/docs

### 4. Start Frontend

```powershell
cd nexus2\frontend
npm install
npm run dev
```

Dashboard at: http://localhost:3000


## CLI Scanners

### EP Scanner (Episodic Pivots)
Find stocks gapping on catalyst with high volume:

```bash
# Basic usage
python -m nexus2.cli.scan_ep

# Custom thresholds
python -m nexus2.cli.scan_ep --min-gap 10 --min-rvol 3

# Export to CSV
python -m nexus2.cli.scan_ep --output ep_results.csv

# All options
python -m nexus2.cli.scan_ep --help
```

### Momentum Scanner
Find stocks meeting KK momentum criteria:

```bash
# Basic usage
python -m nexus2.cli.scan_momentum

# Custom thresholds
python -m nexus2.cli.scan_momentum --min-price 10 --min-adr 5

# Show more results
python -m nexus2.cli.scan_momentum --show-universe

# Export to CSV
python -m nexus2.cli.scan_momentum --output momentum_results.csv
```

## Configuration

Copy `.env.example` to `.env` and configure:
- `FMP_API_KEY` - Financial Modeling Prep API key
- `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` - Alpaca API credentials
- `TRADING_MODE` - SIMULATION, PAPER, or LIVE

## Trading Mode

**IMPORTANT**: Default mode is SIMULATION. Alpaca modes require credentials.

| Mode | Broker | Description |
|------|--------|-------------|
| `SIMULATION` | PaperBroker | Local simulation, no external API (default) |
| `PAPER` | AlpacaBroker | Alpaca paper trading API (no real money) |
| `LIVE` | AlpacaBroker | ⚠️ REAL MONEY - requires explicit confirmation |

```bash
# In .env
TRADING_MODE=SIMULATION  # Local simulation (no API needed)
TRADING_MODE=PAPER       # Alpaca paper trading
TRADING_MODE=LIVE        # ⚠️ Alpaca LIVE (real money!)
```

### Verify Alpaca Connectivity

```bash
python -m nexus2.cli.test_alpaca
```

## Running Tests

```bash
pytest
pytest --cov=nexus2  # With coverage
```

## API Server

Start the FastAPI backend:

```bash
uvicorn nexus2.api.main:app --reload
```

**Endpoints:**
- `GET /health` — Health check
- `POST /orders` — Create order
- `GET /orders` — List orders
- `POST /orders/{id}/submit` — Submit to broker
- `GET /positions` — List positions
- `POST /positions/{id}/partial-exit` — Take partial profit
- `POST /positions/{id}/close` — Close position
- `POST /trade` — Quick trade (order + execute + position)
- `POST /scanner/run` — Run scanner

## Automation Architecture

The automation system has three coordinated components:

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│ POST /automation/scheduler/start                            │
│                                                             │
│ Automatically starts:                                       │
│ 1. Engine (scan execution)                                  │
│ 2. PositionMonitor (intraday checks)                        │
│ 3. EOD Callback (3:45 PM MA trailing check)                 │
└─────────────────────────────────────────────────────────────┘
```

### Scheduler
- **Runs**: Every 15 minutes (configurable)
- **Purpose**: Execute scan cycles (EP, Breakout, HTF scanners)
- **Auto-execute**: If enabled, places bracket orders on top signals

### Position Monitor  
- **Runs**: Every 60 seconds (polling mode)
- **Purpose**: Intraday position protection
- **Checks**:
  - Stop-loss hits → Full exit
  - 1R profit → Move stop to breakeven
  - 3+ days + in profit → KK-style partial exit (50%)

### EOD MA Check
- **Runs**: Once daily at 3:45 PM ET
- **Purpose**: KK-style trailing stop (trend character change)
- **Checks**: Positions 5+ days old, compares daily close to 10/20 EMA
- **Logic**: AUTO mode selects MA based on ADR%:
  - ADR ≥ 5% → Use 10 EMA (tighter trailing for hot stocks)
  - ADR < 5% → Use 20 EMA (wider trailing for slower movers)

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /automation/scheduler/start` | Start all automation |
| `POST /automation/scheduler/stop` | Stop all automation |
| `GET /automation/scheduler/status` | Scheduler status |
| `GET /automation/monitor/status` | Monitor status |
| `POST /automation/ma-check` | Manual EOD check |

**Swagger UI:** http://localhost:8000/docs

## Frontend Dashboard

See [Quick Start Step 4](#4-start-frontend) to run the frontend.

**Features:**
- Dashboard with open positions
- Automation control panel
- Scanner results + signal stream
- Trade execution
- Position management (partial/close)

## Project Status

| Component | Status |
|-----------|--------|
| Domain (Scanner, EP, Risk, Orders, Positions) | ✅ Complete |
| Adapters (Market Data, Broker, Notifications) | ✅ Complete |
| API (FastAPI) | ✅ Complete |
| Frontend (Next.js) | ✅ Dashboard + Automation |
| Tests | ✅ 115 passing |

## Development Workflow

### Daily Development

```powershell
# Terminal 1: Backend (from project root)
.venv\Scripts\activate
uvicorn nexus2.api.main:app --reload

# Terminal 2: Frontend (from nexus2/frontend)
npm run dev
```

### Running Tests

```powershell
pytest                          # Run all tests
pytest --cov=nexus2             # With coverage
pytest tests/test_scanner.py    # Specific file
```

### Database Location

The SQLite database is at `data/nexus.db`. Contains positions, orders, and settings.

> ⚠️ **Do not delete unless troubleshooting schema errors**. Deleting wipes all trade history.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **FMP rate limit errors** | Check your plan limits. Paid tier: 300/min. |
| **Alpaca connection failed** | Check ALPACA_KEY/SECRET in `.env` |
| **Frontend not loading** | Ensure backend is running first |
| **"No such column" errors** | Database schema changed - delete `data/nexus.db` |
| **WebSocket disconnects** | Normal browser behavior - auto-reconnects |

## VPS Deployment (tmux)

For persistent sessions on a remote VPS, use tmux.

### Quick Commands

```bash
# Attach to existing Nexus session
tmux attach -t nexus

# Update code and let uvicorn auto-reload
git pull

# Detach without stopping (keep running)
Ctrl+B, then D
```

### First-Time Setup

```bash
# Create new session
tmux new -s nexus

# Start backend
cd ~/Nexus
source .venv/bin/activate
uvicorn nexus2.api.main:app --reload --host 0.0.0.0

# Detach: Ctrl+B, then D
```

> 📖 **Full tmux reference**: See [docs/tmux_reference.md](../docs/tmux_reference.md) for advanced commands and window management.

## Links

- [FMP API Documentation](https://site.financialmodelingprep.com/developer/docs)
- [Alpaca API Documentation](https://docs.alpaca.markets/)
- [Roadmap](../ROADMAP.md)
