"""
Project: High Tight Flag Scanner (Safe Mode)
Filename: core/scan_htf.py
Version: 3.0.0
Author: Copilot, Gemini (Assistant) & Clay
Date: 2025-12-18

Changelog:
- v3.0.0: Added HTFScanner class with symbol-level get_htf_trend() API for Stage 2/adapters.
- v2.3.0: Replaced Strategy Engine v1 with Strategy Engine v2 (unified scoring, conviction levels)
- v2.2.0: Integrated WorkerController for adaptive, scanner-aware worker governance.
- v2.1.0: Integrated with Strategy Engine, RS Engine, Risk Engine, and Strategy Logger.
- v2.0.0: Renamed file from scan_high_tight_flag to scan_htf
- v1.2.5: EMOJI REMOVAL. Replaced Unicode icons with text tags to prevent UnicodeEncodeError on Windows.
- v1.2.4: PATH FIX.

==============================================================================
HTF Scanner (High Timeframe Trend Leaders)
==============================================================================
"""

import matplotlib
matplotlib.use("Agg")  # Force non-GUI backend

import pandas as pd
import requests
import time
import os
import sys
import threading
import concurrent.futures
import shutil
import mplfinance as mpf
from datetime import datetime
from typing import Optional, Dict, Any

# --- PATH SETUP (CRITICAL FIX) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- MODULE IMPORTS ---
import config
import utils
from core.strategy_engine_v2 import StrategyEngineV2, StrategyContext
from core.worker_controller import WorkerController
from core.catalyst_engine import CatalystEngine, CatalystContext

CATALYST_ENGINE = CatalystEngine()
STRATEGY_ENGINE_V2 = StrategyEngineV2()

# Suppress Pandas FutureWarnings
pd.set_option("future.no_silent_downcasting", True)

# --- CONFIGURATION ---
SCRIPT_NAME = os.path.basename(__file__)
SCRIPT_VERSION = "3.0.0"

# FILES & PATHS
CHART_DIR = os.path.join(config.BASE_DIR, "charts_htf")
RESULTS_FILE = os.path.join(config.DATA_DIR, "htf_results.csv")

# BLACKLIST
BLACKLIST_SECTORS = ["Aerospace & Defense", "Tobacco"]
BLACKLIST_TICKERS = ["PLBY"]

# HTF PARAMETERS
MIN_MOVE_PCT = 0.90      # +90% Move (The "Pole")
MAX_PULLBACK = 0.25      # -25% Depth (The "Flag")
MIN_PRICE = 4.00
MIN_DOLLAR_VOL = 5_000_000
MIN_SHARE_VOL = 500000

# ENGINE SETTINGS
MAX_WORKERS_HARD_CAP = config.WORKER_HARD_CAPS["HTF"]
API_DELAY = 1.0          # soft pacing delay inside analyze_htf

# TELEMETRY
API_LOCK = threading.Lock()
PLOT_LOCK = threading.Lock()
API_CALL_COUNT = 0

# Global controller instance (initialized in __main__)
CONTROLLER: WorkerController | None = None


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
# 1. DATA SOURCE (Two-Step Filter) – used by batch CLI mode
# ==============================================================================
def get_liquid_universe():
    if not config.FMP_KEY:
        print("[ERROR] FMP_API_KEY missing.")
        return []

    print(
        f"[TIME] {datetime.now().strftime('%H:%M:%S')} - Step 1: Broad Screen "
        f"(Price > ${MIN_PRICE}, Vol > {MIN_SHARE_VOL/100}K)..."
    )
    url = (
        f"https://financialmodelingprep.com/api/v3/stock-screener"
        f"?priceMoreThan={MIN_PRICE}&volumeMoreThan={MIN_SHARE_VOL}"
        f"&isEtf=false&exchange=NASDAQ,NYSE,AMEX&limit=10000&apikey={config.FMP_KEY}"
    )
    start = time.time()
    status = 0

    try:
        res_obj = requests.get(url, timeout=15)
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
        print(f"   [INFO] Found {len(candidates)} raw candidates.")
        return candidates
    except Exception as e:
        try:
            _record_api(start, status)
        except Exception:
            pass
        print(f"[WARN] FMP Screener failed: {e}")
        return []


