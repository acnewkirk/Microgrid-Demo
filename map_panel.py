"""
Map panel — H3 hex choropleth with GPU $/hr slider, LCOE toggle, and view modes.
Viridis color scale for cost; marker overlay for lowest-cost system identification.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import h3

from ng_recompute import GPU_HOUR_BASELINE


# ── Technology marker config ─────────────────────────────────────────
# Scattermapbox with open-street-map tiles only supports circle markers.
# We differentiate technologies by bold colors with white outlines.

TECH_MARKERS = {
    "DC Solar":     {"color": "#1A3A7A"},   # blue, matches uptime plot DC Solar line
    "Natural Gas":  {"color": "#FF6600"},   # orange, matches uptime plot NG line
    "Grid":         {"color": "#A0A0A0"},   # medium gray
}

DIVERGING_DELTA = "RdBu_r"


# ── Data loading & geometry ──────────────────────────────────────────

@st.cache_data
def load_data(csv_path: str, _version: int = 2) -> pd.DataFrame:
    return pd.read_csv(csv_path)


@st.cache_data
def build_geojson(h3_indices: list) -> dict:
    """Convert H3 indices to GeoJSON FeatureCollection."""
    features = []
    for h3_idx in h3_indices:
        boundary = h3.cell_to_boundary(h3_idx)
        coords = [[lng, lat] for lat, lng in boundary]
        coords.append(coords[0])
        features.append({
            "type": "Feature",
            "id": h3_idx,
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })
    return {"type": "FeatureCollection", "features": features}


@st.cache_data
def build_centroids(h3_indices: list) -> pd.DataFrame:
    """Get centroid lat/lng for each hex (for marker overlay)."""
    rows = []
    for h3_idx in h3_indices:
        lat, lng = h3.cell_to_latlng(h3_idx)
        rows.append({"h3_index": h3_idx, "centroid_lat": lat, "centroid_lng": lng})
    return pd.DataFrame(rows)


# ── LCOE computation helpers ─────────────────────────────────────────

def adjust_lcoe_for_gpu_price(df: pd.DataFrame, gpu_price: float) -> pd.DataFrame:
    """Recompute total LCOE columns for a given GPU $/hr price."""
    ratio = gpu_price / GPU_HOUR_BASELINE
    out = df.copy()
    for arch in ["ac_coupled", "dc_coupled", "natural_gas", "grid"]:
        base_col = f"{arch}_base_lcoe"
        total_col = f"{arch}_total_lcoe"
        if base_col in df.columns and total_col in df.columns:
            vlc = df[total_col] - df[base_col]
            out[total_col] = df[base_col] + vlc * ratio
    return out


def determine_lowest_cost(df: pd.DataFrame, use_total: bool) -> pd.Series:
    """Return Series with lowest-cost architecture name per row."""
    suffix = "total_lcoe" if use_total else "base_lcoe"
    candidates = {
        "DC Solar": f"dc_coupled_{suffix}",
        "Natural Gas": f"natural_gas_{suffix}",
        "Grid": f"grid_{suffix}",
    }
    totals = pd.DataFrame({name: df[col] for name, col in candidates.items()})
    return totals.idxmin(axis=1)


def get_display_col(arch_prefix: str, use_total: bool) -> str:
    """Get the column name for the active LCOE mode."""
    return f"{arch_prefix}_{'total_lcoe' if use_total else 'base_lcoe'}"


# ── View modes ───────────────────────────────────────────────────────

VIEW_MODES = ["Lowest Cost", "DC Solar", "Natural Gas", "Grid", "NG − DC Cost"]


def _lcoe_label(use_total: bool) -> str:
    return "LCOE + VLC ($/kWh)" if use_total else "LCOE ($/kWh)"


# ── Main render function ─────────────────────────────────────────────

def render_map_panel(df_all: pd.DataFrame, geojson: dict, centroids: pd.DataFrame):
    """Render the map panel with controls. Returns (selected_h3, filtered_df, gpu_price, use_total)."""

    # ── Controls ─────────────────────────────────────────────────
    col_lcoe, col_gpu, col_view = st.columns([1.5, 2, 2.5])

    with col_lcoe:
        lcoe_mode = st.radio(
            "Show",
            ["LCOE", "Value of Lost Compute"],
            horizontal=True,
            help="LCOE = generation cost only. Value of Lost Compute adds the cost of idle GPUs during construction.",
        )
    use_total = lcoe_mode == "Value of Lost Compute"

    with col_gpu:
        if use_total:
            gpu_price = st.slider(
                "GPU $/hr (for VLC calculation)",
                min_value=0.50, max_value=5.00, value=GPU_HOUR_BASELINE, step=0.10,
                format="$%.2f",
            )
        else:
            gpu_price = GPU_HOUR_BASELINE  # doesn't matter for base LCOE

    with col_view:
        view_mode = st.radio(
            "View", VIEW_MODES, horizontal=True,
            help=(
                "**NG − DC Cost** shows the difference between Natural Gas Microgrid "
                "and DC Solar Microgrid LCOE at each location. Positive (red) means "
                "natural gas is more expensive; negative (blue) means DC solar is "
                "more expensive. Click a hex to open the location panel, where you "
                "can adjust the natural gas price with a slider to see how it shifts "
                "the comparison."
            ),
        )

    # ── Prepare data ─────────────────────────────────────────────
    df = adjust_lcoe_for_gpu_price(df_all, gpu_price)
    df["lowest_cost"] = determine_lowest_cost(df, use_total)

    # Merge centroids for marker overlay
    df = df.merge(centroids, on="h3_index", how="left")

    # Active LCOE column for coloring
    label = _lcoe_label(use_total)

    # ── Build figure ─────────────────────────────────────────────
    center = {"lat": 39.5, "lon": -98.5}
    zoom = 3.2
    fig = go.Figure()

    if view_mode == "Lowest Cost":
        # Base: viridis choropleth showing the lowest LCOE value
        suffix = "total_lcoe" if use_total else "base_lcoe"
        cost_cols = [f"dc_coupled_{suffix}", f"natural_gas_{suffix}", f"grid_{suffix}"]
        df["best_lcoe"] = df[cost_cols].min(axis=1)

        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=df["h3_index"],
            z=df["best_lcoe"],
            colorscale="Viridis_r",
            zmin=df["best_lcoe"].quantile(0.02),
            zmax=df["best_lcoe"].quantile(0.98),
            marker_opacity=0.7,
            marker_line_width=0.3,
            colorbar=dict(title=label, tickformat="$.3f"),
            hovertemplate=(
                "DC Solar: $%{customdata[0]:.3f}/kWh<br>"
                "Natural Gas: $%{customdata[1]:.3f}/kWh<br>"
                "Grid: $%{customdata[2]:.3f}/kWh<br>"
                "<extra></extra>"
            ),
            customdata=df[cost_cols].values,
        ))

        # Marker overlay: colored circles at hex centroids
        for tech, mcfg in TECH_MARKERS.items():
            mask = df["lowest_cost"] == tech
            sub = df[mask]
            if len(sub) == 0:
                continue
            fig.add_trace(go.Scattermapbox(
                lat=sub["centroid_lat"],
                lon=sub["centroid_lng"],
                mode="markers",
                marker=dict(
                    size=7,
                    color=mcfg["color"],
                    opacity=0.9,
                ),
                name=tech,
                hoverinfo="skip",
            ))

    elif view_mode in ("DC Solar", "Natural Gas", "Grid"):
        arch_map = {
            "DC Solar": "dc_coupled",
            "Natural Gas": "natural_gas",
            "Grid": "grid",
        }
        col = get_display_col(arch_map[view_mode], use_total)

        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=df["h3_index"],
            z=df[col],
            colorscale="Viridis_r",
            zmin=df[col].quantile(0.02),
            zmax=df[col].quantile(0.98),
            marker_opacity=0.7,
            marker_line_width=0.3,
            colorbar=dict(title=f"{view_mode} {label}", tickformat="$.3f"),
            hovertemplate=f"{view_mode}: $%{{z:.3f}}/kWh<extra></extra>",
        ))

    else:  # Δ (NG − DC)
        suffix = "total_lcoe" if use_total else "base_lcoe"
        df["delta_ng_dc"] = df[f"natural_gas_{suffix}"] - df[f"dc_coupled_{suffix}"]
        abs_max = df["delta_ng_dc"].abs().quantile(0.98)

        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=df["h3_index"],
            z=df["delta_ng_dc"],
            colorscale=DIVERGING_DELTA,
            zmin=-abs_max,
            zmax=abs_max,
            zmid=0,
            marker_opacity=0.7,
            marker_line_width=0.3,
            colorbar=dict(title="NG − DC Cost ($/kWh)", tickformat="$.3f"),
            hovertemplate="NG − DC Cost: $%{z:.3f}/kWh<extra></extra>",
        ))

    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox_center=center,
        mapbox_zoom=zoom,
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=550,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )

    # ── Hex count summary ───────────────────────────────────────
    counts = df["lowest_cost"].value_counts()
    total = len(df)
    parts = []
    for tech, mcfg in TECH_MARKERS.items():
        n = counts.get(tech, 0)
        parts.append(f"**{tech}**: {n} ({n*100/total:.0f}%)")
    st.caption("Lowest cost: " + " · ".join(parts))

    # ── Display and capture click ────────────────────────────────
    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="map")

    selected_h3 = None
    if event and event.selection and event.selection.points:
        point = event.selection.points[0]
        selected_h3 = point.get("location")

    return selected_h3, df, gpu_price, use_total
