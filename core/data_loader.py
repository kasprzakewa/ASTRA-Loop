from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_COLUMNS: dict[str, Any] = {
    "time": 0.0,
    "altitude": np.nan,
    "velocity": np.nan,
    "acceleration": np.nan,
    "position_x": np.nan,
    "position_y": np.nan,
    "position_z": np.nan,
    "velocity_x": np.nan,
    "velocity_y": np.nan,
    "velocity_z": np.nan,
    "true_apogee": np.nan,
    "static_pressure": np.nan,
    "total_pressure": np.nan,
    "airbrake_signal": 0.0,
}


class DataLoader:
    def __init__(self, column_defaults: dict[str, Any] | None = None) -> None:
        self._defaults = column_defaults or DEFAULT_COLUMNS.copy()
        self._data: pd.DataFrame | None = None

    @property
    def data(self) -> pd.DataFrame:
        if self._data is None:
            raise RuntimeError("No data loaded. Call load_csv() first.")
        return self._data

    @property
    def is_loaded(self) -> bool:
        return self._data is not None

    def load_csv(self, path: str | Path) -> pd.DataFrame:
        raw = pd.read_csv(path)
        self._data = self._normalize(raw)
        return self._data

    def _normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        normalized = pd.DataFrame(index=raw.index)

        for column, default in self._defaults.items():
            if column in raw.columns:
                normalized[column] = pd.to_numeric(raw[column], errors="coerce")
            else:
                normalized[column] = default

        for column in raw.columns:
            if column not in normalized.columns:
                normalized[column] = pd.to_numeric(raw[column], errors="coerce")

        return normalized

    def iter_rows(self) -> list[dict[str, Any]]:
        return self.data.to_dict(orient="records")
