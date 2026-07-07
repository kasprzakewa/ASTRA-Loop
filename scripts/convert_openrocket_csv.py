#!/usr/bin/env python3
"""Convert an OpenRocket simulation CSV export to ASTRA-Loop format."""

from __future__ import annotations

import argparse
import csv
import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Row = dict[str, float]
RowTransform = Callable[[Row], Row]


@dataclass(frozen=True)
class OpenRocketProfile:
    """Maps one OpenRocket export layout to ASTRA canonical CSV columns."""

    name: str
    description: str
    # OpenRocket header label (normalized) -> intermediate field name
    column_map: dict[str, str]
    output_columns: tuple[str, ...]
    convert_row: RowTransform


def _normalize_label(label: str) -> str:
    cleaned = "".join(
        char
        for char in unicodedata.normalize("NFKC", label.strip())
        if unicodedata.category(char) != "Cf"
    )
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.lower()


def _pressures_from_openrocket(air_pressure_mbar: float, mach: float) -> tuple[float, float]:
    """Static + total pressure [Pa] from OpenRocket mbar and Mach (gamma = 1.4)."""
    static_pressure = air_pressure_mbar * 100.0
    total_pressure = static_pressure * math.pow(1.0 + 0.2 * mach * mach, 3.5)
    return static_pressure, total_pressure


def _convert_apogee_1d(row: Row) -> Row:
    static_pressure, total_pressure = _pressures_from_openrocket(
        row["air_pressure_mbar"],
        row["mach"],
    )
    return {
        "time": row["time"],
        "static_pressure": static_pressure,
        "total_pressure": total_pressure,
    }


def _convert_apogee_1d_eval(row: Row) -> Row:
    static_pressure, total_pressure = _pressures_from_openrocket(
        row["air_pressure_mbar"],
        row["mach"],
    )
    return {
        "time": row["time"],
        "static_pressure": static_pressure,
        "total_pressure": total_pressure,
        "position_z": row["position_z"],
    }


def _convert_apogee_3d(row: Row) -> Row:
    return {
        "time": row["time"],
        "position_z": row["position_z"],
        "velocity_z": row["velocity_z"],
        "velocity_lateral": row["velocity_lateral"],
    }


OPENROCKET_PROFILES: dict[str, OpenRocketProfile] = {
    "apogee_1d": OpenRocketProfile(
        name="apogee_1d",
        description="Pressure + Mach export for ApogeePredict1D",
        column_map={
            "time (s)": "time",
            "air pressure (mbar)": "air_pressure_mbar",
            "mach number": "mach",
        },
        output_columns=("time", "static_pressure", "total_pressure"),
        convert_row=_convert_apogee_1d,
    ),
    "apogee_1d_eval": OpenRocketProfile(
        name="apogee_1d_eval",
        description="Pressure + Mach + Altitude export for ApogeePredict1D evaluation",
        column_map={
            "time (s)": "time",
            "altitude (m)": "position_z",
            "air pressure (mbar)": "air_pressure_mbar",
            "mach number": "mach",
        },
        output_columns=("time", "static_pressure", "total_pressure", "position_z"),
        convert_row=_convert_apogee_1d_eval,
    ),
    "apogee_3d": OpenRocketProfile(
        name="apogee_3d",
        description="Altitude + velocity export for ApogeePredict3D",
        column_map={
            "time (s)": "time",
            "altitude (m)": "position_z",
            "vertical velocity (m/s)": "velocity_z",
            "lateral velocity (m/s)": "velocity_lateral",
        },
        output_columns=("time", "position_z", "velocity_z", "velocity_lateral"),
        convert_row=_convert_apogee_3d,
    ),
}


def _parse_header_comment(line: str, profile: OpenRocketProfile) -> list[str] | None:
    match = re.match(r"^#\s*(.+)$", line.strip())
    if match is None:
        return None

    parts = [part.strip() for part in match.group(1).split(",")]
    if len(parts) != len(profile.column_map):
        return None

    mapped = [profile.column_map.get(_normalize_label(part)) for part in parts]
    if any(name is None for name in mapped):
        return None
    return mapped


def _parse_data_row(line: str) -> list[float] | None:
    try:
        return [float(value.strip()) for value in line.split(",")]
    except ValueError:
        return None


def convert_openrocket_csv(source: Path, destination: Path, *, profile: str) -> int:
    try:
        mapping = OPENROCKET_PROFILES[profile]
    except KeyError as exc:
        available = ", ".join(sorted(OPENROCKET_PROFILES))
        raise ValueError(f"Unknown profile {profile!r}. Available: {available}") from exc

    source_columns: list[str] | None = None
    raw_rows: list[list[float]] = []

    with source.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                if source_columns is None:
                    source_columns = _parse_header_comment(stripped, mapping)
                continue

            values = _parse_data_row(stripped)
            if values is not None:
                raw_rows.append(values)

    expected_columns = tuple(mapping.column_map.values())
    columns = source_columns or list(expected_columns)
    if tuple(columns) != expected_columns:
        raise ValueError(
            f"Header columns {columns!r} do not match profile {profile!r}. "
            f"Expected {list(expected_columns)!r}."
        )

    rows: list[Row] = []
    for values in raw_rows:
        if len(values) != len(columns):
            raise ValueError(
                f"Expected {len(columns)} values, got {len(values)} in row: {values!r}"
            )
        row = dict(zip(columns, values, strict=True))
        rows.append(mapping.convert_row(row))

    if not rows:
        raise ValueError(f"No data rows found in {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=mapping.output_columns)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def main() -> None:
    profile_names = ", ".join(sorted(OPENROCKET_PROFILES))
    parser = argparse.ArgumentParser(
        description="Convert OpenRocket simulation CSV to ASTRA-Loop flight log format.",
    )
    parser.add_argument("input", type=Path, help="OpenRocket export CSV")
    parser.add_argument(
        "--profile",
        required=True,
        choices=sorted(OPENROCKET_PROFILES),
        metavar="PROFILE",
        help=f"OpenRocket export layout ({profile_names})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output CSV path (default: <input>_astra.csv)",
    )
    args = parser.parse_args()

    output = args.output or args.input.with_name(f"{args.input.stem}_astra.csv")
    count = convert_openrocket_csv(args.input, output, profile=args.profile)
    print(f"Wrote {count} rows to {output}")


if __name__ == "__main__":
    main()
