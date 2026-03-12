"""
LCOE Calculator — trimmed for demo app.
Only includes calculate_gas_system_lcoe and its helper functions.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, List
from config import Config
from power_systems_estimator import PowerFlowAnalyzer
from it_facil import FacilityLoad

HOURS_PER_YEAR = 8760


@dataclass
class LCOEResult:
    system_type: str
    capex_npv: float
    opex_npv: float
    energy_npv: float
    lcoe: float
    construction_years: float
    nameplate_capacity_mw: float


def calculate_npv(cash_flows: list, discount_rate: float, start_year: int = 0) -> float:
    """Calculate net present value of a cash flow series mid year calc"""
    npv = 0
    for i, cf in enumerate(cash_flows):
        year = start_year + i
        npv += cf / ((1 + discount_rate) ** (year + .5))
    return npv


def get_construction_schedule(construction_years: float) -> List[Tuple[float, float]]:
    """Returns construction cash flow schedule. Total fractions always sum to 1.0."""
    if construction_years <= 1.0:
        return [(0.0, 1.0)]
    elif construction_years <= 2.0:
        return [(0.0, 0.4), (1.0, 0.6)]
    elif construction_years <= 3.0:
        return [(0.0, 0.3), (1.0, 0.4), (2.0, 0.3)]
    else:
        full_years = int(construction_years)
        final_fraction = construction_years - full_years
        if final_fraction > 0:
            fraction_per_year = 1.0 / construction_years
            schedule = []
            for year in range(full_years):
                schedule.append((float(year), fraction_per_year))
            schedule.append((float(full_years), fraction_per_year * final_fraction))
        else:
            fraction_per_year = 1.0 / construction_years
            schedule = [(float(year), fraction_per_year) for year in range(full_years)]
        return schedule


def get_operations_start_info(construction_years: float) -> Tuple[int, float]:
    """Calculate when operations start and partial year fraction."""
    completion_fraction = construction_years - int(construction_years)
    first_year_fraction = 1.0 - completion_fraction if completion_fraction > 0 else 1.0
    return int(np.ceil(construction_years)), first_year_fraction


def calculate_gas_system_lcoe(
    plant_config,
    gas_price: float,
    facility_load: FacilityLoad,
    config: Config,
    construction_years: Optional[float] = None
) -> LCOEResult:
    """
    Calculate LCOE for a natural gas + diesel backup system.
    """
    from degradation_model import get_gas_degradation_factors

    if construction_years is None:
        construction_years = plant_config.construction_timeline['construction_years']

    power_analyzer = PowerFlowAnalyzer(config)
    mult = power_analyzer.get_bus_architecture_multipliers("natural_gas")

    total_bus_demand_mwh = (
        facility_load.annual_it_energy_mwh * mult['bus_to_it'] +
        facility_load.annual_cooling_energy_mwh * mult['bus_to_cooling']
    )
    required_at_generator_mwh = total_bus_demand_mwh * mult['grid_to_bus']
    required_at_datacenter_mwh = facility_load.annual_facility_energy_mwh

    diesel_design = getattr(plant_config, "diesel_design", None)
    diesel_capex = diesel_design.total_capex if diesel_design else 0.0
    diesel_fixed_om = diesel_design.annual_fixed_om if diesel_design else 0.0

    # CAPEX NPV
    total_capex = (plant_config.total_capacity_mw * 1000 * plant_config.capex_per_kw) + diesel_capex
    capex_schedule = get_construction_schedule(construction_years)

    capex_npv = 0.0
    for year, fraction in capex_schedule:
        discount_year = year + 0.5
        capex_npv += (total_capex * fraction) / ((1 + config.financial.discount_rate) ** discount_year)

    # OPEX and Energy Flows
    opex_flows = [0.0] * config.financial.evaluation_years
    energy_flows = [0.0] * config.financial.evaluation_years

    ops_start_year, first_year_fraction = get_operations_start_info(construction_years)

    for year in range(ops_start_year, config.financial.evaluation_years):
        operational_year = year - ops_start_year

        cap_factor, eff_factor = get_gas_degradation_factors(
            operational_year, plant_config.turbine_class, config
        )

        degraded_capacity_mw = plant_config.total_capacity_mw * cap_factor
        ng_possible_mwh = degraded_capacity_mw * plant_config.availability * HOURS_PER_YEAR
        ng_generation_mwh = min(ng_possible_mwh, required_at_generator_mwh)

        shortfall_mwh = max(0.0, required_at_generator_mwh - ng_generation_mwh)
        planned_maint_mwh = getattr(plant_config, "eue_maint_mwh", 0.0)
        diesel_capacity_mw = plant_config.diesel_design.total_capacity_mw if plant_config.diesel_design else 0.0
        testing_mwh = diesel_capacity_mw * config.costs.diesel_test_hours_per_year
        diesel_floor_mwh = testing_mwh + planned_maint_mwh
        diesel_generation_mwh = max(shortfall_mwh, diesel_floor_mwh)

        heat_rate_btu_per_kwh = 3412 / (plant_config.efficiency * eff_factor)
        gas_fuel_cost = ng_generation_mwh * (heat_rate_btu_per_kwh / 1000) * gas_price
        diesel_fuel_cost = diesel_generation_mwh * (config.costs.diesel_eff / 1000) * config.costs.diesel_cost

        gas_var_om = ng_generation_mwh * plant_config.var_om_per_mwh
        diesel_var_om = diesel_generation_mwh * config.costs.diesel_var_om_per_mwh
        total_fixed_om = (plant_config.total_capacity_mw * 1000 * plant_config.fixed_om_per_kw_yr) + diesel_fixed_om

        year_fraction = first_year_fraction if (year == ops_start_year and first_year_fraction < 1.0) else 1.0

        opex_flows[year] = (gas_fuel_cost + diesel_fuel_cost +
                            gas_var_om + diesel_var_om +
                            total_fixed_om) * year_fraction
        energy_flows[year] = required_at_datacenter_mwh * year_fraction

    opex_npv = calculate_npv(opex_flows, config.financial.discount_rate)
    energy_npv = calculate_npv(energy_flows, config.financial.discount_rate)

    total_cost_npv = capex_npv + opex_npv
    lcoe = (total_cost_npv / energy_npv if energy_npv > 0 else float('inf')) / 1000

    return LCOEResult(
        system_type="natural_gas",
        capex_npv=capex_npv,
        opex_npv=opex_npv,
        energy_npv=energy_npv,
        lcoe=lcoe,
        construction_years=construction_years,
        nameplate_capacity_mw=plant_config.total_capacity_mw
    )
