"""
Degradation model — trimmed for demo app.
Only includes gas turbine degradation and temperature derating functions.
"""

from typing import Tuple, Optional
from config import Config, load_config


def get_gas_degradation_factors(
    operational_year: int,
    turbine_class: str,
    config: Optional[Config] = None
) -> Tuple[float, float]:
    """
    Gas turbine capacity and efficiency factors.

    Returns:
        Tuple of (capacity_factor, efficiency_factor)
    """
    if operational_year == 0:
        return 1.0, 1.0

    cfg = config or load_config()
    rates = cfg.degradation.gas_degradation_rates
    cap_rate, eff_rate = rates.get(turbine_class, rates['f_class'])

    capacity_factor = (1.0 - cap_rate) ** operational_year
    efficiency_factor = (1.0 - eff_rate) ** operational_year

    return capacity_factor, efficiency_factor


def get_temperature_derating(
    turbine_class: str,
    ambient_temp_c: float,
    config: Optional[Config] = None
) -> float:
    """
    Temperature derating factor for gas turbine capacity.
    """
    cfg = config or load_config()

    baseline_temp = 15.0  # ISO conditions
    temp_delta = ambient_temp_c - baseline_temp

    if turbine_class == 'aero':
        rate = cfg.gas_turbine.temp_derating_per_c_aero
    elif turbine_class == 'f_class':
        rate = cfg.gas_turbine.temp_derating_per_c_f_class
    elif turbine_class == 'h_class':
        rate = cfg.gas_turbine.temp_derating_per_c_h_class
    else:
        raise ValueError(f"Unknown turbine class: {turbine_class}")

    if temp_delta <= 0:
        return 1.0

    derating_factor = 1.0 - (rate * temp_delta)
    return max(0.7, derating_factor)
