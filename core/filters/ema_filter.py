from __future__ import annotations

from typing import Any

from core.filters.base import Filter


class EMAFilter(Filter):
    def __init__(self, alpha: float = 0.3) -> None:
        self._alpha = alpha
        self._state: dict[str, float] = {}

    def reset(self) -> None:
        self._state.clear()

    def update(self, measurement: dict[str, Any]) -> dict[str, Any]:
        output = dict(measurement)
        for key, value in measurement.items():
            if not isinstance(value, (int, float)) or value != value:
                continue
            if key not in self._state:
                self._state[key] = float(value)
            else:
                self._state[key] = self._alpha * float(value) + (1.0 - self._alpha) * self._state[key]
            output[key] = self._state[key]
        return output
