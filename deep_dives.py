"""
Expandable deep-dive sections with static plots and explanatory text.
"""

import os
import io
import streamlit as st
import qrcode


ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
PREPRINT_URL = "https://www.researchsquare.com/article/rs-8272920/v1"


def _img(filename: str, width_pct: int = 100):
    """Display an image from assets, optionally constrained to a percentage of container width."""
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        st.info(f"Image not found: {filename}")
        return
    if width_pct >= 100:
        st.image(path, use_container_width=True)
    else:
        pad = (100 - width_pct) / 2
        _, center, _ = st.columns([pad, width_pct, pad])
        with center:
            st.image(path, use_container_width=True)


@st.cache_data
def _generate_qr_code(url: str) -> bytes:
    """Generate a QR code image as PNG bytes."""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()



def render_deep_dives():
    """Render all four expandable deep-dive sections."""

    # ── Section 1: Solar Microgrid Operations ────────────────────
    with st.expander("How Does a Solar Microgrid Power a Data Center?"):
        st.markdown("""
A DC-coupled solar microgrid pairs photovoltaic arrays with battery
storage on a shared DC bus. During the day, solar generation powers the
facility directly and charges the battery with any surplus. At night and
during intermittent cloud cover, the battery discharges to maintain
supply. The system is sized so that the battery can carry the facility
through extended low-irradiance periods, targeting 99% annual energy
service.

These plots show one week of simulated net power flows on the main DC
distribution bus, by hour, for a 31 MW facility in Colorado. Each
stacked area represents the hourly contribution of a source (solar,
battery discharge) or sink (facility load, battery charge, curtailment)
at the bus.

**Top — typical week:** Solar consistently exceeds demand. The battery
stays nearly full, absorbing midday surplus and discharging overnight.

**Bottom — hardest week of the year:** An extended low-irradiance period
draws the battery down. Unmet load appears at the tail end of the cloudy
stretch.
        """)
        # Vertically stacked at 90% width
        st.caption("Typical week")
        _img("energy_flow_normal_week.png", 80)
        st.caption("Hardest week")
        _img("energy_flow_hardest_week.png", 80)

    # ── Section 2: Natural Gas Scale Economies ───────────────────
    with st.expander("Natural Gas Scale Economies"):
        st.markdown("""
Natural gas LCOE as a function of facility size, showing all feasible
turbine configurations evaluated by the model. Each marker represents a
turbine class: aeroderivatives (small-scale, simple cycle only),
F-class, and H-class (large-scale, simple or combined cycle).

At small facility sizes (< 50 MW), only aeroderivative turbines are
feasible, with higher per-kW costs and lower electrical efficiency.
Combined-cycle configurations become available above ~100 MW and achieve
substantially lower LCOE. Horizontal reference lines show DC-coupled and
AC-coupled solar LCOE at the same location for comparison.
        """)
        _img("ng_scaling.png", 70)

    # ── Section 3: The Cost of Reliability ────────────────────────
    with st.expander("The Cost of Reliability"):
        st.markdown("""
LCOE vs. islanded share of annual energy for DC solar and natural gas
microgrids at four representative locations. The x-axis shows what
fraction of the facility's annual energy is provided by the microgrid
rather than the grid; the dashed line shows the local grid electricity
price for reference.

DC solar LCOE is relatively flat up to ~75–90% islanded share, then
rises steeply as the system must be oversized to cover the last few
percent of energy during worst-case weather. Natural gas LCOE decreases
with utilization as fixed capital costs are spread over more energy. The
crossover point — where the two curves intersect — varies by location
and depends on local solar resource and grid pricing.
        """)
        tab_socal, tab_houston, tab_va, tab_wash = st.tabs([
            "Southern California", "Houston", "Virginia", "Washington"
        ])
        with tab_socal:
            _img("uptime_sensitivity_socal.png", 55)
        with tab_houston:
            _img("uptime_sensitivity_houston.png", 55)
        with tab_va:
            _img("uptime_sensitivity_va.png", 55)
        with tab_wash:
            _img("uptime_sensitivity_wash.png", 55)

    # ── Section 4: DC vs. AC Coupling ────────────────────────────
    with st.expander("DC vs. AC Coupling"):
        st.markdown("""
DC-coupled microgrids reduce LCOE relative to AC-coupled systems by
eliminating power conversion stages between PV panels, battery, and IT
load. The advantage varies geographically: locations with lower solar
resource require larger systems to meet the same load, so the per-kWh
efficiency gain translates to a larger absolute cost difference. The mean
reduction across all locations is approximately 17% (~7¢/kWh).
        """)
        tab_flow, tab_map = st.tabs([
            "Power Flow Comparison", "DC Advantage Distribution"
        ])
        with tab_flow:
            _img("power_flow_comps.png", 60)
        with tab_map:
            _img("dc_vs_ac.png", 65)
