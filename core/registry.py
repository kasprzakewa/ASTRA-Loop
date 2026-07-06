from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Type, TypeVar

T = TypeVar("T")


def discover_plugins(package_name: str, base_class: Type[T]) -> dict[str, Type[T]]:
    package = importlib.import_module(package_name)
    plugins: dict[str, Type[T]] = {}

    for module_info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        if module_info.name.endswith(".base"):
            continue

        module = importlib.import_module(module_info.name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, base_class) and obj is not base_class and not inspect.isabstract(obj):
                plugins[obj.__name__] = obj

    return plugins
