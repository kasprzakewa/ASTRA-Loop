from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelParams:
    reference_pressure: float = 101325.0
    reference_air_density: float = 1.225
    scale_height: float = 44330.0
    baro_exponent: float = 0.1903
    density_exponent: float = 4.256
    g: float = 9.80665
    default_cross_section: float = 0.01
    default_mass: float = 15.0
    default_drag_coefficient: float = 0.45


def calculate_altitude(pressure: float, params: ModelParams) -> float:
    if pressure <= 0.0:
        return 0.0
    ratio = pressure / params.reference_pressure
    return params.scale_height * (1.0 - ratio**params.baro_exponent)


def calculate_air_density(altitude: float, params: ModelParams) -> float:
    altitude = max(altitude, 0.0)
    factor = 1.0 - altitude / params.scale_height
    if factor <= 0.0:
        return 0.0
    return params.reference_air_density * (factor**params.density_exponent)


def calculate_speed(diff_pressure: float, altitude: float, params: ModelParams) -> float:
    if diff_pressure <= 0.0:
        return 0.0
    rho = calculate_air_density(altitude, params)
    if rho <= 0.0:
        return 0.0
    return math.sqrt(2.0 * diff_pressure / rho)
