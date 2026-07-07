from abc import ABC, abstractmethod
from typing import Any


class Filter(ABC):
    required_columns: tuple[str, ...] = ()

    @classmethod
    def validate_columns(cls, available: set[str]) -> list[str]:
        return [f"Missing column: {col}" for col in cls.required_columns if col not in available]

    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def update(self, measurement: dict[str, Any]) -> dict[str, Any]:
        ...
