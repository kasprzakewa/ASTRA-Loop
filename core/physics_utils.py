from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

CoastSolver = Literal["euler", "rk4"]


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


def _coast_derivatives(
    z: float,
    vz: float,
    v_lat_sq: float,
    params: ModelParams,
) -> tuple[float, float, float]:
    """Return (dz/dt, dvz/dt, d(v_lat_sq)/dt) for coast phase with quadratic drag."""
    speed = math.sqrt(max(v_lat_sq, 0.0) + vz * vz)
    rho = calculate_air_density(z, params)
    k = (
        -0.5
        / params.default_mass
        * rho
        * params.default_drag_coefficient
        * params.default_cross_section
        * speed
    )
    dz_dt = vz
    dvz_dt = -params.g + k * vz
    dv_lat_sq_dt = 2.0 * k * v_lat_sq
    return dz_dt, dvz_dt, dv_lat_sq_dt


def propagate_coast_to_apogee_euler(
    z: float,
    vz: float,
    v_lat_sq: float,
    params: ModelParams,
    dt: float = 0.01,
    max_steps: int = 100_000,
) -> tuple[float, float]:
    """Integrate coast-phase motion with forward Euler until v_z <= 0."""
    if vz <= 0.0:
        return z, 0.0

    steps = 0
    while vz > 0.0 and steps < max_steps:
        dz_dt, dvz_dt, dv_lat_sq_dt = _coast_derivatives(z, vz, v_lat_sq, params)
        z += dz_dt * dt
        vz += dvz_dt * dt
        v_lat_sq = max(v_lat_sq + dv_lat_sq_dt * dt, 0.0)
        steps += 1

    return z, steps * dt


def propagate_coast_to_apogee_rk4(
    z: float,
    vz: float,
    v_lat_sq: float,
    params: ModelParams,
    dt: float = 0.01,
    max_steps: int = 100_000,
) -> tuple[float, float]:
    """Integrate coast-phase motion with classic RK4 until v_z <= 0."""
    if vz <= 0.0:
        return z, 0.0

    steps = 0
    while vz > 0.0 and steps < max_steps:
        k1z, k1vz, k1vls = _coast_derivatives(z, vz, v_lat_sq, params)
        k2z, k2vz, k2vls = _coast_derivatives(
            z + 0.5 * dt * k1z,
            vz + 0.5 * dt * k1vz,
            max(v_lat_sq + 0.5 * dt * k1vls, 0.0),
            params,
        )
        k3z, k3vz, k3vls = _coast_derivatives(
            z + 0.5 * dt * k2z,
            vz + 0.5 * dt * k2vz,
            max(v_lat_sq + 0.5 * dt * k2vls, 0.0),
            params,
        )
        k4z, k4vz, k4vls = _coast_derivatives(
            z + dt * k3z,
            vz + dt * k3vz,
            max(v_lat_sq + dt * k3vls, 0.0),
            params,
        )

        z += (dt / 6.0) * (k1z + 2.0 * k2z + 2.0 * k3z + k4z)
        vz += (dt / 6.0) * (k1vz + 2.0 * k2vz + 2.0 * k3vz + k4vz)
        v_lat_sq = max(
            v_lat_sq + (dt / 6.0) * (k1vls + 2.0 * k2vls + 2.0 * k3vls + k4vls),
            0.0,
        )
        steps += 1

    return z, steps * dt


def propagate_coast_to_apogee(
    z: float,
    vz: float,
    v_lat_sq: float,
    params: ModelParams,
    *,
    solver: CoastSolver = "euler",
    dt: float = 0.01,
    max_steps: int = 100_000,
) -> tuple[float, float]:
    if solver == "rk4":
        return propagate_coast_to_apogee_rk4(z, vz, v_lat_sq, params, dt=dt, max_steps=max_steps)
    return propagate_coast_to_apogee_euler(z, vz, v_lat_sq, params, dt=dt, max_steps=max_steps)
