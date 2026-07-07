from __future__ import annotations

import math
from typing import Any

from core.flight_schema import get_field
from core.physics_utils import (
    ModelParams,
    calculate_altitude,
    calculate_speed,
)
from core.predictors.base import Predictor


class ApogeePredict1D(Predictor):
    required_columns = ("static_pressure", "total_pressure")
    produced_fields = ("position_z", "velocity_z", "predicted_apogee")

    def __init__(self, params: ModelParams | None = None) -> None:
        self._params = params or ModelParams()

    def reset(self) -> None:
        pass

    def predict(self, state: dict[str, Any]) -> dict[str, Any]:
        static_pressure = get_field(state, "static_pressure", default=0.0)
        total_pressure = get_field(state, "total_pressure", default=0.0)
        diff_pressure = max(total_pressure - static_pressure, 0.0)

        position_z = calculate_altitude(static_pressure, self._params)
        velocity_z = calculate_speed(diff_pressure, position_z, self._params)

        return {
            **state,
            "position_z": position_z,
            "velocity_z": velocity_z,
            "predicted_apogee": self._predict_apogee(position_z, velocity_z, diff_pressure),
        }

    def _predict_apogee(self, position_z: float, velocity_z: float, diff_pressure: float) -> float:
        drag_force = (
            diff_pressure
            * self._params.default_drag_coefficient
            * self._params.default_cross_section
        )
        mass = self._params.default_mass
        weight = mass * self._params.g

        if drag_force <= 0.0:
            return position_z + (mass * velocity_z**2) / (2.0 * weight)

        return position_z + (mass * velocity_z**2 * math.log(1.0 + (drag_force / weight))) / (
            2.0 * drag_force
        )
