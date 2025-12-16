"""
Module: Performance Analytics (The "Trader's Journal")
Version: 1.1.0
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-14

Changelog:
- v1.1.0: Added robust error handling for corrupted/empty CSVs.
          - Strips whitespace from column names.
          - Checks for missing 'PnL' column before filtering.
"""
import streamlit as st
import pandas as pd
import requests
import os
import config

def get_local_trade_log():
    """Reads the local trade_log.csv which writes P&L on exit."""
    if not os.path.exists(config.TRADE_LOG_FILE):
        return pd.DataFrame()

    try:
        df = pd.read_csv(config.TRADE_LOG_FILE)

        # CRITICAL FIX: Clean column names (remove spaces)
        df.columns = df.columns.str.strip()

        # Validation: If PnL missing, return empty but warn
        if 'PnL' not in df.columns:
            st.error(f"⚠️ Corrupted Trade Log: Found columns {list(df.columns)}, expected 'PnL'.")
            return pd.DataFrame()

        # Clean Currency/Percent Strings ($100 -> 100)
        cols_to_clean = ['PnL', 'Percent']
        for col in cols_to_clean:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace('$', '', regex=False)
                df[col] = df[col].astype(str).str.replace('%', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        return df
    except Exception as e:
        st.error(f"Error reading trade log: {e}")
        return pd.DataFrame()

def render():
    st.header("📊 Performance Analytics (The Mirror)")

    # 1. Load Data
    df = get_local_trade_log()

    if df.empty:
        st.info("ℹ️ No closed trades recorded yet (or file is empty). Go catch some breakouts!")
        return

    # 2. Calculate Stats
    total_trades = len(df)
    winners = df[df['PnL'] > 0]
    losers = df[df['PnL'] <= 0]

    win_rate = (len(winners) / total_trades) * 100 if total_trades > 0 else 0
    avg_win = winners['Percent'].mean() if not winners.empty else 0
    avg_loss = losers['Percent'].mean() if not losers.empty else 0

    # Expectancy (R-Multiple)
    risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    # 3. The KK Scorecard
    st.subheader("🏆 The Qullamaggie Scorecard")

    c1, c2, c3, c4 = st.columns(4)

    # WIN RATE
    c1.metric("Win Rate", f"{win_rate:.1f}%", delta=f"{win_rate-30:.1f}% vs Target", delta_color="normal")
    if win_rate < 30: c1.warning("⚠️ Target: 30-50%")
    else: c1.success("✅ On Track")

    # AVG WIN
    c2.metric("Avg Win", f"{avg_win:.2f}%", delta=f"{avg_win-10:.2f}% vs Target")
    if avg_win < 10: c2.warning("⚠️ Let winners run! (Target >10%)")
    else: c2.success("✅ Home Run Hitter")

    # AVG LOSS
    c3.metric("Avg Loss", f"{avg_loss:.2f}%", delta=f"{-1.0 - avg_loss:.2f}% vs Target", delta_color="inverse")
    if avg_loss < -1.5: c3.error("❌ Cut losses faster! (Target < -1%)")
    elif avg_loss > -1.0: c3.success("✅ Sniper Discipline")

    # R-MULTIPLE
    c4.metric("Risk/Reward", f"{risk_reward:.2f}R")
    if risk_reward < 3.0: c4.warning("⚠️ Aim for 3R+")
    else: c4.success("✅ Asymmetric Returns")

    st.markdown("---")

    # 4. Recent History
    st.subheader("📜 Trade Journal")

    # Style the PnL column (Green for Profit, Red for Loss)
    try:
        st.dataframe(
            df.style.map(lambda x: 'color: green' if isinstance(x, (int, float)) and x > 0 else 'color: red', subset=['PnL']),
            use_container_width=True
        )
    except:
        st.dataframe(df)