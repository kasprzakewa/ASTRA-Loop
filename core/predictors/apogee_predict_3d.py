from __future__ import annotations

import math
from typing import Any

from core.flight_schema import get_field, lateral_velocity_sq
from core.physics_utils import CoastSolver, ModelParams, propagate_coast_to_apogee
from core.predictors.base import Predictor


class ApogeePredict3D(Predictor):
    required_columns = ("position_z", "velocity_z")
    produced_fields = ("predicted_apogee", "time_to_apogee")

    def __init__(
        self,
        params: ModelParams | None = None,
        dt: float = 0.01,
        solver: CoastSolver = "euler",
    ) -> None:
        self._params = params or ModelParams()
        self._dt = dt
        self._solver = solver

    def reset(self) -> None:
        pass

    @classmethod
    def validate_columns(cls, available: set[str]) -> list[str]:
        errors = super().validate_columns(available)
        has_lateral = "velocity_lateral" in available
        has_components = "velocity_x" in available and "velocity_y" in available
        if not has_lateral and not has_components:
            errors.append(
                "Missing column: velocity_lateral (= sqrt(vx²+vy²)) "
                "or both velocity_x and velocity_y"
            )
        return errors

    def predict(self, state: dict[str, Any]) -> dict[str, Any]:
        position_z = get_field(state, "position_z")
        velocity_z = get_field(state, "velocity_z")
        v_lat_sq = lateral_velocity_sq(state)

        if math.isnan(position_z) or math.isnan(velocity_z):
            predicted_apogee = float("nan")
            time_to_apogee = float("nan")
        elif velocity_z <= 0.0:
            predicted_apogee = position_z
            time_to_apogee = 0.0
        else:
            predicted_apogee, time_to_apogee = propagate_coast_to_apogee(
                position_z,
                velocity_z,
                v_lat_sq,
                self._params,
                solver=self._solver,
                dt=self._dt,
            )

        return {
            **state,
            "predicted_apogee": predicted_apogee,
            "time_to_apogee": time_to_apogee,
        }
