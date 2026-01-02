"""
Project: Daily Trend Scanner (The "Governor" Update)
Filename: core/scan_trend_daily.py
Version: 5.1.0
Author: Copilot & Clay
Date: 2025-12-18

Changelog (high level):
- v5.1.0: Added unified daily candle provider with Alpaca fallback.
          DailyTrendScanner and analyze_stock now use get_daily_candles()
          instead of FMP-only get_fmp_candles().
- v5.0.0: Added DailyTrendScanner class with symbol-level get_daily_trend() API for Stage 2/adapters.
- v4.3.0: Replaced Strategy Engine v1 with Strategy Engine v2 (unified scoring, conviction levels)
- v4.2.0: Integrated WorkerController for adaptive, scanner-aware worker governance
- v4.1.0: Integrated with Strategy Engine, RS Engine, Risk Engine, and Strategy Logger
- v4.0.0: Renamed from real_time_scanner.py to scan_trend_daily.py
- v3.9.6: PATH FIX
- v3.9.5: API RATE LIMITER

Design v5.0.0:
- Retains original batch scanner behavior when run as a script (__main__).
- Introduces DailyTrendScanner, a class-based, symbol-level engine:

    daily = DailyTrendScanner()
    daily.get_daily_trend("NVDA") -> {
        "daily_trend": str | None,          # e.g., "PERFECT", "COILING", "SURFING", "TRENDING"
        "daily_trend_score": float | None,  # strategy.score
        "daily_trend_raw": dict | None,     # full per-symbol detail
    }

- Reuses core logic from analyze_stock but strips charting / threading / batch concerns
  for the symbol-level API.
"""

import matplotlib
matplotlib.use("Agg")

import pandas as pd
import requests
import time
import os
import sys
import mplfinance as mpf
import shutil
import threading
import concurrent.futures
from datetime import datetime
from typing import Optional, Dict, Any

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- MODULE IMPORTS ---
import config
import utils
from core.strategy_engine_v2 import StrategyEngineV2, StrategyContext
from core.strategy_error_logger import log_strategy_error
from core.worker_controller import WorkerController
from core.catalyst_engine import CatalystEngine, CatalystContext

# ----------------------------------------------------------------------
# Alpaca configuration (expects keys in config.py)
# ----------------------------------------------------------------------
ALPACA_BASE_URL = "https://data.alpaca.markets"
ALPACA_KEY = getattr(config, "ALPACA_KEY", None)
ALPACA_SECRET = getattr(config, "ALPACA_SECRET", None)

CATALYST_ENGINE = CatalystEngine()
STRATEGY_ENGINE_V2 = StrategyEngineV2()

pd.set_option("future.no_silent_downcasting", True)

# ==============================================================================
# CONFIGURATION
# ==============================================================================
BLACKLIST_SECTORS = ["Aerospace & Defense", "Tobacco"]
BLACKLIST_TICKERS = ["PLBY"]

MIN_MARKET_CAP = 200_000_000
MIN_FLOAT = 20_000_000
MIN_DOLLAR_VOL = 25_000_000
MIN_PRICE = 5.00

MAX_WORKERS_HARD_CAP = config.WORKER_HARD_CAPS["TREND_DAILY"]
API_DELAY = 0.9

PLOT_LOCK = threading.Lock()
API_LOCK = threading.Lock()
API_CALL_COUNT = 0

TREND_RESULTS_FILE = os.path.join(config.DATA_DIR, "trend_results.csv")

# Global controller instance
CONTROLLER: WorkerController | None = None


# ==============================================================================
# 0. UTILS
# ==============================================================================

# ======================================================================
# UNIFIED GLOBAL API WRAPPER (REPLACES _record_api + fixes all counting)
# ======================================================================

API_LOCK = threading.Lock()
API_CALL_COUNT = 0   # global counter used by CLI display

