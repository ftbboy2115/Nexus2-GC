# core/scan_ep.py

"""
Project: Episodic Pivot Scanner (Smart-Batching Edition)
Filename: core/scan_ep.py
Version: 4.2.0
Author: Copilot, Gemini (Assistant) & Clay
Date: 2025-12-18

Changelog (high level):
- v4.2.0: Upgraded EP logic to intraday+daily hybrid:
          * Daily history (yesterday close, RVOL denominator) via FMP daily
            with Alpaca daily fallback.
          * Today’s gap, RVOL numerator, dollar volume, and range quality
            computed from Alpaca intraday (1-minute, extended-hours-aware).
          * process_stock() and EPScanner.get_episodic_pivot() now use a
            unified EP session snapshot instead of FMP daily-only candles.
- v4.0.0: Added EPScanner class with symbol-level get_episodic_pivot() API for use by adapters / Stage 2.
- v3.3.0: Replaced Strategy Engine v1 with Strategy Engine v2 (unified scoring, conviction levels)
- v3.2.0: Integrated WorkerController for adaptive worker governance
- v3.1.0: Integrated WorkerController for adaptive worker governance
- v3.0.0: Renamed from scan_episodic_pivots to scan_ep
- v2.3.1: Strategy Engine integration
- v2.3.0: API efficiency overhaul (batch quote filter)
- v2.2.4: Funnel architecture integration

Design v4.2.0:
- Retains the original batch scanner behavior when run as a script (__main__).
- EPScanner remains the class-based engine with:

    ep = EPScanner()
    ep.get_episodic_pivot("NVDA") -> {
        "ep_pivot_score": float | None,
        "ep_pivot_label": str | None,
        "ep_pivot_trigger": str | None,
        "raw": dict | None,
    }

- EPScanner and process_stock now share a unified EP session snapshot:
    - Daily history (yesterday, historical volume) from FMP daily
      with Alpaca daily fallback.
    - Today’s session (gap, RVOL numerator, dollar vol, range quality)
      from Alpaca intraday (1-minute, extended-hours-aware).
"""

import matplotlib
matplotlib.use("Agg")

import pandas as pd
import requests
import time
import os
# import sys
import threading
import concurrent.futures
# import shutil
import mplfinance as mpf
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

# --- MODULE IMPORTS ---
import config
import utils
from core.strategy_engine_v2 import StrategyEngineV2, StrategyContext
from core.worker_controller import WorkerController
from core.catalyst_engine import CatalystEngine, CatalystContext

pd.set_option("future.no_silent_downcasting", True)

# --- CONFIGURATION ---
SCRIPT_NAME = os.path.basename(__file__)
SCRIPT_VERSION = "4.2.0"
DEBUG_MODE = False

# FILES & PATHS
CHART_DIR = config.CHART_DIR_EP
RESULTS_FILE = os.path.join(config.DATA_DIR, "ep_results.csv")

# BLACKLIST CONFIG
BLACKLIST_SECTORS = ["Aerospace & Defense", "Tobacco"]
BLACKLIST_TICKERS = ["PLBY"]

#######################################################################
# STRATEGY SETTINGS
MIN_CHANGE_PCT_FILTER = 3.0
MIN_GAP_PCT = 0.08
MIN_RVOL = 2.0
MIN_DOLLAR_VOL = 10_000_000
#######################################################################

# ENGINE SETTINGS
API_DELAY = 0.8  # soft pacing delay inside process_stock

# TELEMETRY
API_LOCK = threading.Lock()
PLOT_LOCK = threading.Lock()
DEBUG_LOCK = threading.Lock()
API_CALL_COUNT = 0
DEBUG_PRINT_COUNT = 0

# Global WorkerController instance (for CLI batch mode)
CONTROLLER: WorkerController | None = None

# Engines
CATALYST_ENGINE = CatalystEngine()
STRATEGY_ENGINE_V2 = StrategyEngineV2()

