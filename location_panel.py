"""
Location breakdown panel — appears when a hex is clicked on the map.
Shows 4-architecture LCOE comparison and gas price slider.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from ng_recompute import (
    build_hex_context, recompute_ng_lcoe, DEFAULT_GAS_PRICE,
    GPU_HOUR_BASELINE,
)


# Architecture display config
ARCH_CONFIG = {
    "dc_coupled":   {"label": "DC Solar",     "color": "#E8912D"},
    "ac_coupled":   {"label": "AC Solar",     "color": "#F5C242"},
    "natural_gas":  {"label": "Natural Gas",  "color": "#4A90D9"},
    "grid":         {"label": "Grid",         "color": "#7B7B7B"},
}


def _fmt_lcoe(val: float) -> str:
    """Format LCOE value with units."""
    return f"${val:.3f}/kWh"


def render_location_panel(h3_index: str, df: pd.DataFrame, gpu_price: float, use_total: bool):
    """Render the location breakdown for a selected hex."""

    row = df[df["h3_index"] == h3_index]
    if row.empty:
        st.warning("No data for this location.")
        return
    row = row.iloc[0]

    # ── Location header ──────────────────────────────────────────
    state = row.get("state", "")
    lat, lon = row["latitude"], row["longitude"]
    header = f"{state}" if state else f"{lat:.2f}°N, {lon:.2f}°W"
    st.subheader(header)

    pue = row["annual_pue"]
    gpu_count = int(row["gpu_count"])
    facility_mw = row.get("facility_load_mw")
    meta_parts = [f"{lat:.2f}°N, {abs(lon):.2f}°W", f"PUE {pue:.2f}", f"{gpu_count:,} GPUs"]
    if facility_mw and not pd.isna(facility_mw):
        meta_parts.append(f"{facility_mw:.0f} MW facility")
    st.caption(" · ".join(meta_parts))

    # ── LCOE mode label ──────────────────────────────────────────
    if use_total:
        st.caption(f"Showing **LCOE + Value of Lost Compute** (GPU @ ${gpu_price:.2f}/hr)")
    else:
        st.caption("Showing **LCOE only** (excl. lost compute)")

    # ── Gas price slider ─────────────────────────────────────────
    st.markdown("")  # visual gap before controls
    # Use the hex's actual state-specific gas price as the default
    hex_gas_price = float(row.get("gas_price", DEFAULT_GAS_PRICE))
    gas_price = st.slider(
        "Natural gas price ($/MMBtu)",
        min_value=1.0, max_value=15.0, value=hex_gas_price, step=0.25,
        format="$%.2f",
        key=f"gas_price_slider_{h3_index}",
    )

    # ── Recompute NG LCOE ────────────────────────────────────────
    cache_key = f"hex_ctx_{gpu_count}_{pue:.6f}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = build_hex_context(gpu_count, pue)
    hex_ctx = st.session_state[cache_key]
    ng_result = recompute_ng_lcoe(hex_ctx, gas_price)

    # ── Build comparison bar chart ───────────────────────────────
    gpu_ratio = gpu_price / GPU_HOUR_BASELINE
    architectures = []
    base_lcoes = []
    vlc_components = []

    for arch, cfg in ARCH_CONFIG.items():
        base_col = f"{arch}_base_lcoe"
        total_col = f"{arch}_total_lcoe"

        if arch == "natural_gas" and ng_result["base_lcoe"] is not None:
            base = ng_result["base_lcoe"]
        else:
            base = row[base_col]

        vlc = (row[total_col] - row[base_col]) * gpu_ratio
        architectures.append(cfg["label"])
        base_lcoes.append(base)
        vlc_components.append(vlc)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="LCOE",
        x=architectures,
        y=base_lcoes,
        marker_color=[ARCH_CONFIG[a]["color"] for a in ARCH_CONFIG],
        text=[_fmt_lcoe(v) for v in base_lcoes],
        textposition="inside",
    ))

    if use_total:
        fig.add_trace(go.Bar(
            name="Value of Lost Compute",
            x=architectures,
            y=vlc_components,
            marker_color=[ARCH_CONFIG[a]["color"] for a in ARCH_CONFIG],
            marker_opacity=0.35,
            text=[_fmt_lcoe(v) if v > 0.001 else "" for v in vlc_components],
            textposition="inside",
        ))

    fig.update_layout(
        barmode="stack",
        yaxis_title="LCOE ($/kWh)",
        yaxis_tickformat="$.2f",
        height=380,
        margin={"t": 5, "b": 60, "l": 50, "r": 10},
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── NG config detail ─────────────────────────────────────────
    if ng_result["base_lcoe"] is not None:
        ng_display = ng_result["config_description"]
        ng_lcoe = _fmt_lcoe(ng_result["base_lcoe"])
        timeline = ng_result.get("construction_years")
        timeline_str = f", {timeline:.1f} yr build" if timeline else ""

        if gas_price != DEFAULT_GAS_PRICE:
            st.caption(f"NG @ ${gas_price:.2f}/MMBtu: **{ng_display}** — {ng_lcoe}{timeline_str}")
        else:
            csv_config = row.get("ng_config", "")
            st.caption(f"NG config: **{csv_config}** — {ng_lcoe}{timeline_str}")
