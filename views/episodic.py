"""
Module: Dashboard View - Episodic Pivots
Version: 1.0.1
Author: Gemini (Assistant) & [Your Name]
Date: 2025-12-06
"""
import streamlit as st
import os
import glob
import config
from PIL import Image

def is_valid_image(path):
    try: return os.path.getsize(path) > 0 and Image.open(path).verify() is None
    except: return False

def clean_filename(filename):
    return filename.split("_")[0].replace(".png", "")

def render():
    st.header("💥 Episodic Pivot Candidates")

    if not os.path.exists(config.CHART_DIR_EP):
        st.info("No charts found.")
        return

    images = glob.glob(os.path.join(config.CHART_DIR_EP, "*.png"))
    valid_images = [img for img in images if is_valid_image(img)]

    if valid_images:
        cols = st.columns(3)
        for i, img in enumerate(valid_images):
            ticker = clean_filename(os.path.basename(img))
            with cols[i%3]:
                # FIX: Removed width param
                st.image(img)
                st.caption(f"**{ticker}**")
    else: st.info("No matches found.")