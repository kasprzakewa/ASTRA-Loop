from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from core.controllers.base import Controller
from core.controllers.pd_controller import PDController
from core.data_loader import DataLoader
from core.filters.base import Filter
from core.flight_schema import get_field, lateral_velocity_sq
from core.physics_utils import control_to_servo_angle, step_coast
from core.predictors.base import Predictor

@dataclass
class SimulationResult:
    time: list[float] = field(default_factory=list)
    logged_altitude: list[float] = field(default_factory=list)
    logged_true_altitude: list[float] = field(default_factory=list)
    logged_velocity: list[float] = field(default_factory=list)
    logged_predicted_apogee: list[float] = field(default_factory=list)
    logged_control_signal: list[float] = field(default_factory=list)
    logged_servo_angle: list[float] = field(default_factory=list)
    filtered_states: list[dict[str, Any]] = field(default_factory=list)
    execution_times_ms: list[float] = field(default_factory=list)


def find_burnout_index(velocities: list[float]) -> int | None:
    vel_arr = np.array(velocities, dtype=float)
    valid_vel = ~np.isnan(vel_arr)
    if not valid_vel.any():
        return None

    start = 0
    for index, velocity in enumerate(vel_arr):
        if valid_vel[index] and velocity > 0.0:
            start = index
            break
    else:
        return None

    segment = vel_arr[start:]
    valid_segment = ~np.isnan(segment)
    if not valid_segment.any():
        return None

    peak_offset = int(np.argmax(segment))
    peak_velocity = segment[peak_offset]
    if peak_velocity <= 0.0:
        return None

    return start + peak_offset


def can_detect_burnout(velocities: list[float]) -> bool:
    return find_burnout_index(velocities) is not None


def find_apogee_index(velocities: list[float], altitudes: list[float]) -> int:
    vel_arr = np.array(velocities, dtype=float)
    valid_vel = ~np.isnan(vel_arr)
    has_signed_velocity = valid_vel.any() and np.any(vel_arr[valid_vel] < 0.0)

    if has_signed_velocity:
        was_airborne = False
        for index, velocity in enumerate(vel_arr):
            if not valid_vel[index]:
                continue
            if velocity > 0.0:
                was_airborne = True
            elif was_airborne and velocity <= 0.0:
                return index

    alt_arr = np.array(altitudes, dtype=float)
    valid_alt = ~np.isnan(alt_arr)
    if valid_alt.any():
        return int(np.where(valid_alt)[0][np.argmax(alt_arr[valid_alt])])

    return max(len(altitudes) - 1, 0)


def _slice_result(result: SimulationResult, start: int, end: int) -> SimulationResult:
    return SimulationResult(
        time=result.time[start:end],
        logged_altitude=result.logged_altitude[start:end],
        logged_true_altitude=result.logged_true_altitude[start:end],
        logged_velocity=result.logged_velocity[start:end],
        logged_predicted_apogee=result.logged_predicted_apogee[start:end],
        logged_control_signal=result.logged_control_signal[start:end],
        logged_servo_angle=result.logged_servo_angle[start:end],
        filtered_states=result.filtered_states[start:end],
        execution_times_ms=result.execution_times_ms[start:end],
    )


def slice_flight_window(
    result: SimulationResult,
    *,
    from_burnout: bool = False,
    until_apogee: bool = False,
) -> SimulationResult:
    start = 0
    if from_burnout:
        burnout_index = find_burnout_index(result.logged_velocity)
        if burnout_index is not None:
            start = burnout_index

    end = len(result.time)
    if until_apogee:
        end = find_apogee_index(result.logged_velocity, result.logged_altitude) + 1

    if start >= end:
        return _slice_result(result, start, start + 1)
    return _slice_result(result, start, end)


def slice_to_apogee(result: SimulationResult) -> SimulationResult:
    return slice_flight_window(result, until_apogee=True)


def report_first_brake_open(result: SimulationResult, *, eps: float = 1e-6) -> None:
    """Print vz at the first non-zero control signal (first brake open)."""
    for i, u in enumerate(result.logged_control_signal):
        if abs(u) > eps:
            t = result.time[i] if i < len(result.time) else float("nan")
            vz = result.logged_velocity[i] if i < len(result.logged_velocity) else float("nan")
            z = result.logged_altitude[i] if i < len(result.logged_altitude) else float("nan")
            print(
                f"First brake open: t={t:.3f} s, vz={vz:.2f} m/s, z={z:.1f} m, u={u:.4f}"
            )
            return
    print("First brake open: never (control_u stayed 0)")


