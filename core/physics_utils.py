from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

CoastSolver = Literal["euler", "rk4"]

SERVO_ANGLE_SAFE_DEG = 0.0  # brakes fully retracted
SERVO_ANGLE_OPEN_DEG = 60.0  # brakes fully deployed
BODY_DIAMETER_M = 0.126
BODY_CROSS_SECTION_M2 = math.pi * (BODY_DIAMETER_M / 2.0) ** 2


@dataclass(frozen=True)
class ModelParams:
    reference_pressure: float = 101325.0
    reference_air_density: float = 1.225
    reference_temperature: float = 288.15
    scale_height: float = 44330.0
    baro_exponent: float = 0.1903
    density_exponent: float = 4.256
    g: float = 9.80665
    default_cross_section: float = BODY_CROSS_SECTION_M2
    default_mass: float = 10.453
    default_drag_coefficient: float = 0.42
    brake_drag_coefficient: float = 1.2
    temperature_gradient: float = -0.0065


def servo_angle_safe_deg() -> float:
    return SERVO_ANGLE_SAFE_DEG


def control_to_servo_angle(u: float) -> float:
    try:
        value = float(u)
    except (TypeError, ValueError):
        return servo_angle_safe_deg()
    if value != value:
        return servo_angle_safe_deg()
    u_clamped = max(0.0, min(1.0, value))
    return SERVO_ANGLE_SAFE_DEG + u_clamped * (SERVO_ANGLE_OPEN_DEG - SERVO_ANGLE_SAFE_DEG)


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


def calculate_temperature(altitude: float, params: ModelParams) -> float:
    altitude = max(altitude, 0.0)
    return params.reference_temperature + params.temperature_gradient * altitude


def calculate_speed(diff_pressure: float, altitude: float, params: ModelParams) -> float:
    if diff_pressure <= 0.0:
        return 0.0
    rho = calculate_air_density(altitude, params)
    if rho <= 0.0:
        return 0.0
    return math.sqrt(2.0 * diff_pressure / rho)


def calculate_mach(speed: float, altitude: float, params: ModelParams) -> float:
    temp = calculate_temperature(altitude, params)
    local_sound_speed = 20.05 * math.sqrt(temp)
    return speed / local_sound_speed


def calculate_drag_coefficient(speed: float, altitude: float, params: ModelParams) -> float:
    mach = calculate_mach(speed, altitude, params)
    if mach <= 0.0:
        return 0.0
    mach_sq = min(mach * mach, 0.99)
    return params.default_drag_coefficient / math.sqrt(1.0 - mach_sq)


def calculate_brake_area(servo_angle: float) -> float:
    # p(α) = π*((63 + α/4)² - 3969) mm²; α=0 hidden, α=60 fully open
    radius_mm = 63.0 + float(servo_angle) / 4.0
    brake_cross_section_mm2 = math.pi * (radius_mm * radius_mm - 3969.0)
    return max(brake_cross_section_mm2, 0.0) * 1e-6


def calculate_cross_section(params: ModelParams, servo_angle: float) -> float:
    return params.default_cross_section + calculate_brake_area(servo_angle)


def _coast_derivatives(
    z: float,
    vz: float,
    v_h: float,
    params: ModelParams,
    servo_angle: float = 0.0,
    wind_speed: float = 0.0,
    wind_vertical: float = 0.0,
) -> tuple[float, float, float]:
    """Return (dz/dt, dvz/dt, dv_h/dt) for coast with air-relative quadratic drag"""
    v_rel_h = v_h - wind_speed
    v_rel_z = vz - wind_vertical
    speed_air = math.sqrt(v_rel_z * v_rel_z + v_rel_h * v_rel_h)
    cd_body = calculate_drag_coefficient(speed_air, z, params)
    rho = calculate_air_density(z, params)
    a_brake = calculate_brake_area(servo_angle)
    cda = cd_body * params.default_cross_section + params.brake_drag_coefficient * a_brake
    k = -0.5 / params.default_mass * rho * cda * speed_air
    dz_dt = vz
    dvz_dt = -params.g + k * v_rel_z
    dv_h_dt = k * v_rel_h
    return dz_dt, dvz_dt, dv_h_dt


