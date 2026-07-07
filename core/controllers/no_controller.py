from __future__ import annotations

from typing import Any

from core.controllers.base import Controller


class NoController(Controller):
    def reset(self) -> None:
        pass

    def compute(self, state: dict[str, Any], setpoint: float) -> float:
        return 0.0
