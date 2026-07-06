from __future__ import annotations

import math
from typing import Any

from core.predictors.base import Predictor

GRAVITY = 9.81


class ApogeePredict3D(Predictor):
    def reset(self) -> None:
        pass

    def predict(self, state: dict[str, Any]) -> dict[str, Any]:
        altitude = float(state.get("position_z", state.get("altitude", 0.0)) or 0.0)
        velocity_z = float(state.get("velocity_z", state.get("velocity", 0.0)) or 0.0)

        acceleration_z = state.get("acceleration_z")
        if acceleration_z is None or (isinstance(acceleration_z, float) and math.isnan(acceleration_z)):
            acceleration_z = -GRAVITY
        acceleration_z = float(acceleration_z)

        if acceleration_z >= 0:
            predicted_apogee = altitude
            time_to_apogee = math.inf
        else:
            predicted_apogee = altitude - (velocity_z**2) / (2.0 * acceleration_z)
            time_to_apogee = -velocity_z / acceleration_z

        return {
            **state,
            "predicted_apogee": predicted_apogee,
            "time_to_apogee": time_to_apogee,
        }
