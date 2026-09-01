# ASTRA-Loop Architecture Guidelines

This document explains how ASTRA-Loop is structured and how to extend it with new algorithms.

## Overview

ASTRA-Loop uses three core design principles:

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
    ├── flight_schema.py    # Canonical CSV column names and helpers
    ├── data_loader.py      # CSV loading (columns as present in file)
    ├── simulation_engine.py
    ├── evaluator.py
    ├── filters/
    ├── predictors/
    └── controllers/
```

## Canonical CSV Schema

All flight logs use the column names defined in `core/flight_schema.py` (`CANONICAL_COLUMNS`). A file may contain only a **subset** of these columns; missing columns are not filled with defaults.

| Column | Description |
|--------|-------------|
| `time` | Time [s] — required for every simulation |
| `position_x`, `position_y`, `position_z` | Position [m] |
| `velocity_x`, `velocity_y`, `velocity_z` | Velocity [m/s] |
| `acceleration_x`, `acceleration_y`, `acceleration_z` | Acceleration [m/s²] |
| `velocity_lateral` | Horizontal speed √(vx² + vy²) [m/s] |
| `static_pressure`, `total_pressure` | Pressures [Pa] |

Use `get_field(state, name)` from `flight_schema` to read numeric values from a row or algorithm state.

## Adding a New Algorithm

### 1. Create a new file in the correct package

| Type       | Package             | Base class   |
|------------|---------------------|--------------|
| Filter     | `core/filters/`     | `Filter`     |
| Predictor  | `core/predictors/`  | `Predictor`  |
| Controller | `core/controllers/` | `Controller` |

Do **not** put implementations in `base.py`. That file holds only the abstract interface.

### 2. Subclass the base class and declare requirements

```python
from core.predictors.base import Predictor

class MyPredictor(Predictor):
    required_columns = ("position_z", "velocity_z")
    produced_fields = ("predicted_apogee",)

    def reset(self) -> None:
        ...

    def predict(self, state: dict) -> dict:
        return {**state, "predicted_apogee": ...}
```

Override `validate_columns()` when requirements are conditional (e.g. column A **or** columns B and C).

### 3. Export from `__init__.py` (optional but recommended)

```python
from core.predictors.my_predictor import MyPredictor