# ----------------------------------------------------------------------
# Alpaca configuration (expects keys in config.py)
# ----------------------------------------------------------------------
ALPACA_BASE_URL = getattr(config, "ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")
ALPACA_KEY = getattr(config, "ALPACA_KEY", None)
ALPACA_SECRET = getattr(config, "ALPACA_SECRET", None)


# ==============================================================================
# 0. UTILS
# ==============================================================================
def check_blacklist(candidate):
    symbol = candidate.get("symbol", "").upper()
    sector = candidate.get("sector", "Unknown")
    industry = candidate.get("industry", "Unknown")

    if symbol in BLACKLIST_TICKERS:
        return True
    for banned in BLACKLIST_SECTORS:
        if banned in sector or banned in industry:
            return True
    return False


def debug_log(msg):
    global DEBUG_PRINT_COUNT
    if not DEBUG_MODE:
        return
    with DEBUG_LOCK:
        if DEBUG_PRINT_COUNT < 10:
            print(f"\n[DEBUG] {msg}")
            DEBUG_PRINT_COUNT += 1


def _record_api(latency_start: float, status_code: int) -> None:
    """
    Helper to update global API_CALL_COUNT and WorkerController after an API call.
    """
    global API_CALL_COUNT, CONTROLLER

    latency = time.time() - latency_start
    with API_LOCK:
        API_CALL_COUNT += 1

    if CONTROLLER is not None:
        CONTROLLER.record_api_call(latency_sec=latency, status_code=status_code)


# ==============================================================================
# 1. DATA SOURCE (Two-Step Filter, reused by CLI batch mode)
#   - FMP Screener and batch quotes remain unchanged.
#   - EP signal data (gap/RVOL/dollar_vol/range) now comes from
#     EP session snapshot (daily + Alpaca intraday).
# ==============================================================================
def get_initial_candidates():
    if not config.FMP_KEY:
        print("[ERROR] FMP_API_KEY missing.")
        return []

    print(f"[TIME] {datetime.now().strftime('%H:%M:%S')} - Step 1: Broad Screen (Price > $4)...")

    url = (
        f"https://financialmodelingprep.com/api/v3/stock-screener"
        f"?marketCapMoreThan=50000000&priceMoreThan=4&volumeMoreThan=50000"
        f"&isEtf=false&exchange=NASDAQ,NYSE,AMEX&limit=2000&apikey={config.FMP_KEY}"
    )

    start = time.time()
    status = 0

    try:
        res_obj = requests.get(url, timeout=10)
        status = res_obj.status_code
        res = res_obj.json()
        _record_api(start, status)

        candidates = []
        for item in res:
            candidates.append(
                {
                    "symbol": item.get("symbol", "").replace(".", "-"),
                    "sector": item.get("sector", "Unknown"),
                    "industry": item.get("industry", "Unknown"),
                }
            )

        print(f"   found {len(candidates)} raw candidates.")
        return candidates

    except Exception as e:
        try:
            _record_api(start, status)
        except Exception:
            pass
        print(f"[WARN] FMP Screener failed: {e}")
        return []


def filter_by_batch_quote(candidates):
    if not candidates:
        return []

    print(
        f"[TIME] {datetime.now().strftime('%H:%M:%S')} - Step 2: Batch Filtering "
        f"(> {MIN_CHANGE_PCT_FILTER}% move)..."
    )

    valid_candidates = []
    chunk_size = 100

    cand_map = {c["symbol"]: c for c in candidates}
    all_symbols = list(cand_map.keys())

    for i in range(0, len(all_symbols), chunk_size):
        chunk = all_symbols[i : i + chunk_size]
        tickers_str = ",".join(chunk)

        url = f"https://financialmodelingprep.com/api/v3/quote/{tickers_str}?apikey={config.FMP_KEY}"

        start = time.time()
        status = 0

        try:
            res_obj = requests.get(url, timeout=5)
            status = res_obj.status_code
            res = res_obj.json()
            _record_api(start, status)

            for quote in res:
                sym = quote.get("symbol")
                pct_change = quote.get("changesPercentage", 0)

                if pct_change >= MIN_CHANGE_PCT_FILTER:
                    if sym in cand_map:
                        valid_candidates.append(cand_map[sym])

        except Exception as e:
            try:
                _record_api(start, status)
            except Exception:
                pass
            print(f"   [WARN] Batch {i} failed: {e}")

        time.sleep(0.1)
        print(
            f"\r   Processed {min(i + chunk_size, len(all_symbols))}/{len(all_symbols)} tickers...",
            end="",
        )

    print(f"\n   Reduced {len(candidates)} -> {len(valid_candidates)} Active Movers.")
    return valid_candidates


