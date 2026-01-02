"""
Module: Configuration Management (Nexus Edition)
Version: 3.9.0
Changelog:
- v3.9.0: Added centralized FMP endpoint constants for hybrid Stage 1 scanner.
          Ensures all FMP URLs are managed in one place and imported by scanners.
- v2.2.0: Absolute Path Hardening
          - BASE_DIR and DATA_DIR now use os.path.abspath() to guarantee
            consistent resolution regardless of working directory.
- v2.1.1: PATH STABILITY FIX.
          - Changed BASE_DIR to use os.path.abspath(__file__) instead of os.getcwd().
- v2.1.0: Added support for Account B (Nexus).
"""

import os
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# BASE DIRECTORY (ABSOLUTE PATH HARDENING)
# ------------------------------------------------------------------------------
# Absolute path to the Nexus root directory (directory containing config.py)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Load environment variables from .env in the root directory
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ------------------------------------------------------------------------------
# API KEYS (Account A: Primary)
# ------------------------------------------------------------------------------
FMP_KEY = os.environ.get("FMP_API_KEY")
ALPACA_KEY_A = os.environ.get("APCA_API_KEY_ID")
ALPACA_SECRET_A = os.environ.get("APCA_API_SECRET_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK")

# ------------------------------------------------------------------------------
# API KEYS (Account B: Comparison/A-B Test)
# ------------------------------------------------------------------------------
ALPACA_KEY_B = os.environ.get("APCA_API_KEY_ID_B")
ALPACA_SECRET_B = os.environ.get("APCA_API_SECRET_KEY_B")

# ------------------------------------------------------------------------------
# PORTS & URLS
# ------------------------------------------------------------------------------
ALPACA_BASE_TRADE_URL = "https://paper-api.alpaca.markets"
ALPACA_BASE_DATA_URL = "https://data.alpaca.markets/v2"

# ------------------------------------------------------------------------------
# FMP ENDPOINTS (Centralized for Nexus)
# ------------------------------------------------------------------------------
# These are used by Stage 1 (universe scan) and any future scanners.
# Keeping them here ensures consistent routing and easy overrides.
FMP_GAINERS_PREMARKET = "https://financialmodelingprep.com/api/v3/stock/gainers-premarket"
FMP_ACTIVES_PREMARKET = "https://financialmodelingprep.com/api/v3/stock/actives-premarket"
FMP_GAINERS_REGULAR = "https://financialmodelingprep.com/api/v3/stock/gainers"
FMP_ACTIVES_REGULAR = "https://financialmodelingprep.com/api/v3/stock/actives"

# ------------------------------------------------------------------------------
# DIRECTORY SETUP (ABSOLUTE PATH HARDENING)
# ------------------------------------------------------------------------------
# Absolute path to the data directory
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "data"))

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# ------------------------------------------------------------------------------
# FILE PATHS (Updated for Nexus Architecture)
# ------------------------------------------------------------------------------
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.txt")
ALERTS_FILE = os.path.join(DATA_DIR, "daily_alerts.csv")
TRADE_LOG_FILE = os.path.join(DATA_DIR, "trade_log.csv")
USER_CONFIG_FILE = os.path.join(DATA_DIR, "trading_config.json")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "my_portfolio.txt")
KILL_SWITCH_FILE = os.path.join(BASE_DIR, "STOP_SNIPER")  # Keep in Root for easy access

# Scanner Output Files
MOMENTUM_RESULTS_CSV = os.path.join(DATA_DIR, "momentum_results.csv")
RISK_REPORT_CSV = os.path.join(DATA_DIR, "daily_risk_report.csv")
CSV_FILE = MOMENTUM_RESULTS_CSV  # Alias for backward compatibility

# ------------------------------------------------------------------------------
# DIRECTORIES
# ------------------------------------------------------------------------------
CHART_DIR_KK = os.path.join(BASE_DIR, "charts_kk")
CHART_DIR_EP = os.path.join(BASE_DIR, "charts_ep")

# ------------------------------------------------------------------------------
# SCANNER SETTINGS
# ------------------------------------------------------------------------------
MAX_THREADS = 5
BATCH_SIZE = 50

# ==============================================================================
# WORKER GOVERNANCE (Scanner-Specific Baselines)
# ==============================================================================

# These values define the *baseline* worker counts for each scanner.
# WorkerController will adjust dynamically based on:
# - time of day
# - API latency
# - rate-limit usage
# - error rate
# - min/max caps

WORKER_BASELINES = {
    "TREND_DAILY": 48,   # API-light, highly parallel
    "HTF": 24,           # heavier per symbol, but your machine can handle more
    "EP": 12,            # heaviest scanner; keep conservative
}

# Hard ceilings for each scanner (environment-dependent)
WORKER_HARD_CAPS = {
    "TREND_DAILY": 64,
    "HTF": 48,
    "EP": 24,
}

# Global API rate-limit budget (per minute)
MAX_CALLS_PER_MIN = 300