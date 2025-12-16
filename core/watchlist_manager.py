"""
Project: Nexus Watchlist Manager (The "Bridge")
Filename: core/watchlist_manager.py
Version: 1.0.2
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-15

Changelog:
- v1.0.2: COLUMN FIX.
          - Updated Momentum logic to look for 'Grade' OR 'Status'.
          - Fixes issue where "PERFECT" setups were ignored due to column mismatch.
- v1.0.1: Windows Encoding Fix.
"""

import pandas as pd
import os
import sys
import datetime

# --- ENCODING FIX (CRITICAL FOR WINDOWS) ---
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

import config

# --- CONFIGURATION ---
SCRIPT_NAME = "Watchlist Manager"
SCRIPT_VERSION = "1.0.2"

# Input Files
EP_RESULTS = os.path.join(config.DATA_DIR, "ep_results.csv")
HTF_RESULTS = os.path.join(config.DATA_DIR, "htf_results.csv")
MOM_RESULTS = os.path.join(config.DATA_DIR, "momentum_results.csv")

# Output File
WATCHLIST_FILE = config.WATCHLIST_FILE

# Selection Limits
MAX_MOMENTUM_ADDS = 15  # Limit noise from the broad scanner

# ==============================================================================
# 1. LOADERS
# ==============================================================================
def load_csv(filepath):
    """Safely loads a CSV file."""
    if not os.path.exists(filepath):
        return pd.DataFrame()
    try:
        return pd.read_csv(filepath)
    except Exception as e:
        print(f"[WARN] Could not read {filepath}: {e}")
        return pd.DataFrame()

# ==============================================================================
# 2. AGGREGATION LOGIC
# ==============================================================================
def build_focus_list():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🏗️  Building Focus List...")

    candidates = {} # Format: {Symbol: Reason}

    # --- 1. PROCESS EPISODIC PIVOTS (Highest Priority) ---
    df_ep = load_csv(EP_RESULTS)
    if not df_ep.empty:
        print(f"   🔥 Found {len(df_ep)} Episodic Pivots.")
        for _, row in df_ep.iterrows():
            sym = row['Symbol']
            candidates[sym] = f"EP (Gap {row.get('Gap%', 0)}%)"

    # --- 2. PROCESS HIGH TIGHT FLAGS (High Priority) ---
    df_htf = load_csv(HTF_RESULTS)
    if not df_htf.empty:
        print(f"   🚩 Found {len(df_htf)} High Tight Flags.")
        for _, row in df_htf.iterrows():
            sym = row['Symbol']
            # If already in EP, keep EP label (it's stronger), or combine?
            # Let's keep EP as primary reason if exists.
            if sym not in candidates:
                candidates[sym] = f"HTF (Move {row.get('Move%', 0)}%)"

    # --- 3. PROCESS MOMENTUM SCANS (Fill the rest) ---
    df_mom = load_csv(MOM_RESULTS)
    if not df_mom.empty:
        # Filter for Quality: Only A/A+ or Coiling

        # 1. Sort by RS Score (descending) if available
        if 'RS_Score' in df_mom.columns:
            df_mom = df_mom.sort_values(by='RS_Score', ascending=False)

        count_added = 0
        for _, row in df_mom.iterrows():
            if count_added >= MAX_MOMENTUM_ADDS: break

            sym = row['Symbol']

            # CHECK BOTH COLUMN NAMES (Legacy Support)
            status = str(row.get('Grade', row.get('Status', ''))).upper()

            # CRITERIA: "PERFECT" (A+ Setup) or "COILING" (Squeeze)
            is_prime = "PERFECT" in status or "COILING" in status

            if is_prime and sym not in candidates:
                candidates[sym] = f"MOMENTUM ({status})"
                count_added += 1

        print(f"   🚀 Added {count_added} Top Momentum candidates (Limit {MAX_MOMENTUM_ADDS}).")

    return candidates

# ==============================================================================
# 3. WRITER
# ==============================================================================
def save_watchlist(candidates):
    """Overwrites the watchlist file."""
    unique_tickers = list(candidates.keys())

    # 1. Save to TXT for Sniper (Comma separated)
    with open(WATCHLIST_FILE, "w") as f:
        f.write(", ".join(unique_tickers))

    print(f"\n✅ Watchlist Updated: {len(unique_tickers)} tickers.")
    print(f"📂 Path: {WATCHLIST_FILE}")

    # Print Summary for User
    print("\n--- 🎯 SNIPER FOCUS LIST ---")
    if not unique_tickers:
        print("(Empty - No valid setups found today)")
    else:
        for i, (sym, reason) in enumerate(candidates.items()):
            print(f"{i+1:02d}. {sym:<5} | {reason}")
    print("----------------------------")

# ==============================================================================
# 4. MAIN EXECUTION
# ==============================================================================
if __name__ == "__main__":
    print(f"=== {SCRIPT_NAME} v{SCRIPT_VERSION} ===")

    focus_list = build_focus_list()
    save_watchlist(focus_list)