def get_fmp_candles(symbol):
    """
    Daily candles from FMP, used for:
    - Yesterday's close
    - Historical daily volume for RVOL denominator
    """
    if not config.FMP_KEY:
        return None

    url = (
        f"https://financialmodelingprep.com/api/v3/historical-price-full/"
        f"{symbol}?timeseries=60&apikey={config.FMP_KEY}"
    )

    start = time.time()
    status = 0

    try:
        res_obj = requests.get(url, timeout=5)
        status = res_obj.status_code
        res = res_obj.json()
        _record_api(start, status)

        if "historical" not in res:
            return None
        data = res["historical"]
        if len(data) < 50:
            return None

        df = pd.DataFrame(data)
        df = df.iloc[::-1].reset_index(drop=True)
        df = df.rename(
            columns={
                "date": "Date",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            }
        )
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
        return df

    except Exception:
        try:
            _record_api(start, status)
        except Exception:
            pass
        return None


def get_alpaca_daily_candles(symbol: str) -> Optional[pd.DataFrame]:
    """
    Daily OHLC from Alpaca as a fallback when FMP daily is unavailable.
    Schema normalized to match get_fmp_candles().
    """
    if not ALPACA_KEY or not ALPACA_SECRET:
        return None

    url = (
        f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars"
        f"?timeframe=1Day&limit=60&adjustment=raw"
    )

    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }

    start = time.time()
    status = 0

    try:
        res_obj = requests.get(url, headers=headers, timeout=5)
        status = res_obj.status_code
        res = res_obj.json()
        _record_api(start, status)

        bars = res.get("bars") or []
        if len(bars) < 50:
            return None

        df = pd.DataFrame(bars)
        # t is ISO8601 timestamp
        df["Date"] = pd.to_datetime(df["t"])
        df = df.rename(
            columns={
                "o": "Open",
                "h": "High",
                "l": "Low",
                "c": "Close",
                "v": "Volume",
            }
        )
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
        df = df.set_index("Date")
        df = df.sort_index()
        return df

    except Exception:
        try:
            _record_api(start, status)
        except Exception:
            pass
        return None


def get_ep_daily_history(symbol: str) -> Optional[pd.DataFrame]:
    """
    Unified daily history for EP:
    1) Try FMP daily (primary).
    2) Fallback to Alpaca daily.
    Requires at least 50 bars for RVOL calculation.
    """
    df = get_fmp_candles(symbol)
    if df is not None and len(df) >= 50:
        return df

    df = get_alpaca_daily_candles(symbol)
    if df is not None and len(df) >= 50:
        return df

    return None


def get_alpaca_intraday_1m(symbol: str) -> Optional[pd.DataFrame]:
    """
    Fetch today's 1-minute intraday bars from Alpaca, extended-hours-aware.
    We request recent bars and then filter to today's date server-side.
    """
    if not ALPACA_KEY or not ALPACA_SECRET:
        return None

    # Request enough recent bars to comfortably cover today's session.
    # We'll filter to today's date in pandas.
    url = (
        f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars"
        f"?timeframe=1Min&limit=1000&adjustment=raw"
    )

    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }

    start = time.time()
    status = 0

    try:
        res_obj = requests.get(url, headers=headers, timeout=5)
        status = res_obj.status_code
        res = res_obj.json()
        _record_api(start, status)

        bars = res.get("bars") or []
        if not bars:
            return None

        df = pd.DataFrame(bars)
        df["ts"] = pd.to_datetime(df["t"])
        df = df.rename(
            columns={
                "o": "Open",
                "h": "High",
                "l": "Low",
                "c": "Close",
                "v": "Volume",
            }
        )

        # Filter to today's date (UTC-based; for EP purposes this is sufficient).
        today_utc = datetime.now(timezone.utc).date()
        df = df[df["ts"].dt.date == today_utc]

        if df.empty:
            return None

        df = df.sort_values("ts").reset_index(drop=True)
        return df

    except Exception:
        try:
            _record_api(start, status)
        except Exception:
            pass
        return None


