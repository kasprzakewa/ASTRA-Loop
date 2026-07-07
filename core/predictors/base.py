from abc import ABC, abstractmethod
from typing import Any


class Predictor(ABC):
    required_columns: tuple[str, ...] = ()
    produced_fields: tuple[str, ...] = ("predicted_apogee",)

    @classmethod
    def validate_columns(cls, available: set[str]) -> list[str]:
        return [f"Missing column: {col}" for col in cls.required_columns if col not in available]

    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def predict(self, state: dict[str, Any]) -> dict[str, Any]:
        ...
