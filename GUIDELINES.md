# ASTRA-L Architecture Guidelines

This document explains how ASTRA-L is structured and how to extend it with new algorithms.

## Overview

ASTRA-L uses three core design principles:

1. **Strategy Pattern** — Filters, predictors, and controllers are interchangeable algorithms behind a common interface.
2. **Dependency Injection** — The simulation engine receives algorithm instances at construction time; it does not import concrete implementations.
3. **Dynamic Discovery** — New algorithms are registered automatically when you add a file to the appropriate package.

```
main.py
├── gui/
│   ├── app.py              # UI, plugin selection, simulation trigger
│   └── visualizer.py       # Matplotlib plot management
└── core/
    ├── registry.py         # Dynamic plugin discovery
    ├── data_loader.py      # Fault-tolerant CSV loading
    ├── simulation_engine.py
    ├── evaluator.py
    ├── filters/
    ├── predictors/
    └── controllers/
```

## Adding a New Algorithm

### 1. Create a new file in the correct package

| Type       | Package             | Base class   |
|------------|---------------------|--------------|
| Filter     | `core/filters/`     | `Filter`     |
| Predictor  | `core/predictors/`  | `Predictor`  |
| Controller | `core/controllers/` | `Controller` |

Do **not** put implementations in `base.py`. That file holds only the abstract interface.

### 2. Subclass the base class

```python
from core.predictors.base import Predictor

class MyPredictor(Predictor):
    def reset(self) -> None:
        ...

    def predict(self, state: dict) -> dict:
        return {**state, "predicted_apogee": ...}
```

### 3. Export from `__init__.py` (optional but recommended)

```python
from core.predictors.my_predictor import MyPredictor

__all__ = [..., "MyPredictor"]
```

### 4. Done

`discover_plugins()` scans the package at startup. Your class appears in the GUI dropdown automatically — no registry file to edit.

## Interface Contracts

### Filter (`core/filters/base.py`)

- `reset()` — Clear internal state before a new run.
- `update(measurement: dict) -> dict` — Process one sensor row; return filtered state.

### Predictor (`core/predictors/base.py`)

- `reset()` — Clear internal state.
- `predict(state: dict) -> dict` — Return state extended with at least `predicted_apogee`.

### Controller (`core/controllers/base.py`)

- `reset()` — Clear internal state (e.g. PID integrator).
- `compute(state: dict, setpoint: float) -> float` — Return control signal in `[0, 1]`.

## Simulation Loop

For each CSV row the engine executes:

```
raw measurement → Filter → Predictor → Controller → log
```

The merged filtered + predicted state is passed to the controller. Execution time per step is recorded for performance evaluation.

## Data Loader

`DataLoader` normalizes CSV columns against `DEFAULT_COLUMNS` in `core/data_loader.py`. Missing columns are filled with `NaN` or sensible defaults so partial logs do not crash the simulation.

To support new column names, add them to `DEFAULT_COLUMNS`.

## Evaluator

After simulation, `Evaluator` computes:

- Altitude RMSE (filtered vs true)
- Apogee prediction error
- Max control signal overshoot
- Per-step execution time statistics

## SOLID Mapping

| Principle                 | How it applies                                      |
|---------------------------|-----------------------------------------------------|
| Single Responsibility     | Each module has one job (load, simulate, evaluate, plot) |
| Open/Closed               | Extend via new files; core engine stays unchanged   |
| Liskov Substitution       | Any concrete algorithm can replace another via the base interface |
| Interface Segregation     | Separate ABCs per algorithm family                  |
| Dependency Inversion      | Engine depends on abstractions, GUI injects concretes |

## Testing a New Module Standalone

```python
from core.predictors.my_predictor import MyPredictor

predictor = MyPredictor()
result = predictor.predict({"altitude": 100.0, "velocity": 50.0, "acceleration": -9.81})
print(result["predicted_apogee"])
```
