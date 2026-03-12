"""
Microgrid Demo App — Interactive presentation tool for Newkirk et al. 2026.

Run with: streamlit run app.py
"""

import os
import streamlit as st

from map_panel import load_data, build_geojson, build_centroids, render_map_panel
from location_panel import render_location_panel
from deep_dives import render_deep_dives, _generate_qr_code, PREPRINT_URL

# ── Page config ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="Microgrid Demo — Newkirk et al. 2026",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Title + QR + description in one compact row ─────────────────────

title_col, qr_col = st.columns([6, 1])
with title_col:
    st.title("Off-Grid Power for AI Data Centers")
    st.markdown(
        "Comparing DC-coupled solar microgrids, natural gas generation, and grid "
        "electricity across CONUS at **99% uptime**. Natural gas results use a "
        "3-year construction timeline at 100,000 GPUs. "
        f"[Preprint: Newkirk et al. 2026]({PREPRINT_URL})"
    )
with qr_col:
    st.image(_generate_qr_code(PREPRINT_URL), width=90)

# ── Load data ────────────────────────────────────────────────────────

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "demo_lcoe_merged.csv")
df_all = load_data(DATA_PATH)
h3_list = df_all["h3_index"].unique().tolist()
geojson = build_geojson(h3_list)
centroids = build_centroids(h3_list)

# ── Layout: map (left) + location panel (right) ─────────────────────

map_col, loc_col = st.columns([3, 1])

with map_col:
    selected_h3, df_filtered, gpu_price, use_total = render_map_panel(df_all, geojson, centroids)

    if selected_h3:
        st.session_state["selected_h3"] = selected_h3

with loc_col:
    active_h3 = st.session_state.get("selected_h3")
    if active_h3:
        render_location_panel(active_h3, df_filtered, gpu_price, use_total)
    else:
        st.info("Click a hex on the map to see location details.")

# ── Deep dives ───────────────────────────────────────────────────────

st.divider()
render_deep_dives()