__all__ = [..., "MyPredictor"]
```

### 4. Done

`discover_plugins()` scans the package at startup. Your class appears in the GUI dropdown automatically — no registry file to edit. Column validation runs when the user clicks **Run Simulation**.

## Interface Contracts

### Filter (`core/filters/base.py`)

- `required_columns` — CSV columns needed before `update()` can run.
- `validate_columns(available)` — Returns a list of error messages.
- `reset()` — Clear internal state before a new run.
- `update(measurement: dict) -> dict` — Process one sensor row; return filtered state.

### Predictor (`core/predictors/base.py`)

- `required_columns` — CSV columns the predictor reads.
- `produced_fields` — State keys written by `predict()` (default includes `predicted_apogee`).
- `reset()` — Clear internal state.
- `predict(state: dict) -> dict` — Return state extended with produced fields.

### Controller (`core/controllers/base.py`)

- `required_columns` — CSV columns needed by `compute()`.
- `reset()` — Clear internal state (e.g. PID integrator).
- `compute(state: dict, setpoint: float) -> float` — Return control signal in `[0, 1]`.

### Built-in Controllers

| Controller | Params (GUI) | Behaviour |
|------------|--------------|-----------|
| `NoController` | — | Always returns `0.0` (brakes closed) |
| `PDController` | `target_apogee`, `kp`, `kd` | `e = predicted_apogee − target`, `de = (e − e_prev)/dt`, `u = clamp(Kp·e + Kd·de, 0, 1)` |

Control `u ∈ [0, 1]` maps to physical servo angle via `control_to_servo_angle(u) = 90° − 60°·u` (safe at 90°, max brake at 30°) in `physics_utils`. Brake area uses `S(α) = 0.1512α² − 124.74α + 9996.8` mm² and `calculate_cross_section(params, servo_angle)`. On MCU, `Servo_SetAngleDeg` maps α ∈ [30°, 90°] to PWM (`SERVO_PWM_MIN` @ 30°, `SERVO_PWM_MAX` @ 90°).

## Built-in Predictors

| Predictor | Reads from CSV | Computes |
|-----------|----------------|----------|
| `ApogeePredict1D` | `static_pressure`, `total_pressure` | `position_z`, `velocity_z`, `predicted_apogee` |
| `ApogeePredict3D` | `position_z`, `velocity_z`, and `velocity_lateral` **or** `velocity_x` + `velocity_y` | `predicted_apogee`, `time_to_apogee` |

`ApogeePredict3D` sets `supports_closed_loop_coast = True` and reads optional `control_signal` from state when predicting coast drag.

### Coast solvers (`ApogeePredict3D`)

3D coast propagation integrates until `v_z <= 0`. Choose the integrator in the GUI (**Coast Solver**, visible only when `ApogeePredict3D` is selected):

| Solver | Method | Notes |
|--------|--------|-------|
| `euler` | Forward Euler | Default; cheaper per step |
| `rk4` | Classical 4th-order Runge–Kutta | More accurate for the same `dt` |

Both share the same coast dynamics in `core/physics_utils.py` (`_coast_derivatives` / `step_coast`). The selection is ignored by `ApogeePredict1D` (analytic formula).

Example files:

- `data/converted/or_1d.csv` — pressure log for `ApogeePredict1D` (profile `apogee_1d`)
- `data/converted/or_1d_w_altitude.csv` — 1D with reference altitude for metrics (profile `apogee_1d_eval`)
- `data/converted/or_3d.csv` — OpenRocket 3D export (profile `apogee_3d`)

Convert OpenRocket exports with `scripts/convert_openrocket_csv.py` — pick a **profile** that matches the export layout:

```bash
python scripts/convert_openrocket_csv.py data/or/or_1d.csv --profile apogee_1d
python scripts/convert_openrocket_csv.py data/or/or_1d_w_altitude.csv --profile apogee_1d_eval
python scripts/convert_openrocket_csv.py data/or/or_3d.csv --profile apogee_3d
```

| Profile | OpenRocket columns | ASTRA output |
|---------|-------------------|--------------|
| `apogee_1d` | Time, Air pressure (mbar), Mach number | `time`, `static_pressure`, `total_pressure` |
| `apogee_1d_eval` | Time, Altitude, Air pressure, Mach number | `time`, `static_pressure`, `total_pressure`, `position_z` |
| `apogee_3d` | Time, Altitude, Vertical velocity, Lateral velocity | `time`, `position_z`, `velocity_z`, `velocity_lateral` |

For `apogee_1d` and `apogee_1d_eval`, total pressure is computed from static pressure and Mach using the isentropic relation
`P_total = P_static × (1 + 0.2·M²)^3.5` (air, γ = 1.4); mbar are converted to Pa (×100).
`apogee_1d_eval` adds `position_z` from OpenRocket altitude for evaluating 1D prediction metrics.

## Simulation Loop

For each step the engine executes:

```
raw measurement → Filter → Predictor → Controller → log
```

The merged filtered + predicted state is passed to the controller. Prediction for control uses `control_signal=0.0` (open-brake coast forecast). Execution time per step is recorded for performance evaluation.

### Closed-loop coast (`PDController` + `ApogeePredict3D`)

After burnout is detected:

1. CSV rows are replayed only up to burnout.
2. From that state the plant is integrated with `step_coast` using the commanded servo angle.
3. Logged altitude / velocity come from the **simulated** plant, not post-burnout CSV rows.

**Coast SIL parameters** (GUI gear next to a predictor with `supports_closed_loop_coast`): **Wind speed**, **Gust strength (vertical)**, **Plant mass scale**, **Plant Cd scale**. These disturb only the plant coast step; the predictor keeps ideal Model Parameters and zero wind. Active in closed-loop runs (`PDController` + closed-loop predictor).

**PD parameters** (GUI gear next to `PDController`): `target_apogee`, `kp`, `kd`.

With `NoController` the full CSV is replayed open-loop (no plant).

Logging rules (open-loop / boost):

- **True altitude** — `position_z` from the CSV row
- **Computed altitude** — `position_z` from predictor output (1D computes it; 3D keeps CSV value)
- **Velocity** — `velocity_z` from predictor output, falling back to CSV

During closed-loop coast, true and computed altitude are both the plant height.

## Data Loader

`DataLoader` loads only columns present in the CSV file. Numeric coercion is applied; missing columns are **not** added. Use `DataLoader.columns` for validation.

## Evaluator

After simulation, `Evaluator` computes metrics with explicit availability rules. A metric shown as **N/A** means it does not apply to the current scenario, not a computation failure.

| Metric | Meaning | Computed when |
|--------|---------|---------------|
| **Altitude RMSE** | RMSE of predictor `position_z` vs CSV reference `position_z` | CSV has reference altitude **and** predictor produces `position_z` (1D) |
| **Apogee Error** | `\|max(predicted_apogee) − max(position_z)\|` from **burnout onward** | Reference altitude present and burnout detectable from `velocity_z` |
| **Target Error** | `\|max(altitude) − target_apogee\|` — how far achieved apogee is from the setpoint | `target_apogee` provided (PDController) |
| **OR Apogee Error** | `\|max(achieved altitude) − max(CSV position_z)\|` — closed-loop plant vs OpenRocket reference | CSV loaded with `position_z` |
| **Max Overshoot** | `max(0, control − 1)` — control signal above full deployment | Active controller (not `NoController`) |
| **Exec Time** | Mean / max loop time per step [ms] | Always |

**Burnout** is detected heuristically as the index of peak `velocity_z` after liftoff (when vertical velocity stops increasing). Apogee prediction metrics use only the coast phase from that point.

Plot checkboxes (combinable):

| From Burnout | Until Apogee | Visible range |
|--------------|--------------|---------------|
| off | off | full flight |
| on | off | burnout → end |
| off | on | start → apogee |
| on | on | burnout → apogee |

Typical outcomes:

| Scenario | Altitude RMSE | Apogee Error | Target Error | Max Overshoot |
|----------|---------------|--------------|--------------|---------------|
| 1D, pressures only | N/A | N/A | N/A | N/A |
| 1D eval (`apogee_1d_eval`) | value | value | N/A | N/A |
| 3D + NoController | N/A | value | N/A | N/A |
| 3D + PDController | N/A | value | value | value |

## PD calibration (YAML test suites)

Tuning scenarios live in [`data/calibration/scenarios.yaml`](data/calibration/scenarios.yaml). Structure:

- **`flights`** — booster CSV paths (OpenRocket `apogee_3d` profile)
- **`sil_presets`** — named Coast SIL disturbances (plant-only)
- **`test_cases`** — `flight` + `sil` preset
- **`suites`** — groups of `test_cases` for batch validation

**GUI:** sidebar **Calibrate…** opens tabs for Run (batch suite + PD source), Tune (`tune_pd.py`), Scenarios (YAML editor), and Guides. Results go to `data/calibration/results/gui_validation.json`.

**CLI:**

```bash
python scripts/tune_pd.py              # Monte Carlo PD grid (reads YAML defaults)
python scripts/validate_pd.py --suite validation
```

See [`data/calibration/README.md`](data/calibration/README.md) for physics prerequisites (body cross section 12.6 cm), why `tuning_target_apogee_m` differs from mission target, and that pre-fix tune results are stale.

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
result = predictor.predict({"position_z": 100.0, "velocity_z": 50.0})
print(result["predicted_apogee"])
```