def build_ep_session_snapshot(
    symbol: str, rvol_lookback: int = 50
) -> Optional[Dict[str, Any]]:
    """
    Build a unified EP session snapshot combining:
      - Daily history (yesterday close, historical volume)
      - Today's intraday session from Alpaca (extended-hours-aware)

    Returns dict with:
        {
            "yesterday_close": float,
            "avg_daily_volume": float,
            "session_open": float,
            "session_high": float,
            "session_low": float,
            "last_price": float,
            "session_volume": float,
        }
    Or None if data is insufficient.
    """
    # Daily history for yesterday close + RVOL denominator
    daily = get_ep_daily_history(symbol)
    if daily is None or len(daily) < rvol_lookback + 1:
        debug_log(f"{symbol}: insufficient daily history for EP.")
        return None

    # Yesterday close
    yesterday_close = float(daily["Close"].iloc[-2])

    # Historical daily volumes for RVOL denominator
    hist_vol = daily["Volume"].iloc[-(rvol_lookback + 1) : -1]
    avg_daily_volume = float(hist_vol.mean()) if hist_vol.mean() > 0 else 0.0
    if avg_daily_volume <= 0:
        debug_log(f"{symbol}: avg_daily_volume <= 0.")
        return None

    # Today's intraday session from Alpaca
    intraday = get_alpaca_intraday_1m(symbol)
    if intraday is None or intraday.empty:
        debug_log(f"{symbol}: no intraday data from Alpaca.")
        return None

    session_open = float(intraday["Open"].iloc[0])
    session_high = float(intraday["High"].max())
    session_low = float(intraday["Low"].min())
    last_price = float(intraday["Close"].iloc[-1])
    session_volume = float(intraday["Volume"].sum())

    if session_volume <= 0:
        debug_log(f"{symbol}: session_volume <= 0.")
        return None

    return {
        "yesterday_close": yesterday_close,
        "avg_daily_volume": avg_daily_volume,
        "session_open": session_open,
        "session_high": session_high,
        "session_low": session_low,
        "last_price": last_price,
        "session_volume": session_volume,
    }


