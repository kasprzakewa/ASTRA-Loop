# ASTRA-L

**ASTRA-L** is a Software-in-the-Loop (SITL) simulation environment for testing apogee prediction algorithms and airbrake control strategies on experimental student rocket flight data.

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Usage

1. Launch the application with `python main.py`.
2. Click **Load CSV** and select a flight log (OpenRocket export or Kalman filter log).
3. Choose a **Filter**, **Predictor**, and **Controller** from the dropdown menus.
4. Click **Run Simulation** to execute the SITL loop and view plots with performance metrics.

See [GUIDELINES.md](GUIDELINES.md) for architecture details and instructions on adding new algorithms.
