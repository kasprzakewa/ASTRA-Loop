from __future__ import annotations

import math
from typing import Any

CANONICAL_COLUMNS: tuple[str, ...] = (
    "time",
    "position_x",
    "position_y",
    "position_z",
    "velocity_x",
    "velocity_y",
    "velocity_z",
    "acceleration_x",
    "acceleration_y",
    "acceleration_z",
    "velocity_lateral",
    "static_pressure",
    "total_pressure",
)


def get_field(state: dict[str, Any], name: str, *, default: float | None = None) -> float:
    if name not in state:
        return float("nan") if default is None else default

    value = state[name]
    if value is None:
        return float("nan") if default is None else default

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float("nan") if default is None else default

    if numeric != numeric:
        return float("nan") if default is None else default
    return numeric


def lateral_velocity_sq(state: dict[str, Any]) -> float:
    v_lat = get_field(state, "velocity_lateral")
    if not math.isnan(v_lat):
        return v_lat * v_lat

    vx = get_field(state, "velocity_x", default=0.0)
    vy = get_field(state, "velocity_y", default=0.0)
    return vx * vx + vy * vy


def collect_validation_errors(
    available: set[str],
    filter_cls: type,
    predictor_cls: type,
    controller_cls: type,
) -> list[str]:
    errors: list[str] = []
    if "time" not in available:
        errors.append("Missing column: time")

    for cls in (filter_cls, predictor_cls, controller_cls):
        errors.extend(cls.validate_columns(available))
    return errors
