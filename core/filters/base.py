from abc import ABC, abstractmethod
from typing import Any


class Filter(ABC):
    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def update(self, measurement: dict[str, Any]) -> dict[str, Any]:
        ...
