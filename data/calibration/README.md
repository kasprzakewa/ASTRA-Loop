# PD calibration

Scenarios are defined in **`scenarios.yaml`** (not JSON). For a full YAML scripting guide see **[`SCENARIOS_YAML.md`](SCENARIOS_YAML.md)**. The same file drives:

- GUI **Calibrate…** (Run, Tune, Scenarios, Guides tabs)
- `scripts/validate_pd.py` (CLI / automation)
- `scripts/tune_pd.py` (defaults, Monte Carlo bounds, CSV path)

## Physics prerequisites

Before trusting any tune/validation result:

1. **Model Parameters → Reset Defaults** — body diameter **12.6 cm** → `BODY_CROSS_SECTION_M2 ≈ 0.01247 m²`.
2. Confirm open-loop apogee on `astra_3d.csv` is **~2460 m** (model) vs **~2497 m** (OpenRocket CSV).
3. Mission target **2500 m** is *above* model open-loop apogee → **PD may stay at u=0** on nominal SIL. That is expected; use `tuning_target_apogee_m: 2450` in YAML for grid search so brakes engage.

### Stale results

Files under `results/` from **before** the cross-section fix (wrong `default_cross_section` ≈ 0.05 m²) are **invalid**. Re-run:

```bash
python scripts/tune_pd.py
python scripts/validate_pd.py --suite validation
```

Delete or ignore `best_pd.json`, `tune_pd_*.csv`, `validation.json` dated before the fix.

## YAML structure

```yaml
defaults:          # mission target, PD defaults, plugin names, Monte Carlo seeds
sil_presets:       # named Coast SIL settings (plant-only)
sil_bounds:        # ranges for tune_pd Monte Carlo
flights:           # OpenRocket CSV paths (relative to this file)
test_cases:        # flight + sil preset
suites:            # named lists of test_cases for batch runs
```

Add a new OpenRocket export:

1. Export from OR with columns: Time, Altitude, Vertical velocity, Lateral velocity.
2. `python scripts/convert_openrocket_csv.py data/or/<file>.csv --profile apogee_3d -o data/converted/<name>.csv`
3. Add a `flights` entry and `test_cases` / `suites` in `scenarios.yaml`.

Suggested OR variants (3–8 total): nominal, ±wind, ±mass, Cd override — see table in this README’s git history or GUIDELINES.md.

## Workflow

### 1. GUI — single flight

- Load `astra_3d.csv`, `ApogeePredict3D` + `PDController`, Coast SIL = 0.
- Tune PD via ⚙ if needed; check **Target Error** and **OR Apogee Error**.

### 2. GUI — Calibrate dialog

Open **Calibrate…** from the sidebar:

| Tab | Purpose |
|-----|---------|
| **Run** | Pick suite and PD source; run batch validation; results table + **Load selected CSV** |
| **Tune** | Run `tune_pd.py` (quick or full); view top results; **Apply best PD to GUI** |
| **Scenarios** | Edit `scenarios.yaml` in-app |
| **Guides** | Read **Scenarios scripting** and **Calibration workflow** (formatted, not raw Markdown) |

Results: `results/gui_validation.json` (Run), `best_pd.json` + `tune_pd_*.csv` (Tune).

**PD source** on the Run tab replaces a separate validate button:

- *Current GUI PD* — same as manual ⚙ settings
- *best_pd.json* — after tuning
- *Compare top 3 from last tune* — same as `validate_pd.py --top-n 3`

### 3. Batch tune (Monte Carlo)

From **Calibrate → Tune** tab, or in terminal:

```bash
python scripts/tune_pd.py
python scripts/tune_pd.py --quick   # smoke test
```

Outputs: `results/tune_pd_<timestamp>.csv`, `results/best_pd.json`, optional heatmap PNG.

### 4. Validate (CLI)

Optional if you use **Calibrate → Run** with PD source *best_pd.json* or *Compare top 3*:

```bash
python scripts/validate_pd.py --suite validation
python scripts/validate_pd.py --suite validation --top-n 3
```

### 5. Firmware + HIL

Copy `kp`, `kd`, `error_deadband` from `best_pd.json` into `firmware/examples/main_user_snippet.c` (or use synced defaults in `pd.c`), rebuild, then:

```bash
python scripts/replay_telemetry_uart.py data/converted/astra_3d.csv \
  --port /dev/ttyACM0 --baud 921600
```

## Interpreting metrics

| Metric | Meaning |
|--------|---------|
| **Target Error** | \|achieved apogee − setpoint\| (closed-loop plant) |
| **OR Apogee Error** | \|achieved apogee − max(OpenRocket CSV altitude)\| |
| Low target error + high OR error | Plant hit setpoint but diverged from OR truth (model/plant mismatch) |
| u=0, target error ≈ 38 m | Natural apogee ~2462 m, target 2500 m — no brake authority needed |
