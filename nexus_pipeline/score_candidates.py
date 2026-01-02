"""
Stage 3: Score candidates using StrategyEngineV2.

- Reads:
    - data/contexts.json  (output from Stage 2)
- Hydrates each record into a StrategyContext
- Runs StrategyEngineV2.score()
- Writes:
    - data/scored.json
    - logs/scoring.log

This is INPUT to Stage 4 (signal filtering).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Import your real engine + dataclass
from core.strategy_engine_v2 import StrategyContext, StrategyEngineV2


# ==============================================================================
# PATHS
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

CONTEXTS_INPUT_JSON = DATA_DIR / "contexts.json"
SCORED_OUTPUT_JSON = DATA_DIR / "scored.json"
SCORING_LOG_FILE = LOG_DIR / "scoring.log"


# ==============================================================================
# LOGGING
# ==============================================================================

def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("score_candidates")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fh = logging.FileHandler(SCORING_LOG_FILE, mode="a", encoding="utf-8")
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

def load_contexts(logger: logging.Logger) -> Dict[str, Any]:
    if not CONTEXTS_INPUT_JSON.exists():
        logger.error(f"Contexts input file not found: {CONTEXTS_INPUT_JSON}")
        return {"metadata": {}, "contexts": []}

    with open(CONTEXTS_INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    contexts = data.get("contexts", [])
    logger.info(f"Loaded {len(contexts)} contexts from {CONTEXTS_INPUT_JSON}")
    return data


def hydrate_context(raw: Dict[str, Any]) -> StrategyContext:
    """
    Convert Stage 2 dict into a real StrategyContext dataclass.
    """
    return StrategyContext(
        symbol=raw["symbol"],
        scanner=raw["scanner"],
        catalyst_score=raw.get("catalyst_score"),
        rs_rank=raw.get("rs_rank"),
        rvol=raw.get("rvol"),
        trend_label=raw.get("trend_label"),
        move_pct=raw.get("move_pct"),
        pullback_pct=raw.get("pullback_pct"),
        gap_pct=raw.get("gap_pct"),
        float_m=raw.get("float_m"),
        dollar_vol_m=raw.get("dollar_vol_m"),
    )


# ==============================================================================
# MAIN
# ==============================================================================

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger = setup_logging()
    logger.info("=== Stage 3: Scoring started ===")

    # Load .env (not strictly needed here, but consistent with pipeline)
    env_path = ROOT_DIR / ".env"
    load_dotenv(env_path)

    # Load contexts from Stage 2
    data = load_contexts(logger)
    raw_contexts: List[Dict[str, Any]] = data.get("contexts", [])

    if not raw_contexts:
        logger.warning("No contexts found; nothing to score.")
        payload = {
            "metadata": {
                "generated_at": datetime.now(UTC).isoformat(),
                "source": "Stage3",
                "record_count": 0,
            },
            "scored": [],
        }
        with open(SCORED_OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"Wrote empty scored file to {SCORED_OUTPUT_JSON}")
        logger.info("=== Stage 3: Scoring completed ===")
        return

    engine = StrategyEngineV2()
    scored_records = []

    for raw in raw_contexts:
        ctx = hydrate_context(raw)
        catalyst_tags = raw.get("catalyst_tags", [])

        result = engine.score(ctx, catalyst_tags)

        scored_records.append({
            "symbol": ctx.symbol,
            "scanner": ctx.scanner,
            "score": result.score,
            "conviction": result.conviction,
            "components": result.components,
            "context": raw,  # keep original context for transparency
        })

        logger.debug(
            f"{ctx.symbol}: score={result.score}, "
            f"conviction={result.conviction}, components={result.components}"
        )

    logger.info(f"Scored {len(scored_records)} candidates.")

    payload = {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "Stage3",
            "record_count": len(scored_records),
        },
        "scored": scored_records,
    }

    with open(SCORED_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    logger.info(f"Wrote scored results to {SCORED_OUTPUT_JSON}")
    logger.info("=== Stage 3: Scoring completed ===")


if __name__ == "__main__":
    main()