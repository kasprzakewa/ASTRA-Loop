from __future__ import annotations

from typing import Any

from core.controllers.base import Controller


class PIDController(Controller):
    def __init__(self, kp: float = 1.0, ki: float = 0.0, kd: float = 0.0) -> None:
        self._kp = kp
        self._ki = ki
        self._kd = kd
        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time: float | None = None

    def reset(self) -> None:
        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time = None

    def compute(self, state: dict[str, Any], setpoint: float) -> float:
        measured = float(state.get("predicted_apogee", state.get("altitude", 0.0)) or 0.0)
        error = setpoint - measured
        current_time = float(state.get("time", 0.0))

        dt = 0.01 if self._prev_time is None else max(current_time - self._prev_time, 1e-6)
        self._integral += error * dt
        derivative = (error - self._prev_error) / dt

        output = self._kp * error + self._ki * self._integral + self._kd * derivative
        output = max(0.0, min(1.0, output))

        self._prev_error = error
        self._prev_time = current_time
        return output