def filter_by_volatility(candidates):
    if not candidates:
        return []

    print(
        f"[TIME] {datetime.now().strftime('%H:%M:%S')} - Step 2: Batch Volatility Check "
        f"(> 90% Range)..."
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
                year_high = quote.get("yearHigh")
                year_low = quote.get("yearLow")
                price = quote.get("price")

                if year_high is None or year_low is None or price is None:
                    continue
                if year_low <= 0:
                    continue

                range_pct = (year_high - year_low) / year_low

                if range_pct >= MIN_MOVE_PCT:
                    if year_high > 0:
                        pullback_from_high = (year_high - price) / year_high
                        if pullback_from_high < 0.60:
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

    print(f"\n   [FILTER] Reduced {len(candidates)} -> {len(valid_candidates)} Potential Winners.")
    return valid_candidates


def get_candles(symbol):
    if not config.FMP_KEY:
        return None

    time.sleep(API_DELAY)

    url = (
        f"https://financialmodelingprep.com/api/v3/historical-price-full/"
        f"{symbol}?timeseries=120&apikey={config.FMP_KEY}"
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
        if len(data) < 60:
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


# ==============================================================================
# 2. LOGIC ENGINE – original batch-style HTF analyzer
# ==============================================================================
def analyze_htf(candidate):
    symbol = candidate["symbol"]
    if check_blacklist(candidate):
        return None

    df = get_candles(symbol)
    if df is None:
        return None

    try:
        window = df.tail(60)
        current_close = window["Close"].iloc[-1]
        current_vol = window["Volume"].iloc[-1]

        # --- Dollar Volume Check ---
        dollar_vol = current_close * current_vol
        if dollar_vol < MIN_DOLLAR_VOL:
            return None

        # --- Move% Calculation ---
        highest_high = window["High"].max()
        lowest_low = window["Low"].min()

        if lowest_low == 0:
            return None

        move_pct = (highest_high - lowest_low) / lowest_low
        if move_pct < MIN_MOVE_PCT:
            return None

        # --- Pullback Check ---
        pullback = (highest_high - current_close) / highest_high
        if pullback > MAX_PULLBACK:
            return None

        # ======================================================================
        # Catalyst Engine v2 Integration
        # ======================================================================
        ctx_catalyst = CatalystContext(
            symbol=symbol,
            rvol=None,
            rs_rank=None,
        )
        catalyst = CATALYST_ENGINE.score(ctx_catalyst)

        # ======================================================================
        # Strategy Engine v2 Integration
        # ======================================================================
        ctx_strategy = StrategyContext(
            symbol=symbol,
            scanner="HTF",
            catalyst_score=catalyst.score,
            rs_rank=None,
            rvol=None,
            trend_label=None,
            move_pct=move_pct * 100,
            pullback_pct=pullback * 100,
            gap_pct=None,
            float_m=None,
            dollar_vol_m=dollar_vol / 1_000_000,
        )

        strategy = STRATEGY_ENGINE_V2.score(ctx_strategy, catalyst.tags)
        print(
            f"[HTF STRATEGY V2] {symbol}: score={strategy.score}, "
            f"conviction={strategy.conviction}, components={strategy.components}"
        )

        # ======================================================================
        # Chart Generation (batch mode)
        # ======================================================================
        with PLOT_LOCK:
            save_path = os.path.join(CHART_DIR, f"{symbol}_HTF.png")
            title = (
                f"{symbol} HTF\n"
                f"Move: +{move_pct * 100:.0f}% | Depth: -{pullback * 100:.1f}% | "
                f"$Vol: ${dollar_vol / 1_000_000:.1f}M\n"
                f"Catalyst: {catalyst.strength} ({catalyst.score}) | "
                f"Score: {strategy.score} ({strategy.conviction})"
            )
            plot_data = df.tail(90)
            mpf.plot(
                plot_data,
                type="candle",
                style="yahoo",
                title=title,
                volume=True,
                savefig=save_path,
            )
            matplotlib.pyplot.close("all")

        # ======================================================================
        # Return Result Row (batch schema)
        # ======================================================================
        return {
            "Symbol": symbol,
            "Sector": candidate["sector"],
            "Move%": round(move_pct * 100, 1),
            "Depth%": round(pullback * 100, 1),
            "Close": current_close,
            "$Vol (M)": round(dollar_vol / 1_000_000, 2),
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
# 2b. CLASS-BASED SYMBOL-LEVEL ENGINE (v3.0.0)
# ==============================================================================

class HTFScanner:
    """
    Class-based High Tight Flag / High Timeframe Trend scanner.

    Intended adapter-facing API:

        htf = HTFScanner()
        htf.get_htf_trend("NVDA") -> {
            "htf_trend": str | None,         # e.g., "HTF", or conviction label
            "htf_trend_score": float | None, # strategy.score
            "htf_raw": dict | None,          # full raw details
        }

    This reuses the core logic from analyze_htf but:
        - Does NOT write charts.
        - Does NOT use WorkerController.
        - Does NOT run batch screens.
        - Operates on a single symbol at a time.
    """

    def __init__(self, logger: Optional[Any] = None) -> None:
        self.logger = logger

    def _log_info(self, msg: str) -> None:
        if self.logger:
            self.logger.info(msg)

    def _log_error(self, msg: str) -> None:
        if self.logger:
            self.logger.error(msg)

    def get_htf_trend(self, symbol: str, sector: str = "Unknown") -> Dict[str, Any]:
        """
        Symbol-level HTF query.

        Returns:
            {
                "htf_trend": str | None,
                "htf_trend_score": float | None,
                "htf_raw": dict | None,
            }
        """
        candidate = {
            "symbol": symbol,
            "sector": sector,
            "industry": "Unknown",
        }

        try:
            self._log_info(f"[HTF] Evaluating high-timeframe trend for {symbol}")

            if check_blacklist(candidate):
                return {
                    "htf_trend": None,
                    "htf_trend_score": None,
                    "htf_raw": None,
                }

            df = get_candles(symbol)
            if df is None:
                return {
                    "htf_trend": None,
                    "htf_trend_score": None,
                    "htf_raw": None,
                }

            window = df.tail(60)
            current_close = window["Close"].iloc[-1]
            current_vol = window["Volume"].iloc[-1]

            # Dollar Volume
            dollar_vol = current_close * current_vol
            if dollar_vol < MIN_DOLLAR_VOL:
                return {
                    "htf_trend": None,
                    "htf_trend_score": None,
                    "htf_raw": None,
                }

            # Move%
            highest_high = window["High"].max()
            lowest_low = window["Low"].min()
            if lowest_low == 0:
                return {
                    "htf_trend": None,
                    "htf_trend_score": None,
                    "htf_raw": None,
                }

            move_pct = (highest_high - lowest_low) / lowest_low
            if move_pct < MIN_MOVE_PCT:
                return {
                    "htf_trend": None,
                    "htf_trend_score": None,
                    "htf_raw": None,
                }

            # Pullback
            pullback = (highest_high - current_close) / highest_high
            if pullback > MAX_PULLBACK:
                return {
                    "htf_trend": None,
                    "htf_trend_score": None,
                    "htf_raw": None,
                }

            # Catalyst integration
            ctx_catalyst = CatalystContext(
                symbol=symbol,
                rvol=None,
                rs_rank=None,
            )
            catalyst = CATALYST_ENGINE.score(ctx_catalyst)

            # Strategy integration
            ctx_strategy = StrategyContext(
                symbol=symbol,
                scanner="HTF",
                catalyst_score=catalyst.score,
                rs_rank=None,
                rvol=None,
                trend_label=None,
                move_pct=move_pct * 100,
                pullback_pct=pullback * 100,
                gap_pct=None,
                float_m=None,
                dollar_vol_m=dollar_vol / 1_000_000,
            )
            strategy = STRATEGY_ENGINE_V2.score(ctx_strategy, catalyst.tags)

            self._log_info(
                f"[HTF] {symbol}: score={strategy.score}, "
                f"conviction={strategy.conviction}, components={strategy.components}"
            )

            raw = {
                "symbol": symbol,
                "sector": sector,
                "move_pct": move_pct * 100,
                "pullback_pct": pullback * 100,
                "close": current_close,
                "dollar_vol": dollar_vol,
                "catalyst_score": catalyst.score,
                "catalyst_strength": catalyst.strength,
                "catalyst_tags": catalyst.tags,
                "strategy_score": strategy.score,
                "strategy_conviction": strategy.conviction,
                "strategy_components": strategy.components,
            }

            htf_trend_score = float(strategy.score) if strategy.score is not None else None
            # For Stage 2, treat "HTF" as the trend label when a valid setup is found.
            # You could also use strategy.conviction here if you want.
            htf_trend_label = "HTF" if htf_trend_score is not None else None

            return {
                "htf_trend": htf_trend_label,
                "htf_trend_score": htf_trend_score,
                "htf_raw": raw,
            }

        except Exception as e:
            self._log_error(f"[HTF] Error evaluating HTF for {symbol}: {e}")
            return {
                "htf_trend": None,
                "htf_trend_score": None,
                "htf_raw": None,
            }


# ==============================================================================
# 3. EXECUTION – batch CLI mode (preserved)
# ==============================================================================

if __name__ == "__main__":
    script_start_time = datetime.now()
    utils.print_metadata(SCRIPT_NAME, SCRIPT_VERSION)

    if not os.path.exists(CHART_DIR):
        os.makedirs(CHART_DIR)
    utils.clean_folder(CHART_DIR)

    # Initialize adaptive worker controller for HTF
    CONTROLLER = WorkerController(scanner_name="HTF", max_calls_per_min=300)

    raw_list = get_liquid_universe()
    candidates = filter_by_volatility(raw_list)

    matches = []

    if candidates:
        print(
            f"\n[TIME] {datetime.now().strftime('%H:%M:%S')} - Deep Scanning "
            f"{len(candidates)} candidates..."
        )

        governed_workers = CONTROLLER.get_worker_count()
        governed_workers = max(2, min(governed_workers, MAX_WORKERS_HARD_CAP))

        print(
            f"[INFO] Launching {governed_workers} Worker Threads "
            f"(GOVERNED MODE, {API_DELAY}s delay)."
        )

        analysis_start = time.time()
        processed_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=governed_workers) as executor:
            future_to_cand = {executor.submit(analyze_htf, c): c for c in candidates}

            for future in concurrent.futures.as_completed(future_to_cand):
                processed_count += 1
                try:
                    res = future.result()
                    if res:
                        matches.append(res)
                except Exception:
                    pass

                if processed_count % 10 == 0:
                    elapsed = time.time() - analysis_start
                    if elapsed > 0:
                        rate = processed_count / elapsed
                        with API_LOCK:
                            api_rate = (API_CALL_COUNT / elapsed) * 60
                    else:
                        rate = 0
                        api_rate = 0

                    print(
                        f"\rScan: {processed_count}/{len(candidates)} | "
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

    # ==========================================================================
    # 4. SAVE RESULTS (HTF + Strategy Engine v2)
    # ==========================================================================
    if matches:
        df_res = pd.DataFrame(matches)
        df_res = df_res.sort_values(by="StratScore", ascending=False)

        try:
            os.makedirs(config.DATA_DIR, exist_ok=True)
            temp_file = RESULTS_FILE + ".tmp"
            df_res.to_csv(temp_file, index=False)
            shutil.move(temp_file, RESULTS_FILE)
            print(f"\n[SUCCESS] Saved {len(matches)} HTF results to {RESULTS_FILE}")
        except Exception:
            print("\n[ERROR] Failed to save HTF results.")
    else:
        print("\n\n[DONE] No HTF setups found.")

    print(f"[TIME] Total Duration: {datetime.now() - script_start_time}")