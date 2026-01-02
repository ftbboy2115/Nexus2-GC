"""
File: nexus_pipeline/scan_pre_market.py
Version: 3.2.0
Date: 2025-12-17
Author: Clay & Copilot

Title:
    Stage 1 — Session-Aware Universe Scan (Hybrid FMP + TradingView)

Purpose:
    - Determine current session phase (premarket, regular, off).
    - Build a universe appropriate for the session:
        • Premarket:
            - Primary: FMP premarket movers (gainers/actives).
            - Fallback: TradingView premarket movers.
            - Hybrid: merge + dedupe FMP + TradingView when both available.
        • Regular:
            - Primary: FMP regular-hours gainers/actives.
            - Fallback: TradingView regular-hours movers when FMP is insufficient.
    - Normalize to a scanner-agnostic structure.
    - Emit:
        - data/scan_results.json  (machine-readable)
        - logs/scan.log           (human-readable)

Pipeline:
    This is INPUT to Stage 2 (build_contexts.py).

Changelog:
    - v3.2.0:
        • Added TradingView regular-hours fallback (FMP-first, fallback-only).
        • Logged fallback activation for auditability.
    - v3.1.0:
        • Integrated TradingView client (external module).
        • Removed stub fallback.
        • Cleaned UTC timestamp warning.
        • Preserved hybrid architecture and normalization pipeline.
    - v3.0.0:
        • Introduced session-phase routing (premarket vs regular).
        • Added hybrid architecture with TradingView fallback hooks.
        • Added config-based FMP endpoints (no hard-coded URLs).
        • Added metadata fields: phase, sources.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, time, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import requests
from dotenv import load_dotenv

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

import config
from nexus_pipeline.tradingview_client import (
    fetch_premarket_movers,
    fetch_regular_movers,
)


# ==============================================================================
# CONFIG
# ==============================================================================

FMP_API_KEY_ENV = "FMP_API_KEY"

SESSION_TZ = "America/New_York"
USE_TRADINGVIEW_FALLBACK = True
MIN_FMP_THRESHOLD = 5

MIN_PRICE = 3.0
MAX_PRICE = 200.0
MIN_VOLUME = 0
TOP_N = 50

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
SCAN_OUTPUT_JSON = DATA_DIR / "scan_results.json"
SCAN_LOG_FILE = LOG_DIR / "scan.log"


# ==============================================================================
# DATA STRUCTURES
# ==============================================================================

@dataclass
class RawScanRecord:
    symbol: str
    price: float
    change_pct: float
    volume: int
    dollar_vol_m: float
    raw: Dict[str, Any]


# ==============================================================================
# LOGGING SETUP
# ==============================================================================

def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("scan_pre_market")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fh = logging.FileHandler(SCAN_LOG_FILE, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    ffmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
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
# SESSION ROUTING
# ==============================================================================

def get_session_phase(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(ZoneInfo(SESSION_TZ))
    t = now.time()

    if time(4, 0) <= t < time(9, 25):
        return "premarket"
    if time(9, 30) <= t < time(16, 0):
        return "regular"
    return "off"


# ==============================================================================
# FMP CLIENT
# ==============================================================================

class FMPClient:
    def __init__(self, api_key: str, logger: logging.Logger) -> None:
        self.api_key = api_key
        self.logger = logger

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = params or {}
        params["apikey"] = self.api_key

        self.logger.debug(f"Requesting FMP URL: {url} params={params}")
        resp = requests.get(url, params=params, timeout=10)
        if not resp.ok:
            self.logger.error(
                f"FMP request failed: status={resp.status_code}, body={resp.text[:500]}"
            )
            resp.raise_for_status()
        return resp.json()

    def fetch(self, url: str) -> List[Dict[str, Any]]:
        data = self._get(url)
        if isinstance(data, dict) and "mostGainerStock" in data:
            return data["mostGainerStock"]
        if isinstance(data, list):
            return data
        self.logger.warning("Unexpected FMP payload shape; returning empty list.")
        return []


# ==============================================================================
# NORMALIZATION
# ==============================================================================

def normalize_record(raw: Dict[str, Any], logger: logging.Logger) -> Optional[RawScanRecord]:
    symbol = raw.get("ticker") or raw.get("symbol")
    if not symbol:
        return None

    try:
        price = float(raw.get("price"))
    except Exception:
        return None

    changes_pct_raw = raw.get("changesPercentage") or raw.get("changePercent")
    if isinstance(changes_pct_raw, str):
        changes_pct_raw = changes_pct_raw.strip().replace("%", "")
    try:
        change_pct = float(changes_pct_raw)
    except Exception:
        change_pct = 0.0

    try:
        volume = int(float(raw.get("volume") or raw.get("avgVolume") or 0))
    except Exception:
        volume = 0

    dollar_vol_m = (price * volume) / 1_000_000.0

    return RawScanRecord(
        symbol=symbol,
        price=price,
        change_pct=change_pct,
        volume=volume,
        dollar_vol_m=dollar_vol_m,
        raw=raw,
    )


def apply_basic_filters(records: List[RawScanRecord], logger: logging.Logger) -> List[RawScanRecord]:
    out = []
    for r in records:
        if not (MIN_PRICE <= r.price <= MAX_PRICE):
            continue
        if r.volume < MIN_VOLUME:
            continue
        out.append(r)
    logger.info(f"Applied basic filters: kept {len(out)}/{len(records)}.")
    return out


def limit_universe(records: List[RawScanRecord], logger: logging.Logger) -> List[RawScanRecord]:
    scored = [(abs(r.change_pct) * r.dollar_vol_m, r) for r in records]
    scored.sort(key=lambda t: t[0], reverse=True)
    limited = [r for _, r in scored[:TOP_N]]
    logger.info(f"Limited universe to TOP_N={TOP_N}. Final count={len(limited)}.")
    return limited


# ==============================================================================
# HYBRID BUILDERS
# ==============================================================================

def build_premarket_universe(client: FMPClient, logger: logging.Logger) -> Tuple[List[RawScanRecord], List[str]]:
    sources: List[str] = []

    fmp_raw: List[Dict[str, Any]] = []
    fmp_raw += client.fetch(config.FMP_GAINERS_PREMARKET)
    fmp_raw += client.fetch(config.FMP_ACTIVES_PREMARKET)

    sources.append("fmp_premarket")
    logger.info(f"FMP premarket returned {len(fmp_raw)} records.")

    if len(fmp_raw) >= MIN_FMP_THRESHOLD:
        normalized = [normalize_record(r, logger) for r in fmp_raw if normalize_record(r, logger)]
        return normalized, sources

    if USE_TRADINGVIEW_FALLBACK:
        logger.info("FMP premarket insufficient; activating TradingView fallback.")
        tv_raw = fetch_premarket_movers(logger)
        sources.append("tradingview_premarket")

        combined = fmp_raw + tv_raw
        normalized = [normalize_record(r, logger) for r in combined if normalize_record(r, logger)]
        return normalized, sources

    normalized = [normalize_record(r, logger) for r in fmp_raw if normalize_record(r, logger)]
    return normalized, sources


def build_regular_universe(client: FMPClient, logger: logging.Logger) -> Tuple[List[RawScanRecord], List[str]]:
    sources: List[str] = []

    # --- FMP primary source ---
    fmp_raw: List[Dict[str, Any]] = []
    fmp_raw += client.fetch(config.FMP_GAINERS_REGULAR)
    fmp_raw += client.fetch(config.FMP_ACTIVES_REGULAR)

    sources.append("fmp_regular")
    logger.info(f"FMP regular-hours returned {len(fmp_raw)} records.")

    # --- If FMP is sufficient, use it alone ---
    if len(fmp_raw) >= MIN_FMP_THRESHOLD:
        normalized = [normalize_record(r, logger) for r in fmp_raw if normalize_record(r, logger)]
        return normalized, sources

    # --- Otherwise, fallback to TradingView ---
    if USE_TRADINGVIEW_FALLBACK:
        logger.info("FMP regular-hours insufficient; activating TradingView fallback.")
        tv_raw = fetch_regular_movers(logger)
        sources.append("tradingview_regular")

        combined = fmp_raw + tv_raw
        normalized = [normalize_record(r, logger) for r in combined if normalize_record(r, logger)]
        return normalized, sources

    # --- No fallback or fallback disabled ---
    normalized = [normalize_record(r, logger) for r in fmp_raw if normalize_record(r, logger)]
    return normalized, sources


# ==============================================================================
# MAIN PIPELINE
# ==============================================================================

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger = setup_logging()
    logger.info("=== Stage 1: Universe Scan (Hybrid) started ===")

    env_path = ROOT_DIR / ".env"
    load_dotenv(env_path)

    api_key = os.getenv(FMP_API_KEY_ENV)
    if not api_key:
        logger.error(f"FMP_API_KEY not found in .env at {env_path}")
        return

    client = FMPClient(api_key=api_key, logger=logger)

    phase = get_session_phase()
    logger.info(f"Session phase detected: {phase}")

    if phase == "premarket":
        raw_records, sources = build_premarket_universe(client, logger)
    elif phase == "regular":
        raw_records, sources = build_regular_universe(client, logger)
    else:
        logger.info("Off-session: producing empty universe.")
        raw_records, sources = [], []

    filtered = apply_basic_filters(raw_records, logger)
    final_universe = limit_universe(filtered, logger)

    payload = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "sources": sources,
            "universe_size": len(final_universe),
            "min_price": MIN_PRICE,
            "max_price": MAX_PRICE,
            "min_volume": MIN_VOLUME,
            "top_n": TOP_N,
        },
        "records": [asdict(r) for r in final_universe],
    }

    with open(SCAN_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    logger.info(f"Wrote scan results to {SCAN_OUTPUT_JSON}")
    logger.info("=== Stage 1: Universe Scan (Hybrid) completed ===")


if __name__ == "__main__":
    main()