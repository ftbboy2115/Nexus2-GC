"""
Stage 4: Filter scored candidates into actionable signals.

- Reads:
    - data/scored.json  (output from Stage 3)
- Applies trading rules:
    - min_score
    - allowed conviction tiers
    - liquidity / float constraints (via components)
    - optional max number of signals
- Writes:
    - data/signals.json
    - logs/signals.log

This is INPUT to Stage 5 (execution via Alpaca paper/live).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv


# ==============================================================================
# CONFIG
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

SCORED_INPUT_JSON = DATA_DIR / "scored.json"
SIGNALS_OUTPUT_JSON = DATA_DIR / "signals.json"
SIGNALS_LOG_FILE = LOG_DIR / "signals.log"

# Core filtering rules (tune these as you see real data)
MIN_SCORE = 30               # minimum StrategyEngine score
ALLOWED_CONVICTIONS = {"A", "B", "C"}
MIN_LIQUIDITY_COMPONENT =  -6  # from components["liquidity"]
MIN_FLOAT_COMPONENT = -10     # allow some penalty, but not massive
MAX_SIGNALS = 20             # cap number of signals per run


# ==============================================================================
# DATA STRUCTURES
# ==============================================================================

@dataclass
class SignalRecord:
    """
    Final signal record handed to execution stage.

    Keeps:
    - symbol, scanner
    - score, conviction
    - key components (liquidity, float, catalyst, etc.)
    - original context + components for full transparency
    """
    symbol: str
    scanner: str
    score: int
    conviction: str
    liquidity_component: float
    float_component: float
    catalyst_component: float
    rs_component: float

    context: Dict[str, Any]
    components: Dict[str, float]


# ==============================================================================
# LOGGING
# ==============================================================================

def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("filter_signals")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fh = logging.FileHandler(SIGNALS_LOG_FILE, mode="a", encoding="utf-8")
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

def load_scored(logger: logging.Logger) -> Dict[str, Any]:
    if not SCORED_INPUT_JSON.exists():
        logger.error(f"Scored input file not found: {SCORED_INPUT_JSON}")
        return {"metadata": {}, "scored": []}

    with open(SCORED_INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    scored = data.get("scored", [])
    logger.info(f"Loaded {len(scored)} scored records from {SCORED_INPUT_JSON}")
    return data


def passes_filters(rec: Dict[str, Any], logger: logging.Logger) -> bool:
    """
    Decide whether a scored record becomes a signal.
    """
    symbol = rec.get("symbol")
    score = rec.get("score", 0)
    conviction = rec.get("conviction", "C")
    components = rec.get("components", {})

    if conviction not in ALLOWED_CONVICTIONS:
        logger.debug(f"{symbol}: reject due to conviction={conviction}")
        return False

    if score < MIN_SCORE:
        logger.debug(f"{symbol}: reject due to score={score} < MIN_SCORE={MIN_SCORE}")
        return False

    liquidity = float(components.get("liquidity", 0.0))
    if liquidity < MIN_LIQUIDITY_COMPONENT:
        logger.debug(
            f"{symbol}: reject due to liquidity_component={liquidity} "
            f"< MIN_LIQUIDITY_COMPONENT={MIN_LIQUIDITY_COMPONENT}"
        )
        return False

    flt = float(components.get("float", 0.0))
    if flt < MIN_FLOAT_COMPONENT:
        logger.debug(
            f"{symbol}: reject due to float_component={flt} "
            f"< MIN_FLOAT_COMPONENT={MIN_FLOAT_COMPONENT}"
        )
        return False

    # You can add more rules here: catalyst, RS, structure, etc.

    return True


def build_signal(rec: Dict[str, Any]) -> SignalRecord:
    components = rec.get("components", {})
    context = rec.get("context", {})

    return SignalRecord(
        symbol=rec["symbol"],
        scanner=rec["scanner"],
        score=int(rec["score"]),
        conviction=rec["conviction"],
        liquidity_component=float(components.get("liquidity", 0.0)),
        float_component=float(components.get("float", 0.0)),
        catalyst_component=float(components.get("catalyst", 0.0)),
        rs_component=float(components.get("rs", 0.0)),
        context=context,
        components=components,
    )


# ==============================================================================
# MAIN
# ==============================================================================

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger = setup_logging()
    logger.info("=== Stage 4: Filter signals started ===")

    # Load .env for consistency with pipeline, even if not needed here
    env_path = ROOT_DIR / ".env"
    load_dotenv(env_path)

    data = load_scored(logger)
    scored_records: List[Dict[str, Any]] = data.get("scored", [])

    if not scored_records:
        logger.warning("No scored records found; nothing to filter.")
        payload = {
            "metadata": {
                "generated_at": datetime.now(UTC).isoformat(),
                "source": "Stage4",
                "record_count": 0,
            },
            "signals": [],
        }
        with open(SIGNALS_OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"Wrote empty signals file to {SIGNALS_OUTPUT_JSON}")
        logger.info("=== Stage 4: Filter signals completed ===")
        return

    accepted: List[SignalRecord] = []
    rejected_count = 0

    for rec in scored_records:
        if passes_filters(rec, logger):
            sig = build_signal(rec)
            accepted.append(sig)
        else:
            rejected_count += 1

    # Enforce MAX_SIGNALS (highest score first)
    accepted.sort(key=lambda s: s.score, reverse=True)
    if MAX_SIGNALS is not None and len(accepted) > MAX_SIGNALS:
        logger.info(
            f"Truncating signals from {len(accepted)} to MAX_SIGNALS={MAX_SIGNALS}"
        )
        accepted = accepted[:MAX_SIGNALS]

    logger.info(
        f"Signals summary: accepted={len(accepted)}, rejected={rejected_count}, "
        f"input={len(scored_records)}"
    )

    payload = {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "Stage4",
            "record_count": len(accepted),
            "filters": {
                "min_score": MIN_SCORE,
                "allowed_convictions": sorted(ALLOWED_CONVICTIONS),
                "min_liquidity_component": MIN_LIQUIDITY_COMPONENT,
                "min_float_component": MIN_FLOAT_COMPONENT,
                "max_signals": MAX_SIGNALS,
            },
        },
        "signals": [asdict(s) for s in accepted],
    }

    with open(SIGNALS_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    logger.info(f"Wrote {len(accepted)} signals to {SIGNALS_OUTPUT_JSON}")
    logger.info("=== Stage 4: Filter signals completed ===")


if __name__ == "__main__":
    main()