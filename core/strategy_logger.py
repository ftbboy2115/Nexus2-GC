# core/strategy_logger.py

"""
Strategy Logger (v1.0.0)
------------------------
Append-only logging of strategy objects produced by the Strategy Engine.

Design goals:
- Never break scanners (logging failures are swallowed).
- Append-only JSONL format for easy streaming & analytics.
- Single unified log across all strategies and scanners.
"""

import json
import os
from datetime import datetime

import config

LOGGER_VERSION = "1.0.0"

LOG_PATH = os.path.join(config.DATA_DIR, "strategy_log.jsonl")


def log_strategy(strategy: dict) -> None:
    """
    Append a strategy object to the unified strategy log.

    - Ensures the directory exists.
    - Adds a 'logged_at' timestamp if missing.
    - Swallows all exceptions to avoid impacting scanners.

    Args:
        strategy: Dict produced by Strategy Engine's build_strategy().
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

        # Add a timestamp if not present
        if "logged_at" not in strategy:
            strategy["logged_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(strategy) + "\n")

    except Exception:
        # Logging must never break the pipeline
        pass