from abc import ABC, abstractmethod
from typing import Any


class Controller(ABC):
    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def compute(self, state: dict[str, Any], setpoint: float) -> float:
        ...