def record_api(latency_sec: float, status_code: int):
    """Record API call in BOTH global counter and WorkerController."""
    global API_CALL_COUNT, CONTROLLER

    # Global counter (used for CLI API/min display)
    with API_LOCK:
        API_CALL_COUNT += 1

    # WorkerController counter (used for Calls/min)
    if CONTROLLER is not None:
        CONTROLLER.record_api_call(latency_sec=latency_sec, status_code=status_code)


def rate_limited_get(*args, **kwargs):
    """
    Wraps requests.get() with:
    - global rate limiting
    - unified API counting
    - exception-safe behavior
    """
    global CONTROLLER

    # 1. GLOBAL RATE LIMIT GATE
    if CONTROLLER is not None:
        while CONTROLLER._rate_window.count_last_window() >= CONTROLLER.max_calls_per_min:
            time.sleep(0.05)

    # 2. EXECUTE REQUEST
    start = time.time()
    status = 0

    try:
        res = requests.get(*args, **kwargs)
        status = res.status_code
        return res

    except Exception:
        status = 0
        return None

    finally:
        # 3. UNIFIED API RECORDING
        record_api(time.time() - start, status)

def safe_save_csv(df, filepath):
    temp_file = filepath + ".tmp"
try:
        df.to_csv(temp_file, index=False)
        shutil.move(temp_file, filepath)
    except Exception:
        pass


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


# ==============================================================================
# 1. DATA SOURCE
# ==============================================================================
def get_candidates():
    if config.FMP_KEY:
        print(f"[TIME] {datetime.now().strftime('%H:%M:%S')} - Connecting to FMP Screener...")
        url = (
            f"https://financialmodelingprep.com/api/v3/stock-screener"
            f"?marketCapMoreThan={MIN_MARKET_CAP}&priceMoreThan={MIN_PRICE}"
            f"&volumeMoreThan=500000&isEtf=false&exchange=NASDAQ,NYSE,AMEX"
            f"&limit=3000&apikey={config.FMP_KEY}"
        )

        try:
            # Unified rate-limited request wrapper
            res_obj = rate_limited_get(url, timeout=10)
            if res_obj is None:
                raise RuntimeError("FMP screener request failed")

            res = res_obj.json()
            candidates = []

            for item in res:
                candidates.append(
                    {
                        "symbol": item.get("symbol", "").replace(".", "-"),
                        "sector": item.get("sector", "Unknown"),
                        "industry": item.get("industry", "Unknown"),
                    }
                )

            print(f"[OK] FMP Identified {len(candidates)} candidates.")
            return candidates

        except Exception as e:
            print(f"[WARN] FMP Connection failed: {e}")

    # Fallback when FMP fails or no key
    return [{"symbol": s, "sector": "Unknown", "industry": "Unknown"} for s in ["NVDA", "TSLA"]]

def get_fmp_candles(symbol):
    if not config.FMP_KEY:
        return None

    url = (
        f"https://financialmodelingprep.com/api/v3/historical-price-full/"
        f"{symbol}?timeseries=100&apikey={config.FMP_KEY}"
    )

    try:
        # Unified rate-limited request wrapper
        res_obj = rate_limited_get(url, timeout=5)
        if res_obj is None:
            return None

        res = res_obj.json()

        if "historical" not in res:
            return None

        data = res["historical"]
        if not data:
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
        return None


