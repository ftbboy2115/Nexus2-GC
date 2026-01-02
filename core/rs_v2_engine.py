"""
Project: RS v2 Engine (Percentile Leadership)
Filename: core/rs_v2_engine.py
Version: 2.0.0
Author: Copilot & Clay
Date: 2025-12-18

Purpose:
    - Load strategy_log.jsonl
    - Aggregate RS data per symbol over a recent window
    - Compute RS v2 metrics (percentiles, trend, acceleration, multi-timeframe)
    - Expose a symbol-level, queryable API:
        RSEngineV2.get_rs(symbol) -> Dict[str, Any]
    - Optionally persist rs_v2 metrics to data/rs_v2.csv when run as a script.

Design:
    - On initialization, RSEngineV2:
        1) Loads strategy_log.jsonl
        2) Builds the per-record RS dataframe
        3) Computes universe-level RS v2 metrics
        4) Stores a per-symbol dataframe in memory (self.df_symbols)

    - get_rs(symbol) returns:
        {
            "symbol": str,
            "rs_value": float | None,          # rs_v2_score (0-100)
            "rs_rank": float | None,           # rs_percentile (0-100)
            "rs_sector_rank": float | None,    # rs_sector_percentile (0-100)
            "raw": Dict[str, Any] | None       # full row of RS v2 fields for the symbol
        }

    - Existing helper functions from v1.0.0 are preserved and reused.
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
import numpy as np

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

import config
import utils  # for metadata print, if desired

# ==============================================================================
# CONFIG
# ==============================================================================
SCRIPT_NAME = os.path.basename(__file__)
SCRIPT_VERSION = "2.0.0"

STRATEGY_LOG_FILE = os.path.join(config.DATA_DIR, "strategy_log.jsonl")
RS_V2_OUTPUT_FILE = os.path.join(config.DATA_DIR, "rs_v2.csv")

RS_WINDOW_DAYS = 90   # how many days back to consider
MIN_RS_POINTS = 3     # minimum data points to compute trends meaningfully


# ==============================================================================
# HELPERS (unchanged core logic)
# ==============================================================================

def parse_datetime_safe(value):
    """Parse timestamps in multiple formats safely."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip().replace("Z", "")

    # Try ISO format with T
    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass

    # Try space-separated datetime: "YYYY-MM-DD HH:MM:SS"
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Try date-only
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except Exception:
        pass

    return None


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def load_strategy_log(path):
    """Load strategy_log.jsonl into a list of dicts."""
    if not os.path.exists(path):
        print(f"[WARN] Strategy log not found at {path}")
        return []

    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                records.append(obj)
            except Exception:
                continue

    print(f"[INFO] Loaded {len(records)} records from strategy_log.")
    return records


