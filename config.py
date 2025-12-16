"""
Module: Configuration Management (Nexus Edition)
Version: 2.1.1
Changelog:
- v2.1.1: PATH STABILITY FIX.
          - Changed BASE_DIR to use os.path.abspath(__file__) instead of os.getcwd().
          - This ensures paths are always relative to the ROOT, no matter where scripts are run.
- v2.1.0: Added support for Account B (Nexus).
"""
import os
from dotenv import load_dotenv

# Load environment variables (from .env file)
# Note: load_dotenv() works best if .env is in the same directory as the script running it,
# or explicit path is provided. Since config.py is in root, we can infer .env is here.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# --- API KEYS (Account A: Primary) ---
FMP_KEY = os.environ.get("FMP_API_KEY")
ALPACA_KEY_A = os.environ.get("APCA_API_KEY_ID")
ALPACA_SECRET_A = os.environ.get("APCA_API_SECRET_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK")

# --- API KEYS (Account B: Comparison/A-B Test) ---
ALPACA_KEY_B = os.environ.get("APCA_API_KEY_ID_B")
ALPACA_SECRET_B = os.environ.get("APCA_API_SECRET_KEY_B")

# --- PORTS & URLS ---
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"

# --- DIRECTORY SETUP ---
# CRITICAL FIX: Base Dir is now the directory containing THIS file (Nexus Root)
DATA_DIR = os.path.join(BASE_DIR, "data")

# Create data dir if it doesn't exist to prevent crashes
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# --- FILE PATHS (Updated for Nexus Architecture) ---
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.txt")
ALERTS_FILE = os.path.join(DATA_DIR, "daily_alerts.csv")
TRADE_LOG_FILE = os.path.join(DATA_DIR, "trade_log.csv")
USER_CONFIG_FILE = os.path.join(DATA_DIR, "trading_config.json")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "my_portfolio.txt")
KILL_SWITCH_FILE = os.path.join(BASE_DIR, "STOP_SNIPER") # Keep in Root for easy access

# Scanner Output Files
MOMENTUM_RESULTS_CSV = os.path.join(DATA_DIR, "momentum_results.csv")
RISK_REPORT_CSV = os.path.join(DATA_DIR, "daily_risk_report.csv")
CSV_FILE = MOMENTUM_RESULTS_CSV # Alias for backward compatibility

# --- DIRECTORIES ---
CHART_DIR_KK = os.path.join(BASE_DIR, "charts_kk")
CHART_DIR_EP = os.path.join(BASE_DIR, "charts_ep")

# --- SCANNER SETTINGS ---
MAX_THREADS = 5
BATCH_SIZE = 50