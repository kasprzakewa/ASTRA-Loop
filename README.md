# ASTRA-Loop

Software-in-the-Loop (SITL) environment for testing apogee predictors and airbrake controllers on experimental rocket flight data.

## Requirements

- Python 3.10+
- Dependencies in `requirements.txt`

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Usage

1. Launch with `python main.py`.
2. **Browse CSV...** and select a flight log (OpenRocket export or converted log).
3. Choose **Filter**, **Predictor**, and **Controller**.
4. For `ApogeePredict3D`, optionally set **Coast Solver** (`euler` / `rk4`) and Coast SIL plant knobs (settings).
5. For `PDController`, set gains / target via settings.
6. **Run Simulation** to plot results and metrics.

Sample log: `data/converted/or_3d.csv`.

Convert OpenRocket exports:

```bash
python scripts/convert_openrocket_csv.py data/or/or_3d.csv --profile apogee_3d
```

See [GUIDELINES.md](GUIDELINES.md) for architecture and how to add algorithms.

## Development

```bash
pip install -r requirements-dev.txt
pre-commit install
ruff check .
ruff format .
```

Pre-commit runs Ruff lint (`--fix`) and format on every commit.