class SimulationEngine:
    def __init__(
        self,
        data_loader: DataLoader,
        filter_algo: Filter,
        predictor: Predictor,
        controller: Controller,
        max_coast_steps: int = 100_000,
        wind_speed: float = 0.0,
        gust_strength: float = 0.0,
        gust_alpha: float = 0.08,
        wind_seed: int | None = None,
        plant_mass_scale: float = 1.0,
        plant_cd_scale: float = 1.0,
    ) -> None:
        self._loader = data_loader
        self._filter = filter_algo
        self._predictor = predictor
        self._controller = controller
        self._max_coast_steps = max_coast_steps
        self._wind_speed = wind_speed
        self._gust_strength = abs(gust_strength)
        self._gust_alpha = max(0.0, min(1.0, gust_alpha))
        self._wind_rng = random.Random(wind_seed)
        self._gust_vertical = 0.0
        self._plant_mass_scale = plant_mass_scale if plant_mass_scale > 0.0 else 1.0
        self._plant_cd_scale = plant_cd_scale if plant_cd_scale > 0.0 else 1.0

    def _disturbance_now(self) -> tuple[float, float]:
        """Return (horizontal_wind, vertical_gust) for the plant only."""
        if self._gust_strength <= 0.0:
            return self._wind_speed, 0.0
        sample = self._wind_rng.uniform(-self._gust_strength, self._gust_strength)
        self._gust_vertical = (
            (1.0 - self._gust_alpha) * self._gust_vertical + self._gust_alpha * sample
        )
        return self._wind_speed, self._gust_vertical

    def run(self, *, report_brake_stats: bool = True) -> SimulationResult:
        self._filter.reset()
        self._predictor.reset()
        self._controller.reset()

        rows = list(self._loader.iter_rows())
        if not rows:
            return SimulationResult()

        velocities = [get_field(row, "velocity_z") for row in rows]
        burnout_idx = find_burnout_index(velocities)
        closed_loop = (
            burnout_idx is not None
            and getattr(self._predictor, "supports_closed_loop_coast", False)
            and isinstance(self._controller, PDController)
        )

        result = SimulationResult()
        u = 0.0

        end = burnout_idx if closed_loop else len(rows) - 1
        for row in rows[: end + 1]:
            u = self._step_csv(row, result)

        if closed_loop:
            self._step_coast(result, u)

        if report_brake_stats:
            report_first_brake_open(result)
        return result

    def _target(self, prediction: dict[str, Any]) -> float:
        controller_target = getattr(self._controller, "target_apogee", None)
        if controller_target is not None:
            return float(controller_target)
        predicted = get_field(prediction, "predicted_apogee")
        if not np.isnan(predicted):
            return predicted
        return 0.0

    def _control_step(
        self, measurement: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], float]:
        filtered = self._filter.update(measurement)
        prediction = self._predictor.predict({**filtered, "control_signal": 0.0})
        u = float(self._controller.compute({**filtered, **prediction}, self._target(prediction)))
        max_deploy = getattr(self._controller, "max_deploy_speed", None)
        if max_deploy is not None:
            vz = get_field(measurement, "velocity_z")
            if not math.isnan(vz) and vz > float(max_deploy):
                u = 0.0
        return filtered, prediction, u

    def _log(
        self,
        result: SimulationResult,
        *,
        t: float,
        altitude: float,
        true_altitude: float,
        velocity: float,
        prediction: dict[str, Any],
        u: float,
        filtered: dict[str, Any],
        elapsed_ms: float,
    ) -> None:
        result.time.append(t)
        result.logged_altitude.append(altitude)
        result.logged_true_altitude.append(true_altitude)
        result.logged_velocity.append(velocity)
        result.logged_predicted_apogee.append(get_field(prediction, "predicted_apogee"))
        result.logged_control_signal.append(u)
        result.logged_servo_angle.append(control_to_servo_angle(u))
        result.filtered_states.append(filtered)
        result.execution_times_ms.append(elapsed_ms)

    def _step_csv(self, row: dict[str, Any], result: SimulationResult) -> float:
        t0 = time.perf_counter()
        filtered, prediction, u = self._control_step(row)
        true_z = get_field(row, "position_z")
        true_vz = get_field(row, "velocity_z")
        self._log(
            result,
            t=get_field(row, "time", default=0.0),
            altitude=get_field(prediction, "position_z", default=true_z),
            true_altitude=true_z,
            velocity=get_field(prediction, "velocity_z", default=true_vz),
            prediction=prediction,
            u=u,
            filtered=filtered,
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )
        return u

    def _step_coast(self, result: SimulationResult, u: float) -> None:
        params, dt, solver = self._predictor.coast_config()
        plant_params = replace(
            params,
            default_mass=params.default_mass * self._plant_mass_scale,
            default_drag_coefficient=params.default_drag_coefficient * self._plant_cd_scale,
        )
        z = result.logged_altitude[-1]
        vz = result.logged_velocity[-1]
        t = result.time[-1]
        v_lat_sq = lateral_velocity_sq(result.filtered_states[-1])
        if math.isnan(v_lat_sq):
            v_lat_sq = 0.0
        v_h = math.sqrt(max(v_lat_sq, 0.0))

        for _ in range(self._max_coast_steps):
            if vz <= 0.0:
                break

            t0 = time.perf_counter()
            wind_h, wind_v = self._disturbance_now()
            z, vz, v_h = step_coast(
                z,
                vz,
                v_h,
                plant_params,
                dt,
                servo_angle=control_to_servo_angle(u),
                solver=solver,
                wind_speed=wind_h,
                wind_vertical=wind_v,
            )
            t += dt

            measurement = {
                "time": t,
                "position_z": z,
                "velocity_z": vz,
                "velocity_lateral": abs(v_h),
            }
            filtered, prediction, u = self._control_step(measurement)
            self._log(
                result,
                t=t,
                altitude=z,
                true_altitude=z,
                velocity=vz,
                prediction=prediction,
                u=u,
                filtered=filtered,
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )
