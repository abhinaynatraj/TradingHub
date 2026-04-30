"""
TradingHub — Unified Streamlit Dashboard
=========================================
Run from repo root:
    python3 -m streamlit run app.py
"""

import subprocess
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

if st.sidebar.button("Recalculate Model Stats", type="primary"):
    with st.spinner("Crunching 11 years of data..."):
        
        # Safely execute the script from the root directory
        # sys.executable ensures it uses your venv, not system python
        try:
            subprocess.run(
                [sys.executable, "Fractal Sweep/engine/model_stats.py"], 
                check=True # This will raise an error if the script fails
            )
            
            # CRITICAL: Clear the Streamlit cache so it loads the new Parquet file
            st.cache_data.clear()
            st.sidebar.success("Recalculation complete!")
            st.rerun() # Refresh the page immediately
            
        except subprocess.CalledProcessError as e:
            st.sidebar.error(f"Engine failed to run. Check terminal for errors.")
