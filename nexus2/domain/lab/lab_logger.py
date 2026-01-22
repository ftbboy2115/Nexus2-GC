"""
Lab Logger

Dedicated logging for R&D Lab operations (backtests, experiments, agents).
Logs to nexus2/logs/lab.log with daily rotation.
"""

import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any, List


# Create logs directory (same as automation logger)
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Configure lab logger
_lab_logger: Optional[logging.Logger] = None
_lab_configured: bool = False


def _get_lab_file_handler() -> TimedRotatingFileHandler:
    """Create the shared lab file handler."""
    log_file = LOGS_DIR / "lab.log"
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=14,  # Keep 14 days of experiment logs
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    
    # Format: timestamp | level | module | message
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    return file_handler


def configure_lab_logging() -> None:
    """
    Configure all lab module loggers to write to lab.log.
    
    This adds the lab file handler to the parent 'nexus2.domain.lab' logger,
    so all child loggers (orchestrator, backtest_runner, etc.) inherit it.
    
    Call this once at startup to redirect all lab logs to the dedicated file.
    """
    global _lab_configured
    
    if _lab_configured:
        return
    
    # Configure the parent logger for all lab modules
    lab_parent = logging.getLogger("nexus2.domain.lab")
    lab_parent.setLevel(logging.INFO)
    
    # Add file handler if not already present
    if not any(isinstance(h, TimedRotatingFileHandler) for h in lab_parent.handlers):
        lab_parent.addHandler(_get_lab_file_handler())
    
    # Don't propagate to root logger (prevents duplicate stdout logs)
    lab_parent.propagate = False
    
    _lab_configured = True


def get_lab_logger() -> logging.Logger:
    """Get or create the lab file logger."""
    global _lab_logger
    
    if _lab_logger is None:
        # Ensure lab logging is configured
        configure_lab_logging()
        
        _lab_logger = logging.getLogger("nexus2.lab")
        _lab_logger.setLevel(logging.INFO)
        
        # Prevent duplicate handlers
        if not _lab_logger.handlers:
            _lab_logger.addHandler(_get_lab_file_handler())
    
    return _lab_logger


# =============================================================================
# BACKTEST LOGGING
# =============================================================================

def log_backtest_start(
    strategy_name: str,
    strategy_version: str,
    start_date: str,
    end_date: str,
    initial_capital: float,
) -> None:
    """Log when a backtest starts."""
    logger = get_lab_logger()
    logger.info(
        f"BACKTEST_START | strategy={strategy_name} v{strategy_version} | "
        f"range={start_date} to {end_date} | capital=${initial_capital:,.0f}"
    )


def log_backtest_complete(
    strategy_name: str,
    result_id: str,
    total_trades: int,
    win_rate: float,
    total_pnl: float,
    duration_seconds: float,
) -> None:
    """Log backtest completion with summary."""
    logger = get_lab_logger()
    logger.info(
        f"BACKTEST_COMPLETE | id={result_id} | strategy={strategy_name} | "
        f"trades={total_trades} | win_rate={win_rate:.1%} | pnl=${total_pnl:,.2f} | "
        f"duration={duration_seconds:.1f}s"
    )


def log_backtest_trade(
    symbol: str,
    entry_price: float,
    exit_price: float,
    shares: int,
    pnl: float,
    outcome: str,
    exit_reason: str,
) -> None:
    """Log individual trade from backtest."""
    logger = get_lab_logger()
    logger.info(
        f"  TRADE | {symbol} | entry=${entry_price:.2f} exit=${exit_price:.2f} | "
        f"shares={shares} | pnl=${pnl:.2f} | {outcome} ({exit_reason})"
    )


# =============================================================================
# HISTORICAL DATA LOGGING
# =============================================================================

def log_data_fetch(
    data_type: str,
    symbol: str,
    date_range: str,
    source: str,
    cached: bool,
) -> None:
    """Log historical data fetch."""
    logger = get_lab_logger()
    cache_status = "CACHE_HIT" if cached else "FETCH"
    logger.debug(
        f"DATA_{cache_status} | {data_type} | {symbol} | {date_range} | source={source}"
    )


def log_universe_load(
    date: str,
    symbol_count: int,
    source: str,
) -> None:
    """Log universe/gapper load."""
    logger = get_lab_logger()
    logger.info(
        f"UNIVERSE_LOAD | date={date} | symbols={symbol_count} | source={source}"
    )


# =============================================================================
# EXPERIMENT LOGGING
# =============================================================================

def log_experiment_start(
    experiment_id: str,
    hypothesis: str,
    baseline_strategy: str,
    variant_strategy: str,
) -> None:
    """Log experiment start."""
    logger = get_lab_logger()
    logger.info(
        f"EXPERIMENT_START | id={experiment_id} | "
        f"baseline={baseline_strategy} vs variant={variant_strategy}"
    )
    logger.info(f"  HYPOTHESIS | {hypothesis[:100]}...")


def log_experiment_result(
    experiment_id: str,
    recommendation: str,
    improvement_score: float,
    summary: str,
) -> None:
    """Log experiment result."""
    logger = get_lab_logger()
    logger.info(
        f"EXPERIMENT_RESULT | id={experiment_id} | "
        f"recommendation={recommendation} | score={improvement_score:.2f}"
    )
    logger.info(f"  SUMMARY | {summary}")


# =============================================================================
# AGENT LOGGING
# =============================================================================

def log_agent_action(
    agent_name: str,
    action: str,
    details: str = "",
) -> None:
    """Log agent action (researcher, coder, evaluator)."""
    logger = get_lab_logger()
    logger.info(f"AGENT | {agent_name} | {action} | {details[:80]}")


def log_agent_error(
    agent_name: str,
    error: str,
) -> None:
    """Log agent error."""
    logger = get_lab_logger()
    logger.error(f"AGENT_ERROR | {agent_name} | {error}")
