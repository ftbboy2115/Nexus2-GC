"""
Module: Dashboard View - Momentum Gallery
Version: 2.3.0 (The "Timestamp" Update)
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-09

Changelog:
- v2.3.0: Added 'Last Scanned' timestamp display for data freshness verification.
- v2.2.2: Fixed 'tuple indices' crash in loops.
"""
import streamlit as st
import pandas as pd
import os
import datetime # Added for timestamp formatting
import config
from PIL import Image

def is_valid_image(path):
    try: return os.path.getsize(path) > 0 and Image.open(path).verify() is None
    except: return False

def render():
    st.header("🌊 Momentum Candidates")

    if not os.path.exists(config.CSV_FILE):
        st.info("No data found. Run the scanner!")
        return

    # --- TIMESTAMP LOGIC ---
    try:
        # Get the time the file was last modified
        mod_time = os.path.getmtime(config.CSV_FILE)
        dt_str = datetime.datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"🕒 **Last Scanned:** {dt_str}")
    except:
        st.caption("🕒 **Last Scanned:** Unknown")
    # -----------------------

    try: df = pd.read_csv(config.CSV_FILE)
    except: return
    if 'Grade' not in df.columns: return

    perfect = df[df['Grade'] == 'PERFECT']
    coiling = df[df['Grade'] == 'COILING']
    surfing = df[df['Grade'] == 'SURFING']

    st.markdown("### 🎯 IMMEDIATE ACTION (Perfect Setups)")
    if not perfect.empty:
        st.success(f"Found {len(perfect)} High-Probability Setups")
        for index, row in perfect.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([2, 1, 1])
                p = os.path.join(config.CHART_DIR_KK, f"{row['Symbol']}.png")

                # FIX: Default image width fills column automatically
                if os.path.exists(p) and is_valid_image(p): c1.image(p)

                c2.markdown(f"### {row['Symbol']} ${row['Price']}")
                c2.markdown(f"## {row['Display']}")
                c2.caption(f"🏗️ {row.get('Industry', 'N/A')}")
                c2.write(f"**Why:** {row.get('Reason', 'Momentum')}")
                c2.metric("Velocity", f"{row['ADR%']}%")
                c2.metric("RS Score", f"{row.get('RS_Score', 0):.0f}")

                c3.info("📋 **Trade Plan**")
                c3.metric("Trigger", f"> ${row.get('Pivot', 0)}")
                c3.metric("Stop", f"< ${row.get('Stop_Loss', 0)}")
            st.markdown("---")
    else: st.info("No 'Perfect' setups found.")

    st.markdown("### ⭐ WATCHLIST")
    if not coiling.empty:
        cols = st.columns(4)
        for i, (index, r) in enumerate(coiling.iterrows()):
            p = os.path.join(config.CHART_DIR_KK, f"{r['Symbol']}.png")
            if os.path.exists(p) and is_valid_image(p):
                with cols[i % 4]: st.image(p); st.caption(f"**{r['Symbol']}**")

    with st.expander(f"🌊 See {len(surfing)} Trending Stocks"):
        cols = st.columns(4)
        for i, (index, r) in enumerate(surfing.iterrows()):
            p = os.path.join(config.CHART_DIR_KK, f"{r['Symbol']}.png")
            if os.path.exists(p) and is_valid_image(p):
                with cols[i % 4]: st.image(p); st.caption(f"**{r['Symbol']}**")