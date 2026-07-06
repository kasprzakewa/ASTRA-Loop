from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.controllers.base import Controller
from core.data_loader import DataLoader
from core.filters.base import Filter
from core.predictors.base import Predictor


@dataclass
class SimulationResult:
    time: list[float] = field(default_factory=list)
    logged_altitude: list[float] = field(default_factory=list)
    logged_true_altitude: list[float] = field(default_factory=list)
    logged_velocity: list[float] = field(default_factory=list)
    logged_predicted_apogee: list[float] = field(default_factory=list)
    logged_true_apogee: list[float] = field(default_factory=list)
    logged_control_signal: list[float] = field(default_factory=list)
    filtered_states: list[dict[str, Any]] = field(default_factory=list)
    execution_times_ms: list[float] = field(default_factory=list)


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


def slice_to_apogee(result: SimulationResult) -> SimulationResult:
    end = find_apogee_index(result.logged_velocity, result.logged_altitude) + 1
    return SimulationResult(
        time=result.time[:end],
        logged_altitude=result.logged_altitude[:end],
        logged_true_altitude=result.logged_true_altitude[:end],
        logged_velocity=result.logged_velocity[:end],
        logged_predicted_apogee=result.logged_predicted_apogee[:end],
        logged_true_apogee=result.logged_true_apogee[:end],
        logged_control_signal=result.logged_control_signal[:end],
        filtered_states=result.filtered_states[:end],
        execution_times_ms=result.execution_times_ms[:end],
    )


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
            setpoint = self._resolve_setpoint(row, prediction)
            control = self._controller.compute(control_state, setpoint)

            elapsed_ms = (time.perf_counter() - step_start) * 1000.0

            result.time.append(float(row.get("time", 0.0)))

            computed_altitude = self._safe_float(prediction.get("altitude", filtered.get("altitude")))
            true_altitude = self._safe_float(row.get("altitude"))
            if self._is_nan(true_altitude):
                true_altitude = computed_altitude

            result.logged_altitude.append(computed_altitude)
            result.logged_true_altitude.append(true_altitude)
            result.logged_velocity.append(self._safe_float(prediction.get("velocity", row.get("velocity"))))
            result.logged_predicted_apogee.append(self._safe_float(prediction.get("predicted_apogee")))
            result.logged_true_apogee.append(self._safe_float(row.get("true_apogee")))
            result.logged_control_signal.append(float(control))
            result.filtered_states.append(filtered)
            result.execution_times_ms.append(elapsed_ms)

        return result

    def _resolve_setpoint(self, row: dict[str, Any], prediction: dict[str, Any]) -> float:
        if self._apogee_setpoint is not None:
            return self._apogee_setpoint
        if "true_apogee" in row and not self._is_nan(row["true_apogee"]):
            return float(row["true_apogee"])
        predicted = prediction.get("predicted_apogee")
        if predicted is not None and not self._is_nan(predicted):
            return float(predicted)
        return 0.0

    @staticmethod
    def _safe_float(value: Any) -> float:
        if value is None:
            return float("nan")
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("nan")

    @staticmethod
    def _is_nan(value: Any) -> bool:
        try:
            return value != value
        except TypeError:
            return True
