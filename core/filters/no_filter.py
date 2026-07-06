from __future__ import annotations

from typing import Any

from core.filters.base import Filter


class NoFilter(Filter):
    def reset(self) -> None:
        pass

    def update(self, measurement: dict[str, Any]) -> dict[str, Any]:
        return dict(measurement)