def step_coast(
    z: float,
    vz: float,
    v_h: float,
    params: ModelParams,
    dt: float,
    servo_angle: float = 0.0,
    solver: CoastSolver = "euler",
    wind_speed: float = 0.0,
    wind_vertical: float = 0.0,
) -> tuple[float, float, float]:
    """Advance coast dynamics by one integration step. Returns (z, vz, v_h)"""
    if solver == "rk4":
        k1z, k1vz, k1vh = _coast_derivatives(
            z, vz, v_h, params, servo_angle, wind_speed, wind_vertical
        )
        k2z, k2vz, k2vh = _coast_derivatives(
            z + 0.5 * dt * k1z,
            vz + 0.5 * dt * k1vz,
            v_h + 0.5 * dt * k1vh,
            params,
            servo_angle,
            wind_speed,
            wind_vertical,
        )
        k3z, k3vz, k3vh = _coast_derivatives(
            z + 0.5 * dt * k2z,
            vz + 0.5 * dt * k2vz,
            v_h + 0.5 * dt * k2vh,
            params,
            servo_angle,
            wind_speed,
            wind_vertical,
        )
        k4z, k4vz, k4vh = _coast_derivatives(
            z + dt * k3z,
            vz + dt * k3vz,
            v_h + dt * k3vh,
            params,
            servo_angle,
            wind_speed,
            wind_vertical,
        )
        z += (dt / 6.0) * (k1z + 2.0 * k2z + 2.0 * k3z + k4z)
        vz += (dt / 6.0) * (k1vz + 2.0 * k2vz + 2.0 * k3vz + k4vz)
        v_h += (dt / 6.0) * (k1vh + 2.0 * k2vh + 2.0 * k3vh + k4vh)
        return z, vz, v_h

    dz_dt, dvz_dt, dv_h_dt = _coast_derivatives(
        z, vz, v_h, params, servo_angle, wind_speed, wind_vertical
    )
    z += dz_dt * dt
    vz += dvz_dt * dt
    v_h += dv_h_dt * dt
    return z, vz, v_h


def propagate_coast_to_apogee_euler(
    z: float,
    vz: float,
    v_lat_sq: float,
    params: ModelParams,
    dt: float = 0.01,
    max_steps: int = 100_000,
    servo_angle: float = 0.0,
) -> tuple[float, float]:
    """Integrate coast-phase motion with forward Euler until v_z <= 0"""
    if vz <= 0.0:
        return z, 0.0

    v_h = math.sqrt(max(v_lat_sq, 0.0))
    steps = 0
    while vz > 0.0 and steps < max_steps:
        z, vz, v_h = step_coast(z, vz, v_h, params, dt, servo_angle, "euler")
        steps += 1

    return z, steps * dt


def propagate_coast_to_apogee_rk4(
    z: float,
    vz: float,
    v_lat_sq: float,
    params: ModelParams,
    dt: float = 0.01,
    max_steps: int = 100_000,
    servo_angle: float = 0.0,
) -> tuple[float, float]:
    """Integrate coast-phase motion with classic RK4 until v_z <= 0"""
    if vz <= 0.0:
        return z, 0.0

    v_h = math.sqrt(max(v_lat_sq, 0.0))
    steps = 0
    while vz > 0.0 and steps < max_steps:
        z, vz, v_h = step_coast(z, vz, v_h, params, dt, servo_angle, "rk4")
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
    servo_angle: float = 0.0,
) -> tuple[float, float]:
    if solver == "rk4":
        return propagate_coast_to_apogee_rk4(
            z, vz, v_lat_sq, params, dt=dt, max_steps=max_steps, servo_angle=servo_angle
        )
    return propagate_coast_to_apogee_euler(
        z, vz, v_lat_sq, params, dt=dt, max_steps=max_steps, servo_angle=servo_angle
    )
