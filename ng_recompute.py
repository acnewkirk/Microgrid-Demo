"""
Gas price slider backend — thin wrapper around AI Microgrids model code.

Reconstructs the NG LCOE computation pipeline from CSV fields (gpu_count,
annual_pue) so that we can recompute NG LCOE at arbitrary gas prices.
"""

import os
import sys

# Import from local lib/ (self-contained copy of AI Microgrids modules)
LIB_DIR = os.path.join(os.path.dirname(__file__), "lib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

from config import Config, load_config
from it_facil import calculate_facility_load, FacilityLoad
from power_systems_estimator import PowerFlowAnalyzer
from natgas_system_tool import generate_plant_configurations, TURBINE_LIBRARY
from lcoe_calc import calculate_gas_system_lcoe


# Module-level singletons (these don't change across calls)
_config = load_config()
_power_analyzer = PowerFlowAnalyzer(_config)
_ng_mult = _power_analyzer.get_bus_architecture_multipliers("natural_gas")

# Default values from config
DEFAULT_GAS_PRICE = _config.costs.default_gas_price_mmbtu  # $3.50/MMBtu
DEFAULT_UPTIME_PCT = _config.it_load.default_required_uptime_pct  # 99%
GPU_HOUR_BASELINE = _config.costs.gpu_hour_spot_price  # $2.40/GPU-hr


def build_hex_context(gpu_count: int, annual_pue: float) -> dict:
    """
    Build the reusable computation context for a hex. This is everything
    that doesn't depend on gas price — cache this per (gpu_count, pue).

    Returns dict with keys: facility_load, configs, target_mw
    """
    facility_load = calculate_facility_load(
        total_gpus=gpu_count,
        config=_config,
        pue=annual_pue,
        required_uptime_pct=DEFAULT_UPTIME_PCT,
        use_hourly_load_csv=False,  # NG path only needs scalar values
    )

    target_mw = (
        facility_load.it_load_design_mw * _ng_mult['bus_to_it']
        + facility_load.cooling_load_design_mw * _ng_mult['bus_to_cooling']
    ) * _ng_mult['grid_to_bus']

    configs = generate_plant_configurations(
        target_mw=target_mw,
        turbine_library=TURBINE_LIBRARY,
        design_ambient_temp_c=facility_load.design_ambient_temp_c,
        require_n_minus_1=False,
        config=_config,
        annual_energy_mwh=facility_load.annual_facility_energy_mwh,
    )

    return {
        "facility_load": facility_load,
        "configs": configs,
        "target_mw": target_mw,
    }


def recompute_ng_lcoe(hex_context: dict, gas_price: float) -> dict:
    """
    Recompute NG LCOE at a given gas price using a pre-built hex context.

    Returns dict with keys: base_lcoe, config_description, construction_years,
    nameplate_mw
    """
    facility_load = hex_context["facility_load"]
    configs = hex_context["configs"]

    if not configs:
        return {
            "base_lcoe": None,
            "config_description": "No feasible NG configurations",
            "construction_years": None,
            "nameplate_mw": None,
        }

    best_result = None
    best_config = None

    for cfg in configs:
        result = calculate_gas_system_lcoe(cfg, gas_price, facility_load, _config)
        if best_result is None or result.lcoe < best_result.lcoe:
            best_result = result
            best_config = cfg

    return {
        "base_lcoe": best_result.lcoe,
        "config_description": f"{best_config.n_units}x {best_config.turbine_model} ({best_config.cycle_type})",
        "construction_years": best_result.construction_years,
        "nameplate_mw": best_result.nameplate_capacity_mw,
    }