# ==============================================================================
# 2. LOGIC ENGINE (original batch-style process_stock)
#   - Now uses EP session snapshot (daily + Alpaca intraday) instead of
#     FMP daily-only candles.
# ==============================================================================
def process_stock(candidate):
    """
    Original batch-mode EP logic for a single candidate dict:
        { "symbol": str, "sector": str, "industry": str }

    Returns:
        dict with EP result fields (Symbol, Gap%, CatalystScore, etc.) or None.
    """
    symbol = candidate["symbol"]
    if check_blacklist(candidate):
        return None

    time.sleep(API_DELAY)

    snapshot = build_ep_session_snapshot(symbol)
    if snapshot is None:
        return None

    try:
        yesterday_close = snapshot["yesterday_close"]
        avg_daily_volume = snapshot["avg_daily_volume"]
        session_open = snapshot["session_open"]
        session_high = snapshot["session_high"]
        session_low = snapshot["session_low"]
        last_price = snapshot["last_price"]
        session_volume = snapshot["session_volume"]

        # --- Gap Check ---
        gap_pct = (session_open - yesterday_close) / yesterday_close
        if gap_pct < MIN_GAP_PCT:
            return None

        # --- RVOL Check ---
        rvol = session_volume / avg_daily_volume
        dollar_vol = last_price * session_volume

        if rvol < MIN_RVOL:
            return None
        if dollar_vol < MIN_DOLLAR_VOL:
            return None

        # --- Range Check ---
        range_len = session_high - session_low
        if range_len > 0 and (last_price - session_low) / range_len < 0.40:
            return None

        # ======================================================================
        # Catalyst Engine v2 Integration
        # ======================================================================
        ctx_catalyst = CatalystContext(
            symbol=symbol,
            gap_pct=gap_pct,
            rvol=rvol,
            # Future: earnings, guidance, FDA, etc.
        )

        catalyst = CATALYST_ENGINE.score(ctx_catalyst)

        if not catalyst.has_catalyst:
            return None

        # ======================================================================
        # Strategy Engine v2 Integration
        # ======================================================================
        ctx_strategy = StrategyContext(
            symbol=symbol,
            scanner="EP",
            catalyst_score=catalyst.score,
            rs_rank=None,              # EP doesn't compute RS
            rvol=rvol,
            trend_label=None,          # No trend grading in EP
            move_pct=None,             # HTF-only concept
            pullback_pct=None,         # HTF-only concept
            gap_pct=gap_pct,
            float_m=None,              # Can be wired later from quote
            dollar_vol_m=dollar_vol / 1_000_000,
        )

        strategy = STRATEGY_ENGINE_V2.score(ctx_strategy, catalyst.tags)
        print(
            f"[EP STRATEGY V2] {symbol}: score={strategy.score}, "
            f"conviction={strategy.conviction}, components={strategy.components}"
        )

        # ======================================================================
        # Chart Generation (batch mode only)
        # ======================================================================
        # For visualization, synthesize a "today" candle from intraday snapshot.
        with PLOT_LOCK:
            # Build a tiny DataFrame with synthetic today bar for plotting.
            today_idx = datetime.now()
            df_plot = pd.DataFrame(
                {
                    "Open": [session_open],
                    "High": [session_high],
                    "Low": [session_low],
                    "Close": [last_price],
                    "Volume": [session_volume],
                },
                index=[today_idx],
            )

            save_path = os.path.join(CHART_DIR, f"{symbol}_EP.png")
            title = (
                f"{symbol} EP\n"
                f"Gap: {gap_pct*100:.1f}% | RVOL: {rvol:.1f}x | "
                f"Catalyst: {catalyst.strength} ({catalyst.score}) | "
                f"Score: {strategy.score} ({strategy.conviction})"
            )
            mpf.plot(
                df_plot,
                type="candle",
                style="yahoo",
                title=title,
                volume=True,
                savefig=save_path,
            )
            matplotlib.pyplot.close("all")

        # ======================================================================
        # Return Result Row (batch-style schema)
        # ======================================================================
        return {
            "Symbol": symbol,
            "Gap%": round(gap_pct * 100, 2),
            "Reason": "Gap+News+RVOL",
            "CatalystScore": catalyst.score,
            "CatalystTags": ",".join(catalyst.tags),
            "CatalystStrength": catalyst.strength,
            "StratScore": strategy.score,
            "StratConviction": strategy.conviction,
        }

    except Exception:
        return None


