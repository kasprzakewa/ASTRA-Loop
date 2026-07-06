from abc import ABC, abstractmethod
from typing import Any


class Predictor(ABC):
    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def predict(self, state: dict[str, Any]) -> dict[str, Any]:
        ...
