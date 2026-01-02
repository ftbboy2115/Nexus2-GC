"""
File: nexus_pipeline/execute_paper_trade.py
Stage 5: Execute paper trades (manual confirmation via paper_trader)

Purpose:
    - Read actionable signals from Stage 4
    - Present each signal to the user for confirmation (Option C)
    - Compute entry/stop levels
    - Execute trades via core.paper_trader.submit_buy_order()
    - Log all actions to logs/execution.log
    - Write a machine-readable record to data/executed.json

Inputs:
    - data/signals.json  (from Stage 4)

Outputs:
    - logs/execution.log
    - data/executed.json

Notes:
    - This stage does NOT contain broker logic.
    - All execution is delegated to core.paper_trader.
    - User remains the final gatekeeper for each trade.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Import your existing execution engine
from core import paper_trader


# ==============================================================================
# CONFIG
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

SIGNALS_INPUT_JSON = DATA_DIR / "signals.json"
EXECUTED_OUTPUT_JSON = DATA_DIR / "executed.json"
EXECUTION_LOG_FILE = LOG_DIR / "execution.log"

# Default risk settings for this wrapper
DEFAULT_STOP_PCT = 0.05  # 5% below entry if user doesn't override


# ==============================================================================
# LOGGING
# ==============================================================================

def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("execute_paper_trade")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fh = logging.FileHandler(EXECUTION_LOG_FILE, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    ffmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(ffmt)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    cfmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    ch.setFormatter(cfmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


# ==============================================================================
# HELPERS
# ==============================================================================

def load_signals(logger: logging.Logger) -> Dict[str, Any]:
    if not SIGNALS_INPUT_JSON.exists():
        logger.error(f"Signals input file not found: {SIGNALS_INPUT_JSON}")
        return {"metadata": {}, "signals": []}

    with open(SIGNALS_INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    signals = data.get("signals", [])
    logger.info(f"Loaded {len(signals)} signals from {SIGNALS_INPUT_JSON}")
    return data


def format_signal_summary(sig: Dict[str, Any]) -> str:
    symbol = sig.get("symbol")
    scanner = sig.get("scanner")
    score = sig.get("score")
    conviction = sig.get("conviction")
    comps = sig.get("components", {})
    ctx = sig.get("context", {})

    price = ctx.get("price") or ctx.get("entry_price")
    rs = comps.get("rs")
    liq = comps.get("liquidity")
    flt = comps.get("float")
    cat = comps.get("catalyst")

    parts = [
        f"Symbol={symbol}",
        f"Scanner={scanner}",
        f"Score={score}",
        f"Conviction={conviction}",
        f"Price={price}",
        f"RS={rs}",
        f"LiqComp={liq}",
        f"FloatComp={flt}",
        f"CatalystComp={cat}",
    ]
    return " | ".join(str(p) for p in parts)


def ask_user_confirmation(prompt: str) -> str:
    """
    Return 'y', 's', or 'q'.
    """
    while True:
        ans = input(prompt).strip().lower()
        if ans in {"y", "yes"}:
            return "y"
        if ans in {"s", "skip"}:
            return "s"
        if ans in {"q", "quit"}:
            return "q"
        print("Please enter 'y' (yes), 's' (skip), or 'q' (quit).")


def determine_entry_and_stop(
    sig: Dict[str, Any],
    logger: logging.Logger,
    default_stop_pct: float = DEFAULT_STOP_PCT,
) -> Optional[tuple[float, float]]:
    """
    Determine entry_price and stop_loss for a signal.

    - Uses context['price'] as entry_price if available.
    - Asks user to confirm or override stop percentage.
    """
    ctx = sig.get("context", {})
    raw_price = ctx.get("price") or ctx.get("entry_price")

    if raw_price is None:
        print("   [WARN] No price in context; please enter entry price manually.")
        while True:
            val = input("   Entry price: ").strip()
            try:
                entry_price = float(val)
                break
            except ValueError:
                print("   Invalid number. Try again.")
    else:
        try:
            entry_price = float(raw_price)
        except (TypeError, ValueError):
            print("   [WARN] Invalid price in context; please enter entry price manually.")
            while True:
                val = input("   Entry price: ").strip()
                try:
                    entry_price = float(val)
                    break
                except ValueError:
                    print("   Invalid number. Try again.")

    # Ask user for stop percentage override
    print(f"   Suggested stop: {default_stop_pct * 100:.1f}% below entry.")
    val = input("   Enter stop% below entry (blank to accept default): ").strip()
    if val:
        try:
            stop_pct = float(val) / 100.0
        except ValueError:
            print("   Invalid percentage, using default.")
            stop_pct = default_stop_pct
    else:
        stop_pct = default_stop_pct

    stop_loss = round(entry_price * (1.0 - stop_pct), 2)
    logger.debug(
        f"Computed entry/stop: entry_price={entry_price}, stop_pct={stop_pct}, stop_loss={stop_loss}"
    )
    return entry_price, stop_loss


# ==============================================================================
# MAIN
# ==============================================================================

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger = setup_logging()
    logger.info("=== Stage 5: Execute paper trades started ===")

    # Load .env for consistency with pipeline (paper_trader uses config/env)
    env_path = ROOT_DIR / ".env"
    load_dotenv(env_path)

    data = load_signals(logger)
    signals: List[Dict[str, Any]] = data.get("signals", [])

    if not signals:
        logger.warning("No signals found; nothing to execute.")
        payload = {
            "metadata": {
                "generated_at": datetime.now(UTC).isoformat(),
                "source": "Stage5",
                "record_count": 0,
            },
            "executions": [],
        }
        with open(EXECUTED_OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"Wrote empty executions file to {EXECUTED_OUTPUT_JSON}")
        logger.info("=== Stage 5: Execute paper trades completed ===")
        return

    executions: List[Dict[str, Any]] = []
    logger.info("Presenting signals for manual confirmation (Option C).")

    for idx, sig in enumerate(signals, start=1):
        print("\n------------------------------------------------------------")
        print(f"Signal {idx}/{len(signals)}")
        print(format_signal_summary(sig))

        choice = ask_user_confirmation("Execute this trade? [y]es / [s]kip / [q]uit: ")

        if choice == "q":
            logger.info("User chose to quit execution loop.")
            break

        symbol = sig.get("symbol")
        if choice == "s":
            logger.info(f"{symbol}: user skipped.")
            executions.append({
                "symbol": symbol,
                "action": "SKIP",
                "reason": "user_skip",
                "timestamp": datetime.now(UTC).isoformat(),
                "signal": sig,
            })
            continue

        # choice == "y"
        entry_stop = determine_entry_and_stop(sig, logger)
        if entry_stop is None:
            logger.warning(f"{symbol}: failed to determine entry/stop; skipping.")
            executions.append({
                "symbol": symbol,
                "action": "SKIP",
                "reason": "entry_stop_error",
                "timestamp": datetime.now(UTC).isoformat(),
                "signal": sig,
            })
            continue

        entry_price, stop_loss = entry_stop

        logger.info(f"{symbol}: submitting buy order via paper_trader.")
        try:
            paper_trader.submit_buy_order(symbol, entry_price, stop_loss)
            status = "SUBMITTED"
            error = None
        except Exception as e:
            logger.exception(f"{symbol}: error during submit_buy_order: {e}")
            status = "ERROR"
            error = str(e)

        executions.append({
            "symbol": symbol,
            "action": "BUY",
            "status": status,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "timestamp": datetime.now(UTC).isoformat(),
            "signal": sig,
            "error": error,
        })

    payload = {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "Stage5",
            "record_count": len(executions),
        },
        "executions": executions,
    }

    with open(EXECUTED_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    logger.info(f"Wrote {len(executions)} execution records to {EXECUTED_OUTPUT_JSON}")
    logger.info("=== Stage 5: Execute paper trades completed ===")


if __name__ == "__main__":
    main()