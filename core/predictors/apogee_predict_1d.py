from __future__ import annotations

import math
from typing import Any

from core.physics_utils import (
    ModelParams,
    calculate_air_density,
    calculate_altitude,
    calculate_speed,
)
from core.predictors.base import Predictor


class ApogeePredict1D(Predictor):
    def __init__(self, params: ModelParams | None = None) -> None:
        self._params = params or ModelParams()

    def reset(self) -> None:
        pass

    def predict_apogee(self, state: dict[str, Any]) -> float:
        static_pressure = self._pressure(state, "static_pressure")
        diff_pressure = self._diff_pressure(state)

        altitude = calculate_altitude(static_pressure, self._params)
        speed = calculate_speed(diff_pressure, altitude, self._params)
        rho = calculate_air_density(altitude, self._params)
        dynamic_pressure = 0.5 * rho * speed**2

        drag_force = (
            dynamic_pressure
            * self._params.default_drag_coefficient
            * self._params.default_cross_section
        )
        mass = self._params.default_mass
        weight = mass * self._params.g

        if drag_force <= 0.0:
            return altitude + (mass * speed**2) / (2.0 * weight)

        return altitude + (mass * speed**2 * math.log(1.0 + (drag_force / weight))) / (2.0 * drag_force)

    def predict(self, state: dict[str, Any]) -> dict[str, Any]:
        static_pressure = self._pressure(state, "static_pressure")
        diff_pressure = self._diff_pressure(state)
        altitude = calculate_altitude(static_pressure, self._params)
        speed = calculate_speed(diff_pressure, altitude, self._params)

        return {
            **state,
            "altitude": altitude,
            "velocity": speed,
            "diff_pressure": diff_pressure,
            "predicted_apogee": self.predict_apogee(state),
        }

    def _diff_pressure(self, state: dict[str, Any]) -> float:
        static_pressure = self._pressure(state, "static_pressure")
        total_pressure = self._pressure(state, "total_pressure")
        return max(total_pressure - static_pressure, 0.0)

    @staticmethod
    def _pressure(state: dict[str, Any], key: str) -> float:
        value = state.get(key, 0.0)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return 0.0 if numeric != numeric else numeric