def get_alpaca_daily_candles(symbol: str) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLC from Alpaca as a fallback when FMP is empty.
    Normalizes output to match get_fmp_candles().
    """
    if not ALPACA_KEY or not ALPACA_SECRET:
        return None

    url = (
        f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars"
        f"?timeframe=1Day&limit=100&adjustment=raw"
    )

    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }

    try:
        # Unified rate-limited request wrapper
        res_obj = rate_limited_get(url, headers=headers, timeout=5)
        if res_obj is None:
            return None

        res = res_obj.json()
        bars = res.get("bars") or []
        if not bars:
            return None

        df = pd.DataFrame(bars)
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
        return None


def get_daily_candles(symbol: str) -> Optional[pd.DataFrame]:
    """
    Unified daily OHLC provider:
    1) Try FMP first (legacy behavior)
    2) Fallback to Alpaca daily bars
    """
    # --- Primary: FMP ---
    df = get_fmp_candles(symbol)
    if df is not None and len(df) >= 50:
        return df

    # --- Fallback: Alpaca ---
    df = get_alpaca_daily_candles(symbol)
    if df is not None and len(df) >= 50:
        return df

    return None


def get_fmp_quote(symbol):
    if not config.FMP_KEY:
        return None

    url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={config.FMP_KEY}"

    try:
        # Unified rate-limited request wrapper
        res_obj = rate_limited_get(url, timeout=5)
        if res_obj is None:
            return None

        res = res_obj.json()

        if res and isinstance(res, list):
            return res[0]

    except Exception:
        return None

    return None


def get_benchmark():
    print(f"\n[TIME] {datetime.now().strftime('%H:%M:%S')} - Downloading Benchmark (SPY) via FMP...")
    df = get_fmp_candles("SPY")
    return df if df is not None else pd.DataFrame()


# ==============================================================================
# 2. LOGIC ENGINE – original batch-style analyze_stock
# ==============================================================================
def analyze_stock(candidate, spy_data):
    time.sleep(API_DELAY)

    if not isinstance(candidate, dict):
        return None
    if check_blacklist(candidate):
        return None

    symbol = candidate["symbol"]
    df = get_daily_candles(symbol)

    if df is None or len(df) < 50:
        return None

    try:
        close = df["Close"]
        ema10 = close.ewm(span=10, adjust=False).mean()
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()

        daily_range_pct = (df["High"] - df["Low"]) / df["Low"]
        adr = daily_range_pct.rolling(20).mean() * 100
        dollar_vol = close.iloc[-1] * df["Volume"].iloc[-1]

        # --- RS Calculation ---
        if not spy_data.empty:
            spy_aligned = spy_data.reindex(df.index).ffill()
            rs_score = (
                close.pct_change(50, fill_method=None)
                - spy_aligned["Close"].pct_change(50, fill_method=None)
            )
        else:
            rs_score = pd.Series(0, index=df.index)

        p = close.iloc[-1]

        # --- Core Trend Daily Filters ---
        stack_ok = p > ema10.iloc[-1] > sma20.iloc[-1] > sma50.iloc[-1]
        adr_ok = adr.iloc[-1] > 4.0
        liq_ok = dollar_vol > MIN_DOLLAR_VOL

        if not (stack_ok and adr_ok and liq_ok):
            return None

        quote = get_fmp_quote(symbol)
        if not quote:
            return None

        shares_out = quote.get("sharesOutstanding", 0)
        if shares_out < MIN_FLOAT:
            return None

        vol_tight = daily_range_pct.iloc[-5:].mean() * 100 < (adr.iloc[-1] * 0.75)
        surfing = abs(p - ema10.iloc[-1]) / ema10.iloc[-1] < 0.04

        grade = "TRENDING"
        if vol_tight and surfing:
            grade = "PERFECT"
        elif vol_tight:
            grade = "COILING"
        elif surfing:
            grade = "SURFING"

        pivot = df["High"].iloc[-20:].max()
        stop = sma20.iloc[-1]

        # ======================================================================
        # Catalyst Engine v2 Integration
        # ======================================================================
        today_vol = df["Volume"].iloc[-1] / df["Volume"].iloc[-51:-1].mean()
        ctx_catalyst = CatalystContext(
            symbol=symbol,
            rvol=today_vol,
            rs_rank=rs_score.iloc[-1] * 100,
        )

        catalyst = CATALYST_ENGINE.score(ctx_catalyst)

        # ======================================================================
        # Strategy Engine v2 Integration
        # ======================================================================
        ctx_strategy = StrategyContext(
            symbol=symbol,
            scanner="TREND",
            catalyst_score=catalyst.score,
            rs_rank=rs_score.iloc[-1] * 100,
            rvol=today_vol,
            trend_label=grade,
            move_pct=None,
            pullback_pct=None,
            gap_pct=None,
            float_m=shares_out / 1_000_000,
            dollar_vol_m=dollar_vol / 1_000_000,
        )

        strategy = STRATEGY_ENGINE_V2.score(ctx_strategy, catalyst.tags)

        # ======================================================================
        # Chart Generation
        # ======================================================================
        with PLOT_LOCK:
            save_path = os.path.join(config.CHART_DIR_KK, f"{symbol}.png")
            title = (
                f"[{grade}] {symbol} ({candidate.get('industry')[:15]})\n"
                f"Shares: {shares_out/1_000_000:.1f}M | ADR: {adr.iloc[-1]:.1f}%\n"
                f"Catalyst: {catalyst.strength} ({catalyst.score}) | "
                f"Score: {strategy.score} ({strategy.conviction})"
            )
            ap = [
                mpf.make_addplot(ema10, color="blue", width=1.5),
                mpf.make_addplot(sma50, color="red", width=1.5),
            ]
            mpf.plot(
                df,
                type="candle",
                style="yahoo",
                title=title,
                addplot=ap,
                volume=False,
                savefig=save_path,
            )
            matplotlib.pyplot.close("all")

        # ======================================================================
        # Return Result Row
        # ======================================================================
        return {
            "Symbol": symbol,
            "Grade": grade,
            "Price": round(p, 2),
            "ADR%": round(adr.iloc[-1], 2),
            "RS_Score": round(rs_score.iloc[-1] * 100, 2),
            "Vol_M": round(dollar_vol / 1_000_000, 1),
            "Float_M": round(shares_out / 1_000_000, 1),
            "Sector": candidate.get("sector", "Unknown"),
            "Industry": candidate.get("industry", "Unknown"),
            "Pivot": round(pivot, 2),
            "Stop_Loss": round(stop, 2),
            "Reason": "Tight & Surfing" if grade == "PERFECT" else "Uptrend",
            # Catalyst Engine v2 fields
            "CatalystScore": catalyst.score,
            "CatalystTags": ",".join(catalyst.tags),
            "CatalystStrength": catalyst.strength,
            # Strategy Engine v2 fields
            "StratScore": strategy.score,
            "StratConviction": strategy.conviction,
        }

    except Exception:
        return None


# ==============================================================================
# 2b. CLASS-BASED SYMBOL-LEVEL ENGINE (v5.0.0)
# ==============================================================================
class DailyTrendScanner:
    """
    Class-based Daily Trend scanner.

    Intended adapter-facing API:

        daily = DailyTrendScanner()
        daily.get_daily_trend("NVDA") -> {
            "daily_trend": str | None,          # "PERFECT", "COILING", "SURFING", "TRENDING"
            "daily_trend_score": float | None,  # strategy.score
            "daily_trend_raw": dict | None,     # full raw details
        }

    Symbol-level only:
        - No WorkerController
        - No batch screener
        - No chart generation
    """

    def __init__(self, logger: Optional[Any] = None, spy_data: Optional[pd.DataFrame] = None) -> None:
        self.logger = logger
        # Optionally allow caller to pass pre-fetched SPY data;
        # if not provided, we fetch on demand once.
        self.spy_data = spy_data if spy_data is not None else get_benchmark()

    def _log_info(self, msg: str) -> None:
        if self.logger:
            self.logger.info(msg)

    def _log_error(self, msg: str) -> None:
        if self.logger:
            self.logger.error(msg)

    def get_daily_trend(
        self,
        symbol: str,
        sector: str = "Unknown",
        industry: str = "Unknown",
    ) -> Dict[str, Any]:
        """
        Symbol-level daily trend evaluation.

        Returns:
            {
                "daily_trend": str | None,
                "daily_trend_score": float | None,
                "daily_trend_raw": dict | None,
            }
        """
        try:
            self._log_info(f"[TREND_DAILY] Evaluating daily trend for {symbol}")

            candidate = {
                "symbol": symbol,
                "sector": sector,
                "industry": industry,
            }

            if check_blacklist(candidate):
                return {
                    "daily_trend": None,
                    "daily_trend_score": None,
                    "daily_trend_raw": None,
                }

            df = get_daily_candles(symbol)
            if df is None or len(df) < 50:
                return {
                    "daily_trend": None,
                    "daily_trend_score": None,
                    "daily_trend_raw": None,
                }

            close = df["Close"]
            ema10 = close.ewm(span=10, adjust=False).mean()
            sma20 = close.rolling(20).mean()
            sma50 = close.rolling(50).mean()

            daily_range_pct = (df["High"] - df["Low"]) / df["Low"]
            adr = daily_range_pct.rolling(20).mean() * 100
            dollar_vol = close.iloc[-1] * df["Volume"].iloc[-1]

            # RS vs SPY
            spy_data = self.spy_data if self.spy_data is not None else pd.DataFrame()
            if not spy_data.empty:
                spy_aligned = spy_data.reindex(df.index).ffill()
                rs_score = (
                    close.pct_change(50, fill_method=None)
                    - spy_aligned["Close"].pct_change(50, fill_method=None)
                )
            else:
                rs_score = pd.Series(0, index=df.index)

            p = close.iloc[-1]

            # Trend filters
            stack_ok = p > ema10.iloc[-1] > sma20.iloc[-1] > sma50.iloc[-1]
            adr_ok = adr.iloc[-1] > 4.0
            liq_ok = dollar_vol > MIN_DOLLAR_VOL

            if not (stack_ok and adr_ok and liq_ok):
                return {
                    "daily_trend": None,
                    "daily_trend_score": None,
                    "daily_trend_raw": None,
                }

            quote = get_fmp_quote(symbol)
            if not quote:
                return {
                    "daily_trend": None,
                    "daily_trend_score": None,
                    "daily_trend_raw": None,
                }

            shares_out = quote.get("sharesOutstanding", 0)
            if shares_out < MIN_FLOAT:
                return {
                    "daily_trend": None,
                    "daily_trend_score": None,
                    "daily_trend_raw": None,
                }

            vol_tight = daily_range_pct.iloc[-5:].mean() * 100 < (adr.iloc[-1] * 0.75)
            surfing = abs(p - ema10.iloc[-1]) / ema10.iloc[-1] < 0.04

            grade = "TRENDING"
            if vol_tight and surfing:
                grade = "PERFECT"
            elif vol_tight:
                grade = "COILING"
            elif surfing:
                grade = "SURFING"

            pivot = df["High"].iloc[-20:].max()
            stop = sma20.iloc[-1]

            today_vol = df["Volume"].iloc[-1] / df["Volume"].iloc[-51:-1].mean()

            # Catalyst
            ctx_catalyst = CatalystContext(
                symbol=symbol,
                rvol=today_vol,
                rs_rank=rs_score.iloc[-1] * 100,
            )
            catalyst = CATALYST_ENGINE.score(ctx_catalyst)

            # Strategy
            ctx_strategy = StrategyContext(
                symbol=symbol,
                scanner="TREND",
                catalyst_score=catalyst.score,
                rs_rank=rs_score.iloc[-1] * 100,
                rvol=today_vol,
                trend_label=grade,
                move_pct=None,
                pullback_pct=None,
                gap_pct=None,
                float_m=shares_out / 1_000_000,
                dollar_vol_m=dollar_vol / 1_000_000,
            )
            strategy = STRATEGY_ENGINE_V2.score(ctx_strategy, catalyst.tags)

            self._log_info(
                f"[TREND_DAILY] {symbol}: grade={grade}, "
                f"score={strategy.score}, conviction={strategy.conviction}"
            )

            raw = {
                "symbol": symbol,
                "sector": sector,
                "industry": industry,
                "grade": grade,
                "price": float(p),
                "adr_pct": float(adr.iloc[-1]),
                "rs_score": float(rs_score.iloc[-1] * 100),
                "dollar_vol": float(dollar_vol),
                "float_m": float(shares_out / 1_000_000),
                "pivot": float(pivot),
                "stop_loss": float(stop),
                "vol_tight": bool(vol_tight),
                "surfing": bool(surfing),
                "catalyst_score": catalyst.score,
                "catalyst_strength": catalyst.strength,
                "catalyst_tags": catalyst.tags,
                "strategy_score": strategy.score,
                "strategy_conviction": strategy.conviction,
                "strategy_components": strategy.components,
            }

            daily_trend_score = float(strategy.score) if strategy.score is not None else None
            daily_trend_label = grade if daily_trend_score is not None else None

            return {
                "daily_trend": daily_trend_label,
                "daily_trend_score": daily_trend_score,
                "daily_trend_raw": raw,
            }

        except Exception as e:
            log_strategy_error(symbol, "trend_daily_get_daily_trend", e)
            self._log_error(f"[TREND_DAILY] Error evaluating trend for {symbol}: {e}")
            return {
                "daily_trend": None,
                "daily_trend_score": None,
                "daily_trend_raw": None,
            }


# ==============================================================================
# 3. EXECUTION – batch CLI mode (preserved)
# ==============================================================================
if __name__ == "__main__":
    script_start_time = datetime.now()
    utils.print_metadata(os.path.basename(__file__), "5.1.0")
    print(f"[TIME] Script Start: {script_start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    utils.clean_folder(config.CHART_DIR_KK)

    # Initialize adaptive worker controller
    CONTROLLER = WorkerController(scanner_name="TREND_DAILY", max_calls_per_min=300)

    candidates = get_candidates()
    spy = get_benchmark()

    matches = []
    print(f"\n[TIME] {datetime.now().strftime('%H:%M:%S')} - Scanning {len(candidates)} candidates...")

    governed_workers = CONTROLLER.get_worker_count()
    governed_workers = max(2, min(governed_workers, MAX_WORKERS_HARD_CAP))

    print(f"[INFO] Launching {governed_workers} Worker Threads (GOVERNED MODE).")

    analysis_start = time.time()
    processed_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=governed_workers) as executor:
        future_to_candidate = {
            executor.submit(analyze_stock, cand, spy): cand for cand in candidates
        }

        for future in concurrent.futures.as_completed(future_to_candidate):
            processed_count += 1
            try:
                res = future.result()
                if res:
                    matches.append(res)
            except Exception:
                pass

            if processed_count % 5 == 0:
                elapsed = time.time() - analysis_start
                if elapsed > 0:
                    rate = processed_count / elapsed
                    with API_LOCK:
                        api_rate = (API_CALL_COUNT / elapsed) * 60
                else:
                    rate = 0
                    api_rate = 0

                print(
                    f"\rScanning {processed_count}/{len(candidates)} | "
                    f"Found: {len(matches)} | Rate: {rate:.1f}/s | API: {api_rate:.0f}/min",
                    end="",
                )

            if processed_count % 50 == 0 and CONTROLLER is not None:
                snap = CONTROLLER.debug_snapshot()
                print(
                    f"\n[WORKERS] Lat={snap['rolling_latency']}s | "
                    f"Calls={snap['calls_last_min']}/{snap['max_calls_per_min']} | "
                    f"Err={snap['error_count_window']} | "
                    f"Recommended={snap['recommended_workers']}"
                )

    print("\n\n" + "=" * 50)
    print(f"[DONE] SCAN COMPLETE. Found {len(matches)} Candidates.")

    # Save results
    if matches:
        df_res = pd.DataFrame(matches)
        df_res = df_res.sort_values(by="StratScore", ascending=False)
        safe_save_csv(df_res, TREND_RESULTS_FILE)

        print(f"[SUCCESS] Saved {len(matches)} Trend Daily results to {TREND_RESULTS_FILE}")
    else:
        print("[WARN] No matches found.")

    script_end_time = datetime.now()
    duration = script_end_time - script_start_time
    print(f"\n[TIME] Script Finished: {script_end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[TIME] Total Execution Duration: {duration}")