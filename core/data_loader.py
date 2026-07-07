from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


class DataLoader:
    def __init__(self) -> None:
        self._data: pd.DataFrame | None = None

    @property
    def data(self) -> pd.DataFrame:
        if self._data is None:
            raise RuntimeError("No data loaded. Call load_csv() first.")
        return self._data

    @property
    def columns(self) -> set[str]:
        return set(self.data.columns)

    @property
    def is_loaded(self) -> bool:
        return self._data is not None

    def load_csv(self, path: str | Path) -> pd.DataFrame:
        raw = pd.read_csv(path)
        self._data = self._normalize(raw)
        return self._data

    def _normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        normalized = pd.DataFrame(index=raw.index)
        for column in raw.columns:
            normalized[column] = pd.to_numeric(raw[column], errors="coerce")
        return normalized

    def iter_rows(self) -> list[dict[str, Any]]:
        return self.data.to_dict(orient="records")
