from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from core.controllers.base import Controller
from core.flight_schema import get_field


@dataclass(frozen=True)
class PDControllerParams:
    target_apogee: float = 2300.0
    kp: float = 0.08
    kd: float = 0.0005
    # ~400 N envelope: sqrt(2*F/(rho*Cx*A)), rho=1.2, Cx=1.2, A=0.0138
    max_deploy_speed: float = 200.0
    error_deadband: float = 10.0


_DEFAULTS = PDControllerParams()


class PDController(Controller):
    required_columns = ("time",)

    def __init__(
        self,
        target_apogee: float = _DEFAULTS.target_apogee,
        kp: float = _DEFAULTS.kp,
        kd: float = _DEFAULTS.kd,
        max_deploy_speed: float = _DEFAULTS.max_deploy_speed,
        error_deadband: float = _DEFAULTS.error_deadband,
    ) -> None:
        self.target_apogee = target_apogee
        self.kp = kp
        self.kd = kd
        self.max_deploy_speed = max_deploy_speed
        self.error_deadband = error_deadband
        self.reset()

    def reset(self) -> None:
        self.prev_error = 0.0
        self.prev_time: float | None = None

    def compute(self, state: dict[str, Any], setpoint: float) -> float:
        del setpoint
        vz = get_field(state, "velocity_z")
        t = get_field(state, "time")

        if math.isnan(vz) or vz <= 0.0 or vz > self.max_deploy_speed:
            self.prev_time = t
            return 0.0

        predicted = get_field(state, "predicted_apogee")
        error = predicted - self.target_apogee

        if error < self.error_deadband:
            u = 0.0
        elif self.prev_time is None:
            u = max(0.0, min(1.0, self.kp * error))
        else:
            dt = t - self.prev_time
            de = (error - self.prev_error) / dt if dt > 0.0 else 0.0
            u = max(0.0, min(1.0, self.kp * error + self.kd * de))

        self.prev_error = error
        self.prev_time = t
        return u
