from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from core.simulation_engine import SimulationResult


@dataclass(frozen=True)
class EvaluationMetrics:
    altitude_rmse: float
    apogee_error: float
    max_overshoot: float
    mean_execution_time_ms: float
    max_execution_time_ms: float


class Evaluator:
    def evaluate(self, result: SimulationResult) -> EvaluationMetrics:
        altitude_rmse = self._rmse(result.logged_altitude, result.logged_true_altitude)
        apogee_error = self._apogee_error(result.logged_predicted_apogee, result.logged_true_apogee)
        max_overshoot = self._max_overshoot(result.logged_control_signal)
        mean_exec, max_exec = self._execution_time_stats(result.execution_times_ms)

        return EvaluationMetrics(
            altitude_rmse=altitude_rmse,
            apogee_error=apogee_error,
            max_overshoot=max_overshoot,
            mean_execution_time_ms=mean_exec,
            max_execution_time_ms=max_exec,
        )

    def summary(self, metrics: EvaluationMetrics) -> dict[str, float]:
        return {
            "altitude_rmse": metrics.altitude_rmse,
            "apogee_error": metrics.apogee_error,
            "max_overshoot": metrics.max_overshoot,
            "mean_execution_time_ms": metrics.mean_execution_time_ms,
            "max_execution_time_ms": metrics.max_execution_time_ms,
        }

    def _rmse(self, predicted: list[float], actual: list[float]) -> float:
        pred = np.array(predicted, dtype=float)
        act = np.array(actual, dtype=float)
        mask = ~(np.isnan(pred) | np.isnan(act))
        if not mask.any():
            return float("nan")
        return float(np.sqrt(np.mean((pred[mask] - act[mask]) ** 2)))

    def _apogee_error(self, predicted: list[float], true_apogee: list[float]) -> float:
        pred = np.array(predicted, dtype=float)
        true = np.array(true_apogee, dtype=float)
        valid_pred = pred[~np.isnan(pred)]
        valid_true = true[~np.isnan(true)]
        if valid_pred.size == 0 or valid_true.size == 0:
            return float("nan")
        return float(abs(np.nanmax(valid_pred) - np.nanmax(valid_true)))

    def _max_overshoot(self, control_signal: list[float]) -> float:
        signal = np.array(control_signal, dtype=float)
        if signal.size == 0:
            return 0.0
        return float(np.nanmax(signal))

    def _execution_time_stats(self, times_ms: list[float]) -> tuple[float, float]:
        if not times_ms:
            return 0.0, 0.0
        arr = np.array(times_ms, dtype=float)
        return float(np.mean(arr)), float(np.max(arr))
