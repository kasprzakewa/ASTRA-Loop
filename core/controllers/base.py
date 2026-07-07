from abc import ABC, abstractmethod
from typing import Any


class Controller(ABC):
    required_columns: tuple[str, ...] = ()

    @classmethod
    def validate_columns(cls, available: set[str]) -> list[str]:
        return [f"Missing column: {col}" for col in cls.required_columns if col not in available]

    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def compute(self, state: dict[str, Any], setpoint: float) -> float:
        ...
