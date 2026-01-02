# core/rs_engine.py

"""
RS Engine (v1.0.0 → 2.0.0)
---------------------------

Purpose:
    - Compute basic Relative Strength vs SPY for a single symbol.
    - RS_raw = stock_return - SPY_return over a fixed lookback window.

v2.0.0 Design:
    - Wraps the original functional design in a class-based engine.
    - Exposes a clean, symbol-level API:

        engine = RSEngine()
        engine.get_rs("NVDA") -> {
            "symbol": "NVDA",
            "rs_value": float | None,   # rs_raw
            "rs_rank": None,            # v1 is not percentile-based
            "raw": {
                "rs_raw": float | None,
                "rs_lookback_days": int,
            }
        }

    - Keeps RS v1 "pure": no cross-sectional ranking,
      no universe-level percentiles, no CSV output.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta

import requests
import config
from core.strategy_error_logger import log_strategy_error


LOOKBACK_DAYS_DEFAULT = 20  # KK-style short-term leadership window


def _fetch_candles(symbol: str, lookback_days: int) -> Optional[Dict[str, Any]]:
    """
    Fetch recent daily candles for a symbol from FMP.

    Returns:
        {
            "dates": [...],
            "close": [...],
        }
    or None on failure.
    """
    # Request a bit more than lookback to be safe
    timeseries = lookback_days + 5
    url = (
        f"https://financialmodelingprep.com/api/v3/historical-price-full/"
        f"{symbol}?timeseries={timeseries}&apikey={config.FMP_KEY}"
    )

    try:
        res = requests.get(url, timeout=5).json()
        if "historical" not in res or not res["historical"]:
            return None

        # Sort by date ascending just in case
        hist = sorted(res["historical"], key=lambda x: x.get("date", ""))

        dates = [row.get("date") for row in hist]
        closes = [row.get("close") for row in hist]

        # Basic sanity
        if len(closes) < (lookback_days + 1):
            return None

        return {"dates": dates, "close": closes}

    except Exception as e:
        log_strategy_error(symbol, "rs_engine_fetch_candles", e)
        return None


def _compute_return(closes, lookback_days: int) -> Optional[float]:
    """
    Compute simple return over lookback_days:
        (P_today / P_lookback - 1)
    """
    try:
        p_today = closes[-1]
        p_past = closes[-(lookback_days + 1)]
        if p_today is None or p_past is None or p_past == 0:
            return None
        return (p_today / p_past) - 1.0
    except Exception:
        return None


def get_rs_metrics(symbol: str, lookback_days: int = LOOKBACK_DAYS_DEFAULT) -> Dict[str, Any]:
    """
    (Legacy functional API — preserved for backward compatibility.)

    Compute RS metrics for a symbol vs SPY.

    RS_raw = stock_return - SPY_return over lookback_days.

    Returns:
        {
            "rs_raw": float or None,
            "rs_lookback_days": int,
        }
    """
    try:
        stock_data = _fetch_candles(symbol, lookback_days)
        spy_data = _fetch_candles("SPY", lookback_days)

        if not stock_data or not spy_data:
            return {"rs_raw": None, "rs_lookback_days": lookback_days}

        stock_ret = _compute_return(stock_data["close"], lookback_days)
        spy_ret = _compute_return(spy_data["close"], lookback_days)

        if stock_ret is None or spy_ret is None:
            return {"rs_raw": None, "rs_lookback_days": lookback_days}

        rs_raw = stock_ret - spy_ret
        return {"rs_raw": rs_raw, "rs_lookback_days": lookback_days}

    except Exception as e:
        log_strategy_error(symbol, "rs_engine_compute", e)
        return {"rs_raw": None, "rs_lookback_days": lookback_days}


# ==============================================================================
# Class-based engine (v2.0.0)
# ==============================================================================

class RSEngine:
    """
    Class-based RS v1 engine.

    Keeps RS v1 "pure":
        - Computes RS_raw = stock_return - SPY_return over a fixed lookback.
        - No cross-sectional ranking.
        - No percentiles.
        - No CSV output or batch mode.

    Intended Stage 2 / adapter-facing API:

        engine = RSEngine()
        engine.get_rs("NVDA") -> {
            "symbol": "NVDA",
            "rs_value": float | None,   # rs_raw
            "rs_rank": None,
            "raw": {
                "rs_raw": float | None,
                "rs_lookback_days": int,
            }
        }
    """

    def __init__(
        self,
        lookback_days: int = LOOKBACK_DAYS_DEFAULT,
        logger: Optional[Any] = None,
    ) -> None:
        self.lookback_days = lookback_days
        self.logger = logger

    def _log_info(self, msg: str) -> None:
        if self.logger:
            self.logger.info(msg)

    def _log_error(self, msg: str) -> None:
        if self.logger:
            self.logger.error(msg)

    def get_rs(self, symbol: str) -> Dict[str, Any]:
        """
        Compute RS v1 for a single symbol vs SPY.

        Returns:
            {
                "symbol": str,
                "rs_value": float | None,   # rs_raw
                "rs_rank": None,            # v1 does not define rank/percentile
                "raw": {
                    "rs_raw": float | None,
                    "rs_lookback_days": int,
                }
            }
        """
        try:
            self._log_info(f"[RS v1] Computing RS for {symbol} over {self.lookback_days} days")

            metrics = get_rs_metrics(symbol, lookback_days=self.lookback_days)
            rs_raw = metrics.get("rs_raw")
            lookback = metrics.get("rs_lookback_days", self.lookback_days)

            raw = {
                "rs_raw": rs_raw,
                "rs_lookback_days": lookback,
            }

            return {
                "symbol": symbol,
                "rs_value": rs_raw,
                "rs_rank": None,  # RS v1 is not percentile-based
                "raw": raw,
            }

        except Exception as e:
            log_strategy_error(symbol, "rs_engine_get_rs", e)
            self._log_error(f"[RS v1] Error computing RS for {symbol}: {e}")
            return {
                "symbol": symbol,
                "rs_value": None,
                "rs_rank": None,
                "raw": {
                    "rs_raw": None,
                    "rs_lookback_days": self.lookback_days,
                },
            }