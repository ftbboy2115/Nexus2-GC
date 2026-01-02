"""
Project: Unified Daily Scanner Report
Filename: core/report_daily.py
Version: 1.0.0
Author: Copilot, Gemini (Assistant) & [Your Name]
Date: 2025-12-16

Purpose:
    Merge EP, Trend Daily, and HTF scanner outputs into a single,
    normalized, ranked daily report using Strategy Engine v2 scores.

Outputs (written to /data/):
    - unified_report.csv
    - unified_report_topA.csv
    - unified_report_dashboard.json
"""

import os
import json
import pandas as pd
from datetime import datetime
import config

# ----------------------------------------------------------------------
# FILE PATHS
# ----------------------------------------------------------------------
EP_FILE     = os.path.join(config.DATA_DIR, "ep_results.csv")
TREND_FILE  = os.path.join(config.DATA_DIR, "trend_results.csv")
HTF_FILE    = os.path.join(config.DATA_DIR, "htf_results.csv")

OUT_FULL    = os.path.join(config.DATA_DIR, "unified_report.csv")
OUT_TOPA    = os.path.join(config.DATA_DIR, "unified_report_topA.csv")
OUT_JSON    = os.path.join(config.DATA_DIR, "unified_report_dashboard.json")


# ----------------------------------------------------------------------
# LOAD HELPERS
# ----------------------------------------------------------------------
def load_csv(path, scanner_name):
    if not os.path.exists(path):
        print(f"[WARN] Missing file: {path}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    df["Scanner"] = scanner_name
    return df


# ----------------------------------------------------------------------
# NORMALIZATION
# ----------------------------------------------------------------------
def normalize_columns(df):
    """
    Normalize column names across scanners.
    Missing columns are filled with None.
    """

    required_cols = [
        "Symbol",
        "Scanner",
        "StratScore",
        "StratConviction",
        "CatalystScore",
        "CatalystStrength",
        "CatalystTags",
        "Reason",
        "Sector",
        "Industry",
        "Move%",
        "Gap%",
        "RS_Score",
        "Vol_M",
        "Float_M",
        "Depth%",
        "Close",
        "Pivot",
        "Stop_Loss",
    ]

    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    return df[required_cols]


# ----------------------------------------------------------------------
# MAIN MERGE LOGIC
# ----------------------------------------------------------------------
def build_unified_report():
    print("\n[INFO] Loading scanner outputs...")

    ep_df    = load_csv(EP_FILE, "EP")
    trend_df = load_csv(TREND_FILE, "TREND")
    htf_df   = load_csv(HTF_FILE, "HTF")

    frames = [ep_df, trend_df, htf_df]
    frames = [f for f in frames if not f.empty]

    if not frames:
        print("[ERROR] No scanner outputs found. Nothing to merge.")
        return

    print("[INFO] Normalizing columns...")
    frames = [normalize_columns(f) for f in frames]

    print("[INFO] Merging...")
    merged = pd.concat(frames, ignore_index=True)

    # Sort by unified Strategy Engine v2 score
    merged = merged.sort_values(by="StratScore", ascending=False)

    # Add timestamp
    merged["CreatedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # SAVE FULL REPORT
    # ------------------------------------------------------------------
    print(f"[INFO] Saving full report → {OUT_FULL}")
    merged.to_csv(OUT_FULL, index=False)

    # ------------------------------------------------------------------
    # SAVE TOP A-TIER REPORT
    # ------------------------------------------------------------------
    topA = merged[merged["StratConviction"] == "A"]
    print(f"[INFO] Saving A-tier report → {OUT_TOPA}")
    topA.to_csv(OUT_TOPA, index=False)

    # ------------------------------------------------------------------
    # SAVE JSON DASHBOARD
    # ------------------------------------------------------------------
    print(f"[INFO] Saving dashboard JSON → {OUT_JSON}")
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(merged.to_dict(orient="records"), f, indent=2)

    print("\n[SUCCESS] Unified report generation complete.")


# ----------------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print("\n=== Unified Daily Report Builder ===")
    build_unified_report()