"""
Configuration Loader

Loads environment variables from .env file in project root.
"""

import os
from pathlib import Path

# Find project root (where .env should be)
# Walk up from this file until we find .env or nexus2 root
_current = Path(__file__).resolve()
_root = _current.parent  # nexus2/

# Try to load .env from nexus2/ directory
_env_file = _root / ".env"
if not _env_file.exists():
    # Also check parent (Nexus/) for legacy location
    _env_file = _root.parent / ".env"

# Load dotenv if available
try:
    from dotenv import load_dotenv
    if _env_file.exists():
        load_dotenv(_env_file)
        print(f"[Config] Loaded: {_env_file}")
except ImportError:
    # dotenv not installed, rely on system env vars
    pass


def get_env(key: str, default: str = "") -> str:
    """Get environment variable."""
    return os.environ.get(key, default)


# API Keys - FMP
FMP_API_KEY = get_env("FMP_API_KEY") or get_env("FMP_KEY")

# API Keys - Alpaca (Account A is default, Account B available)
# Uses Clay's existing naming convention
ALPACA_KEY = get_env("APCA_API_KEY_ID") or get_env("ALPACA_KEY")
ALPACA_SECRET = get_env("APCA_API_SECRET_KEY") or get_env("ALPACA_SECRET")

# Account B (optional)
ALPACA_KEY_B = get_env("APCA_API_KEY_ID_B")
ALPACA_SECRET_B = get_env("APCA_API_SECRET_KEY_B")

# Trading Mode
TRADING_MODE = get_env("TRADING_MODE", "SIMULATION")

# Discord Webhook
DISCORD_WEBHOOK = get_env("DISCORD_WEBHOOK")

# Schwab API (for Level 2 bid/ask quotes)
SCHWAB_CLIENT_ID = get_env("SCHWAB_CLIENT_ID")
SCHWAB_CLIENT_SECRET = get_env("SCHWAB_CLIENT_SECRET")

# Discord Bot (for divergence approval reactions)
DISCORD_BOT_TOKEN = get_env("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = get_env("DISCORD_CHANNEL_ID")

# Alpha Vantage (4th quote source - optional)
ALPHA_VANTAGE_API_KEY = get_env("ALPHA_VANTAGE_API_KEY")

# Validate on import
if not FMP_API_KEY:
    print("[Config] WARNING: FMP_API_KEY not set")
if not ALPACA_KEY or not ALPACA_SECRET:
    print("[Config] WARNING: ALPACA keys not set (checked APCA_API_KEY_ID and ALPACA_KEY)")
