"""
Automation Logger

Persistent file logging for scanner results and trade execution decisions.
Logs to nexus2/logs/automation.log with daily rotation.
"""

import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import List, Optional, Dict, Any


# Create logs directory
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Configure automation logger
_automation_logger: Optional[logging.Logger] = None


def get_automation_logger() -> logging.Logger:
    """Get or create the automation file logger."""
    global _automation_logger
    
    if _automation_logger is None:
        _automation_logger = logging.getLogger("nexus2.automation")
        _automation_logger.setLevel(logging.INFO)
        
        # Prevent duplicate handlers
        if not _automation_logger.handlers:
            # File handler with daily rotation
            log_file = LOGS_DIR / "automation.log"
            file_handler = TimedRotatingFileHandler(
                log_file,
                when="midnight",
                interval=1,
                backupCount=7,  # Keep 7 days of logs
                encoding="utf-8",
            )
            file_handler.setLevel(logging.INFO)
            
            # Format: timestamp | level | message
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(formatter)
            
            _automation_logger.addHandler(file_handler)
    
    return _automation_logger


def log_scan_start(scan_modes: List[str], settings: Dict[str, Any]) -> None:
    """Log when a scan cycle starts."""
    logger = get_automation_logger()
    logger.info(
        f"SCAN_START | modes={scan_modes} | min_quality={settings.get('min_quality')} | "
        f"min_price=${settings.get('min_price', 5.0)} | stop_mode={settings.get('stop_mode')}"
    )


def log_scan_result(
    total_signals: int,
    ep_count: int,
    breakout_count: int,
    htf_count: int,
    duration_ms: int,
    signals: List[Any],
) -> None:
    """Log scan results with all signals found."""
    logger = get_automation_logger()
    
    logger.info(
        f"SCAN_COMPLETE | signals={total_signals} (EP:{ep_count}, BO:{breakout_count}, HTF:{htf_count}) | "
        f"duration={duration_ms}ms"
    )
    
    # Log each signal
    for sig in signals:
        symbol = getattr(sig, 'symbol', sig.get('symbol', '?'))
        setup_type = getattr(sig, 'setup_type', sig.get('setup_type', '?'))
        if hasattr(setup_type, 'value'):
            setup_type = setup_type.value
        entry_price = getattr(sig, 'entry_price', sig.get('entry_price', 0))
        tactical_stop = getattr(sig, 'tactical_stop', sig.get('tactical_stop', 0))
        quality = getattr(sig, 'quality_score', sig.get('quality_score', 0))
        tier = getattr(sig, 'tier', sig.get('tier', '?'))
        
        logger.info(
            f"  SIGNAL | {symbol} | type={setup_type} | entry=${entry_price} | "
            f"stop=${tactical_stop} | quality={quality} | tier={tier}"
        )


def log_position_sizing(
    symbol: str,
    entry_price: float,
    shares_calculated: int,
    shares_capped: int,
    max_per_symbol: float,
    reason: str = "",
) -> None:
    """Log position sizing calculation and capping."""
    logger = get_automation_logger()
    
    if shares_capped != shares_calculated:
        logger.info(
            f"SIZING_CAP | {symbol} | price=${entry_price:.2f} | "
            f"calculated={shares_calculated} → capped={shares_capped} | "
            f"max_per_symbol=${max_per_symbol:.2f} | {reason}"
        )
    else:
        logger.info(
            f"SIZING | {symbol} | price=${entry_price:.2f} | shares={shares_calculated}"
        )


def log_execution_decision(
    symbol: str,
    shares: int,
    stop_price: float,
    decision: str,  # "EXECUTED", "SKIPPED", "ERROR"
    reason: str = "",
    order_id: str = "",
) -> None:
    """Log trade execution decision."""
    logger = get_automation_logger()
    
    if decision == "EXECUTED":
        logger.info(
            f"TRADE_EXECUTED | {symbol} x {shares} @ stop=${stop_price:.2f} | order_id={order_id}"
        )
    elif decision == "SKIPPED":
        logger.info(
            f"TRADE_SKIPPED | {symbol} | reason={reason}"
        )
    else:
        logger.warning(
            f"TRADE_ERROR | {symbol} | reason={reason}"
        )


def log_cycle_summary(
    executed_count: int,
    skipped_count: int,
    error_count: int,
    executed_symbols: List[str],
    skipped_symbols: List[str],
) -> None:
    """Log end-of-cycle summary."""
    logger = get_automation_logger()
    
    logger.info(
        f"CYCLE_SUMMARY | executed={executed_count} | skipped={skipped_count} | errors={error_count}"
    )
    if executed_symbols:
        logger.info(f"  Executed: {', '.join(executed_symbols)}")
    if skipped_symbols:
        logger.info(f"  Skipped: {', '.join(skipped_symbols)}")
    
    logger.info("-" * 60)  # Separator between cycles
