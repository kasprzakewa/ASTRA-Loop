from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.controllers.base import Controller
from core.data_loader import DataLoader
from core.filters.base import Filter
from core.flight_schema import get_field
from core.predictors.base import Predictor


@dataclass
class SimulationResult:
    time: list[float] = field(default_factory=list)
    logged_altitude: list[float] = field(default_factory=list)
    logged_true_altitude: list[float] = field(default_factory=list)
    logged_velocity: list[float] = field(default_factory=list)
    logged_predicted_apogee: list[float] = field(default_factory=list)
    logged_control_signal: list[float] = field(default_factory=list)
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


class SimulationEngine:
    def __init__(
        self,
        data_loader: DataLoader,
        filter_algo: Filter,
        predictor: Predictor,
        controller: Controller,
        apogee_setpoint: float | None = None,
    ) -> None:
        self._loader = data_loader
        self._filter = filter_algo
        self._predictor = predictor
        self._controller = controller
        self._apogee_setpoint = apogee_setpoint

    def run(self) -> SimulationResult:
        self._filter.reset()
        self._predictor.reset()
        self._controller.reset()

        result = SimulationResult()
        rows = self._loader.iter_rows()

        for row in rows:
            step_start = time.perf_counter()

            filtered = self._filter.update(row)
            prediction = self._predictor.predict(filtered)
            control_state = {**filtered, **prediction}
            setpoint = self._resolve_setpoint(prediction)
            control = self._controller.compute(control_state, setpoint)

            elapsed_ms = (time.perf_counter() - step_start) * 1000.0

            true_position_z = get_field(row, "position_z")
            computed_position_z = get_field(prediction, "position_z", default=true_position_z)
            true_velocity_z = get_field(row, "velocity_z")
            computed_velocity_z = get_field(prediction, "velocity_z", default=true_velocity_z)

            result.time.append(get_field(row, "time", default=0.0))
            result.logged_altitude.append(computed_position_z)
            result.logged_true_altitude.append(true_position_z)
            result.logged_velocity.append(computed_velocity_z)
            result.logged_predicted_apogee.append(get_field(prediction, "predicted_apogee"))
            result.logged_control_signal.append(float(control))
            result.filtered_states.append(filtered)
            result.execution_times_ms.append(elapsed_ms)

        return result

    def _resolve_setpoint(self, prediction: dict[str, Any]) -> float:
        if self._apogee_setpoint is not None:
            return self._apogee_setpoint
        predicted = get_field(prediction, "predicted_apogee")
        if not np.isnan(predicted):
            return predicted
        return 0.0