# ==============================================================================
# 2b. CLASS-BASED SYMBOL-LEVEL ENGINE (v4.2.0)
# ==============================================================================
class EPScanner:
    """
    Class-based Episodic Pivot scanner for symbol-level use.

    Intended adapter-facing API:

        ep = EPScanner()
        ep.get_episodic_pivot("NVDA") -> {
            "ep_pivot_score": float | None,
            "ep_pivot_label": str | None,
            "ep_pivot_trigger": str | None,
            "raw": dict | None,
        }

    This reuses the core EP logic but:
        - Does NOT write charts.
        - Does NOT use WorkerController.
        - Does NOT run batch screens.
        - Uses EP session snapshot (daily + Alpaca intraday) to be
          extended-hours-aware and real-time capable.
    """

    def __init__(self, logger: Optional[Any] = None) -> None:
        self.logger = logger

    def _log_info(self, msg: str) -> None:
        if self.logger:
            self.logger.info(msg)

    def _log_error(self, msg: str) -> None:
        if self.logger:
            self.logger.error(msg)

    def get_episodic_pivot(self, symbol: str) -> Dict[str, Any]:
        """
        Symbol-level EP query.

        Returns:
            {
                "ep_pivot_score": float | None,
                "ep_pivot_label": str | None,
                "ep_pivot_trigger": str | None,
                "raw": dict | None,
            }
        """
        # Build a minimal candidate dict (sector/industry currently unused here)
        candidate = {
            "symbol": symbol,
            "sector": "Unknown",
            "industry": "Unknown",
        }

        if check_blacklist(candidate):
            return {
                "ep_pivot_score": None,
                "ep_pivot_label": None,
                "ep_pivot_trigger": None,
                "raw": None,
            }

        try:
            self._log_info(f"[EP] Evaluating episodic pivot for {symbol}")

            snapshot = build_ep_session_snapshot(symbol)
            if snapshot is None:
                return {
                    "ep_pivot_score": None,
                    "ep_pivot_label": None,
                    "ep_pivot_trigger": None,
                    "raw": None,
                }

            yesterday_close = snapshot["yesterday_close"]
            avg_daily_volume = snapshot["avg_daily_volume"]
            session_open = snapshot["session_open"]
            session_high = snapshot["session_high"]
            session_low = snapshot["session_low"]
            last_price = snapshot["last_price"]
            session_volume = snapshot["session_volume"]

            # Gap
            gap_pct = (session_open - yesterday_close) / yesterday_close
            if gap_pct < MIN_GAP_PCT:
                return {
                    "ep_pivot_score": None,
                    "ep_pivot_label": None,
                    "ep_pivot_trigger": None,
                    "raw": None,
                }

            # RVOL
            if avg_daily_volume <= 0:
                return {
                    "ep_pivot_score": None,
                    "ep_pivot_label": None,
                    "ep_pivot_trigger": None,
                    "raw": None,
                }

            rvol = session_volume / avg_daily_volume
            dollar_vol = last_price * session_volume

            if rvol < MIN_RVOL or dollar_vol < MIN_DOLLAR_VOL:
                return {
                    "ep_pivot_score": None,
                    "ep_pivot_label": None,
                    "ep_pivot_trigger": None,
                    "raw": None,
                }

            # Range quality
            range_len = session_high - session_low
            if range_len > 0 and (last_price - session_low) / range_len < 0.40:
                return {
                    "ep_pivot_score": None,
                    "ep_pivot_label": None,
                    "ep_pivot_trigger": None,
                    "raw": None,
                }

            # Catalyst integration
            ctx_catalyst = CatalystContext(
                symbol=symbol,
                gap_pct=gap_pct,
                rvol=rvol,
            )
            catalyst = CATALYST_ENGINE.score(ctx_catalyst)

            if not catalyst.has_catalyst:
                return {
                    "ep_pivot_score": None,
                    "ep_pivot_label": None,
                    "ep_pivot_trigger": None,
                    "raw": None,
                }

            # Strategy integration
            ctx_strategy = StrategyContext(
                symbol=symbol,
                scanner="EP",
                catalyst_score=catalyst.score,
                rs_rank=None,
                rvol=rvol,
                trend_label=None,
                move_pct=None,
                pullback_pct=None,
                gap_pct=gap_pct,
                float_m=None,
                dollar_vol_m=dollar_vol / 1_000_000,
            )
            strategy = STRATEGY_ENGINE_V2.score(ctx_strategy, catalyst.tags)

            self._log_info(
                f"[EP] {symbol}: score={strategy.score}, "
                f"conviction={strategy.conviction}, components={strategy.components}"
            )

            raw = {
                "symbol": symbol,
                "gap_pct": gap_pct,
                "rvol": rvol,
                "dollar_vol": dollar_vol,
                "yesterday_close": yesterday_close,
                "session_open": session_open,
                "session_high": session_high,
                "session_low": session_low,
                "last_price": last_price,
                "session_volume": session_volume,
                "avg_daily_volume": avg_daily_volume,
                "catalyst_score": catalyst.score,
                "catalyst_strength": catalyst.strength,
                "catalyst_tags": catalyst.tags,
                "strategy_score": strategy.score,
                "strategy_conviction": strategy.conviction,
                "strategy_components": strategy.components,
            }

            ep_pivot_score = float(strategy.score) if strategy.score is not None else None
            ep_pivot_label = strategy.conviction  # e.g., "High", "Medium", etc.
            ep_pivot_trigger = "Gap+News+RVOL"

            return {
                "ep_pivot_score": ep_pivot_score,
                "ep_pivot_label": ep_pivot_label,
                "ep_pivot_trigger": ep_pivot_trigger,
                "raw": raw,
            }

        except Exception as e:
            self._log_error(f"[EP] Error evaluating EP for {symbol}: {e}")
            return {
                "ep_pivot_score": None,
                "ep_pivot_label": None,
                "ep_pivot_trigger": None,
                "raw": None,
            }


