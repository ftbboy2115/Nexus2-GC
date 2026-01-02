# core/strategy_engine.py

"""
Strategy Engine (v1.6.0)
------------------------
Unifies scanner outputs into a single strategy object, enriches with
catalyst data, computes pivot/stop for EP setups, applies risk
profiling, computes RS vs SPY, integrates RS v2 leadership metrics,
and logs both strategies and internal errors.

Changelog:
- v1.6.0:
    - Integrated RS v2 Engine output (rs_v2.csv).
    - Added rs_v2_score, rs_percentile, rs_sector_percentile,
      rs_multi_timeframe, rs_raw_mean, rs_raw_trend, rs_raw_acceleration
      to strategy objects.

- v1.5.0:
    - Integrated RS Engine (v1.0.0).
    - Added rs_raw and rs_lookback_days to strategy objects.

- v1.4.0:
    - Integrated Risk Engine (v1.0.0).

- v1.3.0:
    - Added Strategy Error Logger integration.
    - Added daily-candle-based EP pivot/stop computation.

- v1.2.0:
    - Added EP pivot/stop logic (daily candle version).

- v1.1.0:
    - Integrated Strategy Logger.

- v1.0.0:
    - Initial implementation.
"""

import datetime
import os
from typing import Dict, Any

import pandas as pd
import requests

import config
from core.catalyst_engine import get_catalyst_data
from core.strategy_logger import log_strategy
from core.strategy_error_logger import log_strategy_error
from core.risk_engine import get_risk_profile
from core.rs_engine import get_rs_metrics

ENGINE_VERSION = "1.6.0"


# ------------------------------------------------------------
# RS v2 Lookup Loader
# ------------------------------------------------------------

RS_V2_PATH = os.path.join(config.DATA_DIR, "rs_v2.csv")


def load_rs_v2_lookup() -> Dict[str, Dict[str, Any]]:
    """
    Load RS v2 metrics from rs_v2.csv into an in-memory lookup.

    Returns:
        Dict mapping symbol -> RS v2 metrics dict.
    """
    if not os.path.exists(RS_V2_PATH):
        return {}

    try:
        df = pd.read_csv(RS_V2_PATH)
    except Exception:
        # If RS v2 file is missing or corrupt, fail soft and continue
        return {}

    lookup: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        symbol = row.get("symbol")
        if not symbol:
            continue

        lookup[symbol] = {
            "rs_v2_score": row.get("rs_v2_score"),
            "rs_percentile": row.get("rs_percentile"),
            "rs_sector_percentile": row.get("rs_sector_percentile"),
            "rs_multi_timeframe": row.get("rs_multi_timeframe"),
            "rs_raw_mean": row.get("rs_raw_mean"),
            "rs_raw_trend": row.get("rs_raw_trend"),
            "rs_raw_acceleration": row.get("rs_raw_acceleration"),
        }

    return lookup


# Loaded once at import time; strategies read from this cache
RS_V2_LOOKUP = load_rs_v2_lookup()


# ------------------------------------------------------------
# Helper: Fetch latest daily candle
# ------------------------------------------------------------
def _fetch_daily_candle(symbol: str):
    url = (
        f"https://financialmodelingprep.com/api/v3/historical-price-full/"
        f"{symbol}?timeseries=1&apikey={config.FMP_KEY}"
    )

    try:
        res = requests.get(url, timeout=5).json()
        if "historical" not in res or not res["historical"]:
            return None

        candle = res["historical"][0]
        return {
            "open": candle.get("open"),
            "high": candle.get("high"),
            "low": candle.get("low"),
            "close": candle.get("close"),
        }

    except Exception as e:
        log_strategy_error(symbol, "fetch_daily_candle", e)
        return None


# ------------------------------------------------------------
# Helper: EP pivot/stop logic
# ------------------------------------------------------------
def _compute_ep_pivot_stop(symbol: str):
    try:
        candle = _fetch_daily_candle(symbol)
        if not candle:
            return None, None

        pivot = candle["high"]
        stop = candle["low"]
        return pivot, stop

    except Exception as e:
        log_strategy_error(symbol, "compute_ep_pivot_stop", e)
        return None, None


# ------------------------------------------------------------
# Main Strategy Builder
# ------------------------------------------------------------
def build_strategy(symbol: str, setup_type: str, scanner_data: Dict[str, Any]) -> Dict[str, Any]:
    # Catalyst enrichment
    try:
        catalyst_text, catalyst_score = get_catalyst_data(symbol)
    except Exception as e:
        log_strategy_error(symbol, "catalyst_engine", e)
        catalyst_text, catalyst_score = "", 0.0

    # Default pivot/stop from scanner (usually None)
    pivot = scanner_data.get("pivot")
    stop = scanner_data.get("stop")

    # EP-specific pivot/stop override
    if setup_type == "EP":
        try:
            pivot, stop = _compute_ep_pivot_stop(symbol)
        except Exception as e:
            log_strategy_error(symbol, "ep_pivot_stop", e)

    # Compute risk per share
    risk_per_share = None
    if pivot is not None and stop is not None:
        try:
            risk_per_share = pivot - stop
        except Exception as e:
            log_strategy_error(symbol, "risk_per_share", e)

    # RS metrics (v1: per-symbol vs SPY)
    rs_raw = None
    rs_lookback_days = None
    try:
        rs = get_rs_metrics(symbol)
        rs_raw = rs.get("rs_raw")
        rs_lookback_days = rs.get("rs_lookback_days")
    except Exception as e:
        log_strategy_error(symbol, "rs_engine", e)

    # Base strategy object
    strategy: Dict[str, Any] = {
        "symbol": symbol,
        "setup": setup_type,
        "pivot": pivot,
        "stop": stop,
        "risk_per_share": risk_per_share,

        "catalyst": catalyst_text,
        "catalyst_score": catalyst_score,

        "risk_rating": None,            # Risk Engine
        "risk_score": None,             # Risk Engine
        "position_size_factor": None,   # Risk Engine

        # RS v1 (vs SPY)
        "rs_raw": rs_raw,
        "rs_lookback_days": rs_lookback_days,

        # RS v2 fields (leadership metrics)
        "rs_v2_score": None,
        "rs_percentile": None,
        "rs_sector_percentile": None,
        "rs_multi_timeframe": None,
        "rs_raw_mean": None,
        "rs_raw_trend": None,
        "rs_raw_acceleration": None,

        "sector": None,
        "industry": None,
        "rs_score": None,  # reserved for future percentile-based RS
        "adr": None,

        "reason": scanner_data.get("reason", ""),
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "raw_scanner_data": scanner_data,
    }

    # RS v2 enrichment (from rs_v2.csv)
    try:
        rs2 = RS_V2_LOOKUP.get(symbol)
        if rs2:
            strategy.update(rs2)
    except Exception as e:
        log_strategy_error(symbol, "rs_v2_engine", e)

    # Risk Engine enrichment
    try:
        risk_profile = get_risk_profile(strategy)
        strategy["risk_rating"] = risk_profile.get("risk_rating")
        strategy["risk_score"] = risk_profile.get("risk_score")
        strategy["position_size_factor"] = risk_profile.get("position_size_factor")
    except Exception as e:
        log_strategy_error(symbol, "risk_engine", e)

    # Log strategy (never breaks pipeline)
    try:
        log_strategy(strategy)
    except Exception as e:
        log_strategy_error(symbol, "strategy_logger", e)

    return strategy