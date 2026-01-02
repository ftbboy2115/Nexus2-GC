# core/strategy_error_logger.py

"""
Strategy Error Logger (v1.0.0)
------------------------------
Append-only error logging for Strategy Engine and Catalyst Engine.

Design goals:
- Never interrupt scanner execution.
- Always record internal failures for audit and debugging.
- Keep logs human-readable and timestamped.
"""

import os
from datetime import datetime
import config

ERROR_LOG_PATH = os.path.join(config.DATA_DIR, "strategy_errors.log")


def log_strategy_error(symbol: str, context: str, error: Exception) -> None:
    """
    Append an error entry to the strategy error log.

    Args:
        symbol: Ticker symbol involved in the failure.
        context: Description of the operation that failed.
        error: Exception object.
    """
    try:
        os.makedirs(os.path.dirname(ERROR_LOG_PATH), exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = (
            f"{timestamp} | symbol={symbol} | context={context} | "
            f"error={type(error).__name__}: {error}\n"
        )

        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)

    except Exception:
        # Must never break the pipeline
        pass