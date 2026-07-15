# ASTRA-Loop

**ASTRA-Loop** is a Software-in-the-Loop (SITL) simulation environment for testing apogee prediction algorithms and airbrake control strategies on experimental student rocket flight data.

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
2. Click **Browse CSV…** and select a flight log (OpenRocket export or Kalman filter log).
3. Choose a **Filter**, **Predictor**, and **Controller** from the dropdown menus.
4. For `ApogeePredict3D`, optionally choose a **Coast Solver** (`euler` or `rk4`).
5. Click **Run Simulation** to execute the SITL loop and view plots with performance metrics.

See [GUIDELINES.md](GUIDELINES.md) for architecture details and instructions on adding new algorithms.

## Apogee predictors

Both predictors estimate apogee during coast after burnout. Physical constants (mass, drag coefficient, reference atmosphere, …) come from **Model Parameters**.

### ApogeePredict1D

Pressure-only estimator for pitot/static-style logs.

**Inputs (CSV):** `static_pressure`, `total_pressure` [Pa]

**Pipeline each step:**

1. Differential pressure:
   $$\Delta p = \max(p_{\mathrm{total}} - p_{\mathrm{static}},\, 0)$$
2. Altitude from the barometric relation (ISA-style scale height / exponent in `ModelParams`).
3. Airspeed from Bernoulli using density at the estimated altitude:
   $$v_z = \sqrt{2\,\Delta p / \rho(z)}$$
4. Closed-form coast apogee with quadratic drag. Drag force is taken **directly from $\Delta p$** as dynamic pressure:
   $$F_d = \Delta p \cdot C_d \cdot A$$
   so the algorithm does **not** recompute $\frac{1}{2}\rho v^2$ from the derived speed (avoids redundant calculation and keeps drag consistent with the pressure measurement).

**Outputs:** `position_z`, `velocity_z`, `predicted_apogee`

When $\Delta p = 0$, apogee falls back to the vacuum ballistic term $z + \frac{m v_z^2}{2mg}$.

OpenRocket pressure/Mach exports can be converted with profile `apogee_1d` (or `apogee_1d_eval` if altitude is included for metrics). Total pressure is reconstructed from static pressure and Mach via the isentropic relation:
$$P_{\mathrm{total}} = P_{\mathrm{static}}\,(1 + 0.2\,M^2)^{3.5}$$

### ApogeePredict3D

State-based coast propagator for Kalman / OpenRocket kinematics logs.

**Inputs (CSV):** `position_z`, `velocity_z`, and either `velocity_lateral` ($= \sqrt{v_x^2 + v_y^2}$) **or** both `velocity_x` and `velocity_y`

**Pipeline each step:**

1. Read current $z$, $v_z$, and lateral speed squared $v_{\mathrm{lat}}^2$.
2. Numerically integrate coast dynamics until $v_z \le 0$:

$$
\begin{aligned}
\dot{z} &= v_z \\
\dot{v}_z &= -g + k\,v_z \\
\frac{d}{dt}(v_{\mathrm{lat}}^2) &= 2\,k\,v_{\mathrm{lat}}^2
\end{aligned}
$$

with

$$
k = -\frac{1}{2m}\,\rho(z)\,C_d\,A\,\sqrt{v_{\mathrm{lat}}^2 + v_z^2}.
$$

**Outputs:** `predicted_apogee` (final $z$), `time_to_apogee`

**Optimizations / design choices:**

- State uses **$v_{\mathrm{lat}}^2$** instead of separate $v_x$, $v_y$ — one less variable in the ODE, same physics for axisymmetric drag.
- Shared derivative function `_coast_derivatives` for both integrators.
- Chooseable solver in the GUI (**Coast Solver**, only when this predictor is selected):
  - `euler` — forward Euler (default, cheaper per step)
  - `rk4` — classical 4th-order Runge–Kutta (more accurate for the same `dt`)

Default step size is $dt = 0.01\,\mathrm{s}$.
