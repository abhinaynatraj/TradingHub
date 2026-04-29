"""
TradingHub — Unified Streamlit Dashboard
=========================================
Run from repo root:
    python3 -m streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st

# Make sure sibling page modules are importable
sys.path.insert(0, str(Path(__file__).parent))
from pages import fs_page, ttfm_page

st.set_page_config(
    page_title="TradingHub",
    page_icon="📊",
    layout="wide",
)

with st.sidebar:
    st.title("TradingHub")
    st.caption("ICT Quantitative Analytics")
    st.divider()
    model_choice = st.selectbox(
        "Select Strategy",
        ["Fractal Sweep", "TTrades Fractal Model"],
    )

if model_choice == "Fractal Sweep":
    fs_page.render()
elif model_choice == "TTrades Fractal Model":
    ttfm_page.render()