def build_rs_dataframe(records, window_days=RS_WINDOW_DAYS):
    """Convert strategy log records into a DataFrame filtered by date and RS presence."""
    if not records:
        return pd.DataFrame()

    rows = []
    cutoff = datetime.now() - timedelta(days=window_days)

    for r in records:
        symbol = r.get("symbol")
        if not symbol:
            continue

        created_at = parse_datetime_safe(r.get("created_at"))
        if created_at is None or created_at < cutoff:
            continue

        rs_raw = safe_float(r.get("rs_raw"))
        if rs_raw is None:
            # skip entries without RS data
            continue

        setup = r.get("setup")
        source_scanner = r.get("source_scanner")

        raw_scanner_data = r.get("raw_scanner_data", {}) or {}
        sector = raw_scanner_data.get("sector") or r.get("sector") or "Unknown"
        industry = raw_scanner_data.get("industry") or r.get("industry") or "Unknown"

        rows.append({
            "symbol": symbol,
            "created_at": created_at,
            "rs_raw": rs_raw,
            "rs_lookback_days": safe_float(r.get("rs_lookback_days")),
            "setup": setup,
            "source_scanner": source_scanner,
            "sector": sector,
            "industry": industry,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(["symbol", "created_at"]).reset_index(drop=True)
    print(f"[INFO] RS dataframe built with {len(df)} rows across {df['symbol'].nunique()} symbols.")
    return df


def compute_linear_trend(y):
    """
    Compute linear trend slope of y over index 0..n-1.
    Returns slope (float). If insufficient data, returns 0.0.
    """
    if len(y) < MIN_RS_POINTS:
        return 0.0
    x = np.arange(len(y), dtype=float)
    y = np.array(y, dtype=float)
    x_mean = x.mean()
    y_mean = y.mean()
    denom = np.sum((x - x_mean) ** 2)
    if denom == 0:
        return 0.0
    slope = np.sum((x - x_mean) * (y - y_mean)) / denom
    return float(slope)


def normalize_series_to_0_100(s, default_value=50.0):
    """
    Normalize a numeric series into 0-100 space using z-score-like scaling and clipping.
    If series is constant or empty, return a series filled with default_value.
    """
    if s is None or len(s) == 0:
        return pd.Series([], dtype=float)

    s = pd.Series(s, dtype=float)
    mean = s.mean()
    std = s.std(ddof=0)

    if std == 0 or np.isnan(std):
        return pd.Series([default_value] * len(s), index=s.index, dtype=float)

    z = (s - mean) / std
    # map z-score to 0-100; clip to avoid extreme outliers
    scaled = 50 + 15 * z
    scaled = scaled.clip(lower=0, upper=100)
    return scaled


def compute_symbol_metrics(df_symbol):
    """
    Compute RS metrics for a single symbol.
    df_symbol: DataFrame filtered to that symbol, sorted by created_at.
    """
    rs_values = df_symbol["rs_raw"].values
    if len(rs_values) == 0:
        return None

    rs_raw_mean = float(np.mean(rs_values))

    # Linear trend (slope) over time index
    rs_raw_trend = compute_linear_trend(rs_values)

    # Acceleration: trend of second half minus trend of first half
    if len(rs_values) >= 2 * MIN_RS_POINTS:
        mid = len(rs_values) // 2
        trend_first = compute_linear_trend(rs_values[:mid])
        trend_second = compute_linear_trend(rs_values[mid:])
        rs_raw_acceleration = float(trend_second - trend_first)
    else:
        # fallback: simple normalized difference between last and first
        rs_raw_acceleration = float(rs_values[-1] - rs_values[0]) / max(len(rs_values), 1)

    # Multi-timeframe RS:
    # Short: last 20, Medium: last 50, Long: all (up to window)
    def window_mean(vals, window_size):
        if len(vals) == 0:
            return None
        if len(vals) < window_size:
            return float(np.mean(vals))
        return float(np.mean(vals[-window_size:]))

    rs_short = window_mean(rs_values, 20)
    rs_medium = window_mean(rs_values, 50)
    rs_long = float(np.mean(rs_values))  # same as rs_raw_mean, but explicit

    # Weighted blend: 40% medium, 30% long, 30% short (if present)
    weights = []
    components = []

    if rs_medium is not None:
        weights.append(0.4)
        components.append(rs_medium)
    if rs_long is not None:
        weights.append(0.3)
        components.append(rs_long)
    if rs_short is not None:
        weights.append(0.3)
        components.append(rs_short)

    if components and weights and len(components) == len(weights):
        rs_multi_timeframe = float(np.average(components, weights=weights))
    else:
        rs_multi_timeframe = rs_raw_mean

    last_row = df_symbol.iloc[-1]
    last_seen = last_row["created_at"]
    sector = last_row.get("sector", "Unknown")
    industry = last_row.get("industry", "Unknown")

    setups_seen = sorted(set(df_symbol["setup"].dropna().astype(str).tolist()))
    scanners_seen = sorted(set(df_symbol["source_scanner"].dropna().astype(str).tolist()))

    return {
        "symbol": last_row["symbol"],
        "sector": sector,
        "industry": industry,
        "last_seen": last_seen,
        "rs_raw_mean": rs_raw_mean,
        "rs_raw_trend": rs_raw_trend,
        "rs_raw_acceleration": rs_raw_acceleration,
        "rs_multi_timeframe": rs_multi_timeframe,
        "setups_seen_in": ",".join(setups_seen),
        "scanners_seen_in": ",".join(scanners_seen),
    }


def compute_universe_metrics(df_rs):
    """
    Compute RS v2 metrics for the entire universe.
    df_rs: per-record RS dataframe (symbol, created_at, rs_raw, sector, etc.)
    Returns: DataFrame with one row per symbol and all RS v2 fields.
    """
    if df_rs.empty:
        print("[WARN] No RS data available to compute RS v2.")
        return pd.DataFrame()

    # Group by symbol, compute base metrics
    symbol_groups = df_rs.groupby("symbol")
    records = []

    for symbol, g in symbol_groups:
        m = compute_symbol_metrics(g.sort_values("created_at"))
        if m is not None:
            records.append(m)

    if not records:
        print("[WARN] No symbols had sufficient RS data for RS v2.")
        return pd.DataFrame()

    df_symbols = pd.DataFrame(records)

    # Percentile ranking by rs_raw_mean
    df_symbols["rs_percentile"] = df_symbols["rs_raw_mean"].rank(pct=True) * 100.0

    # Sector percentile ranking
    def sector_percentile(group):
        return group["rs_raw_mean"].rank(pct=True) * 100.0

    df_symbols["rs_sector_percentile"] = (
        df_symbols.groupby("sector", group_keys=False).apply(sector_percentile, include_groups=False)
    )

    # Normalize supporting metrics into 0-100 for blending
    df_symbols["rs_trend_norm"] = normalize_series_to_0_100(df_symbols["rs_raw_trend"])
    df_symbols["rs_accel_norm"] = normalize_series_to_0_100(df_symbols["rs_raw_acceleration"])
    df_symbols["rs_multi_norm"] = normalize_series_to_0_100(df_symbols["rs_multi_timeframe"])

    # Composite RS v2 score
    # 40% rs_percentile, 30% rs_multi_norm, 20% rs_trend_norm, 10% rs_accel_norm
    df_symbols["rs_v2_score"] = (
        0.40 * df_symbols["rs_percentile"]
        + 0.30 * df_symbols["rs_multi_norm"]
        + 0.20 * df_symbols["rs_trend_norm"]
        + 0.10 * df_symbols["rs_accel_norm"]
    )

    # Clip final score to 0-100
    df_symbols["rs_v2_score"] = df_symbols["rs_v2_score"].clip(lower=0, upper=100)

    # Sort by RS v2 descending
    df_symbols = df_symbols.sort_values("rs_v2_score", ascending=False).reset_index(drop=True)

    return df_symbols


def save_rs_v2(df_symbols, path):
    """
    Save RS v2 metrics to CSV.
    """
    if df_symbols.empty:
        # Write an empty file with header for downstream consumers
        print("[INFO] No RS v2 symbols to save; creating empty rs_v2.csv with header.")
        cols = [
            "symbol",
            "rs_v2_score",
            "rs_percentile",
            "rs_sector_percentile",
            "rs_raw_mean",
            "rs_raw_trend",
            "rs_raw_acceleration",
            "rs_multi_timeframe",
            "last_seen",
            "scanners_seen_in",
            "setups_seen_in",
        ]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pd.DataFrame(columns=cols).to_csv(path, index=False)
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)

    out_df = df_symbols[[
        "symbol",
        "rs_v2_score",
        "rs_percentile",
        "rs_sector_percentile",
        "rs_raw_mean",
        "rs_raw_trend",
        "rs_raw_acceleration",
        "rs_multi_timeframe",
        "last_seen",
        "scanners_seen_in",
        "setups_seen_in",
    ]].copy()

    # Ensure datetime is serialized
    out_df["last_seen"] = out_df["last_seen"].astype(str)

    out_df.to_csv(path, index=False)
    print(f"[SUCCESS] RS v2 metrics saved to {path} ({len(out_df)} symbols).")


# ==============================================================================
# CLASS-BASED ENGINE (v2.0.0)
# ==============================================================================

class RSEngineV2:
    """
    Class-based RS v2 engine.

    On initialization, loads strategy_log.jsonl, computes RS v2 metrics for the
    entire universe, and exposes a symbol-level query API via get_rs(symbol).

    Intended adapter-facing API:
        engine = RSEngineV2()
        engine.get_rs("NVDA") -> {
            "symbol": "NVDA",
            "rs_value": <rs_v2_score>,
            "rs_rank": <rs_percentile>,
            "rs_sector_rank": <rs_sector_percentile>,
            "raw": { ... per-symbol RS v2 fields ... }
        }
    """

    def __init__(
        self,
        strategy_log_path: Optional[str] = None,
        window_days: int = RS_WINDOW_DAYS,
        logger: Optional[Any] = None,
    ) -> None:
        self.logger = logger
        self.strategy_log_path = strategy_log_path or STRATEGY_LOG_FILE
        self.window_days = window_days

        self.df_rs: pd.DataFrame = pd.DataFrame()
        self.df_symbols: pd.DataFrame = pd.DataFrame()

        self._initialize()

    def _log_info(self, msg: str) -> None:
        if self.logger:
            self.logger.info(msg)
        else:
            print(msg)

    def _log_error(self, msg: str) -> None:
        if self.logger:
            self.logger.error(msg)
        else:
            print(msg)

    def _initialize(self) -> None:
        start_time = datetime.now()
        self._log_info(
            f"[RS v2] Initializing RSEngineV2 v{SCRIPT_VERSION} at "
            f"{start_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        try:
            # 1) Load log
            records = load_strategy_log(self.strategy_log_path)

            # 2) Build base RS dataframe
            self.df_rs = build_rs_dataframe(records, window_days=self.window_days)

            # 3) Compute universe-level RS v2 metrics
            self.df_symbols = compute_universe_metrics(self.df_rs)

            # Index by symbol for fast lookup
            if not self.df_symbols.empty:
                self.df_symbols = self.df_symbols.set_index("symbol", drop=False)

            end_time = datetime.now()
            self._log_info(
                f"[RS v2] Initialization complete. Symbols: "
                f"{len(self.df_symbols)}. Duration: {end_time - start_time}"
            )
        except Exception as e:
            self._log_error(f"[RS v2] Initialization failed: {e}")
            self.df_rs = pd.DataFrame()
            self.df_symbols = pd.DataFrame()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_rs(self, symbol: str) -> Dict[str, Any]:
        """
        Return RS v2 metrics for a single symbol.

        Returns:
            {
                "symbol": str,
                "rs_value": float | None,         # rs_v2_score
                "rs_rank": float | None,          # rs_percentile
                "rs_sector_rank": float | None,   # rs_sector_percentile
                "raw": Dict[str, Any] | None
            }
        """
        if self.df_symbols.empty:
            return {
                "symbol": symbol,
                "rs_value": None,
                "rs_rank": None,
                "rs_sector_rank": None,
                "raw": None,
            }

        if symbol not in self.df_symbols.index:
            return {
                "symbol": symbol,
                "rs_value": None,
                "rs_rank": None,
                "rs_sector_rank": None,
                "raw": None,
            }

        row = self.df_symbols.loc[symbol]

        raw = {
            "symbol": row.get("symbol"),
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "last_seen": row.get("last_seen"),
            "rs_v2_score": row.get("rs_v2_score"),
            "rs_percentile": row.get("rs_percentile"),
            "rs_sector_percentile": row.get("rs_sector_percentile"),
            "rs_raw_mean": row.get("rs_raw_mean"),
            "rs_raw_trend": row.get("rs_raw_trend"),
            "rs_raw_acceleration": row.get("rs_raw_acceleration"),
            "rs_multi_timeframe": row.get("rs_multi_timeframe"),
            "scanners_seen_in": row.get("scanners_seen_in"),
            "setups_seen_in": row.get("setups_seen_in"),
        }

        return {
            "symbol": row.get("symbol"),
            "rs_value": row.get("rs_v2_score"),
            "rs_rank": row.get("rs_percentile"),
            "rs_sector_rank": row.get("rs_sector_percentile"),
            "raw": raw,
        }


# ==============================================================================
# MAIN (optional batch mode, preserved for CLI use)
# ==============================================================================

if __name__ == "__main__":
    start_time = datetime.now()
    utils.print_metadata(SCRIPT_NAME, SCRIPT_VERSION)
    print(f"[TIME] RS v2 Engine Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Use the class-based engine to compute metrics and save CSV
    engine = RSEngineV2(strategy_log_path=STRATEGY_LOG_FILE, window_days=RS_WINDOW_DAYS)
    df_symbols = engine.df_symbols

    save_rs_v2(df_symbols, RS_V2_OUTPUT_FILE)

    end_time = datetime.now()
    print(f"[TIME] RS v2 Engine Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[TIME] Total Duration: {end_time - start_time}")