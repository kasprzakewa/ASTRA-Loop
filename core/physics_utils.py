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


def propagate_coast_to_apogee_euler(
    z: float,
    vz: float,
    v_lat_sq: float,
    params: ModelParams,
    dt: float = 0.01,
    max_steps: int = 100_000,
) -> tuple[float, float]:
    """Integrate coast-phase motion until v_z <= 0. Returns (z_apogee, time_to_apogee)."""
    if vz <= 0.0:
        return z, 0.0

    mass = params.default_mass
    drag_coefficient = params.default_drag_coefficient
    cross_section = params.default_cross_section
    gravity = params.g

    steps = 0
    while vz > 0.0 and steps < max_steps:
        speed = math.sqrt(v_lat_sq + vz * vz)
        rho = calculate_air_density(z, params)
        k = -0.5 / mass * rho * drag_coefficient * cross_section * speed

        z += vz * dt
        v_lat_sq += 2.0 * k * v_lat_sq * dt
        v_lat_sq = max(v_lat_sq, 0.0)
        vz += (-gravity + k * vz) * dt
        steps += 1

    return z, steps * dt