# ==============================================================================
# 3. EXECUTION (batch CLI mode, preserved)
# ==============================================================================
if __name__ == "__main__":
    script_start_time = datetime.now()
    utils.print_metadata(SCRIPT_NAME, SCRIPT_VERSION)

    if not os.path.exists(CHART_DIR):
        os.makedirs(CHART_DIR)
    utils.clean_folder(CHART_DIR)

    # Initialize WorkerController for EP
    CONTROLLER = WorkerController(scanner_name="EP", max_calls_per_min=config.MAX_CALLS_PER_MIN)

    raw_list = get_initial_candidates()
    candidates = filter_by_batch_quote(raw_list)

    matches = []

    if candidates:
        print(
            f"\n[TIME] {datetime.now().strftime('%H:%M:%S')} - Deep Scanning "
            f"{len(candidates)} movers... (Min Gap: {MIN_GAP_PCT*100}%)"
        )

        # Determine governed worker count
        governed_workers = CONTROLLER.get_worker_count()
        governed_workers = max(2, min(governed_workers, config.WORKER_HARD_CAPS["EP"]))

        print(f"[INFO] Launching {governed_workers} Worker Threads (GOVERNED MODE).")

        analysis_start = time.time()
        processed_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=governed_workers) as executor:
            future_to_cand = {executor.submit(process_stock, c): c for c in candidates}

            for future in concurrent.futures.as_completed(future_to_cand):
                processed_count += 1
                try:
                    res = future.result()
                    if res:
                        matches.append(res)
                except Exception:
                    pass

                if processed_count % 5 == 0:
                    elapsed = time.time() - analysis_start
                    rate = processed_count / elapsed if elapsed > 0 else 0
                    print(
                        f"\rScanning {processed_count}/{len(candidates)} | "
                        f"Found: {len(matches)} | Rate: {rate:.1f}/s",
                        end="",
                    )

                # Periodic worker diagnostics
                if processed_count % 50 == 0:
                    snap = CONTROLLER.debug_snapshot()
                    print(
                        f"\n[WORKERS] Lat={snap['rolling_latency']}s | "
                        f"Calls={snap['calls_last_min']}/{snap['max_calls_per_min']} | "
                        f"Err={snap['error_count_window']} | "
                        f"Recommended={snap['recommended_workers']}"
                    )

    # SAVE RESULTS
    if matches:
        df_res = pd.DataFrame(matches)
        df_res = df_res.sort_values(by="Gap%", ascending=False)
        df_res.to_csv(RESULTS_FILE, index=False)

        print("\n\n" + "=" * 50)
        print(f"[SUCCESS] Saved {len(matches)} EP candidates to {RESULTS_FILE}")

    else:
        print("\n\n" + "=" * 50)
        print(f"[DONE] No EP setups found.")

    print(f"[TIME] Total Duration: {datetime.now() - script_start_time}")