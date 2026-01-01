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

## Quick Start

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your FMP_API_KEY and ALPACA_KEY/SECRET
```

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

**Swagger UI:** http://localhost:8000/docs

## Frontend Dashboard

```bash
cd nexus2/frontend
npm install
npm run dev
```

Open http://localhost:3000

**Features:**
- Create trades
- View open positions
- Take partial profits
- Close positions
- Real-time updates

## Project Status

| Component | Status |
|-----------|--------|
| Domain (Scanner, EP, Risk, Orders, Positions) | ✅ Complete |
| Adapters (Market Data, Broker, Notifications) | ✅ Complete |
| API (FastAPI) | ✅ Complete |
| Frontend (Next.js) | ✅ Basic dashboard |
| Tests | ✅ 115 passing |

