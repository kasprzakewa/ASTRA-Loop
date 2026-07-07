from __future__ import annotations

from dataclasses import dataclass
from typing import Type

import numpy as np

from core.controllers.base import Controller
from core.controllers.no_controller import NoController
from core.predictors.base import Predictor
from core.simulation_engine import (
    SimulationResult,
    can_detect_burnout,
    slice_flight_window,
)


@dataclass(frozen=True)
class EvaluationMetrics:
    altitude_rmse: float | None
    altitude_rmse_na_reason: str | None
    apogee_error: float | None
    apogee_error_na_reason: str | None
    max_overshoot: float | None
    max_overshoot_na_reason: str | None
    mean_execution_time_ms: float
    max_execution_time_ms: float


class Evaluator:
    def evaluate(
        self,
        result: SimulationResult,
        *,
        predictor_cls: Type[Predictor],
        controller_cls: Type[Controller],
    ) -> EvaluationMetrics:
        has_reference = self._has_reference_altitude(result.logged_true_altitude)
        predictor_estimates_altitude = "position_z" in predictor_cls.produced_fields

        altitude_rmse: float | None = None
        altitude_rmse_na_reason: str | None = None
        if not has_reference:
            altitude_rmse_na_reason = "no reference position_z"
        elif not predictor_estimates_altitude:
            altitude_rmse_na_reason = "predictor does not estimate altitude"
        else:
            altitude_rmse = self._rmse(result.logged_altitude, result.logged_true_altitude)

        apogee_error: float | None = None
        apogee_error_na_reason: str | None = None
        if not has_reference:
            apogee_error_na_reason = "no reference position_z"
        elif not can_detect_burnout(result.logged_velocity):
            apogee_error_na_reason = "no burnout detected"
        else:
            coast = slice_flight_window(result, from_burnout=True, until_apogee=False)
            apogee_error = self._apogee_error(
                coast.logged_predicted_apogee,
                coast.logged_true_altitude,
            )

        max_overshoot: float | None = None
        max_overshoot_na_reason: str | None = None
        if issubclass(controller_cls, NoController):
            max_overshoot_na_reason = "NoController"
        else:
            max_overshoot = self._max_overshoot(result.logged_control_signal)

        mean_exec, max_exec = self._execution_time_stats(result.execution_times_ms)

        return EvaluationMetrics(
            altitude_rmse=altitude_rmse,
            altitude_rmse_na_reason=altitude_rmse_na_reason,
            apogee_error=apogee_error,
            apogee_error_na_reason=apogee_error_na_reason,
            max_overshoot=max_overshoot,
            max_overshoot_na_reason=max_overshoot_na_reason,
            mean_execution_time_ms=mean_exec,
            max_execution_time_ms=max_exec,
        )

    def _has_reference_altitude(self, altitudes: list[float]) -> bool:
        alt = np.array(altitudes, dtype=float)
        return bool(np.any(~np.isnan(alt)))

    def _rmse(self, predicted: list[float], actual: list[float]) -> float:
        pred = np.array(predicted, dtype=float)
        act = np.array(actual, dtype=float)
        mask = ~(np.isnan(pred) | np.isnan(act))
        if not mask.any():
            return float("nan")
        return float(np.sqrt(np.mean((pred[mask] - act[mask]) ** 2)))

    def _apogee_error(self, predicted: list[float], altitudes: list[float]) -> float:
        pred = np.array(predicted, dtype=float)
        alt = np.array(altitudes, dtype=float)
        valid_pred = pred[~np.isnan(pred)]
        valid_alt = alt[~np.isnan(alt)]
        if valid_pred.size == 0 or valid_alt.size == 0:
            return float("nan")
        reference_apogee = float(np.max(valid_alt))
        return float(abs(np.nanmax(valid_pred) - reference_apogee))

    def _max_overshoot(self, control_signal: list[float]) -> float:
        signal = np.array(control_signal, dtype=float)
        if signal.size == 0:
            return 0.0
        return float(np.max(np.maximum(0.0, signal - 1.0)))

    def _execution_time_stats(self, times_ms: list[float]) -> tuple[float, float]:
        if not times_ms:
            return 0.0, 0.0
        arr = np.array(times_ms, dtype=float)
        return float(np.mean(arr)), float(np.max(arr))
