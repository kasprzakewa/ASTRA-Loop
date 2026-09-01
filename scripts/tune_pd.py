#!/usr/bin/env python3
"""Grid-search PD gains with Monte Carlo Coast SIL disturbances."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.calibration_scenarios import (
    default_scenarios_path,
    load_calibration_config,
    sample_sil,
    SilBounds,
)
from core.controllers.pd_controller import PDController, PDControllerParams
from core.data_loader import DataLoader
from core.evaluator import Evaluator
from core.filters.no_filter import NoFilter
from core.physics_utils import ModelParams
from core.predictors.apogee_predict_3d import ApogeePredict3D
from core.simulation_engine import SimulationEngine


@dataclass(frozen=True)
class TrialResult:
    kp: float
    kd: float
    error_deadband: float
    mean_target_error: float
    p95_target_error: float
    max_overshoot: float
    mean_u_squared: float
    score: float
    brakes_engaged_fraction: float


def _run_once(
    loader: DataLoader,
    params: ModelParams,
    pd: PDControllerParams,
    *,
    target_apogee: float,
    sil: dict[str, float],
    wind_seed: int,
) -> tuple[float, float, float, float]:
    controller = PDController(
        target_apogee=target_apogee,
        kp=pd.kp,
        kd=pd.kd,
        max_deploy_speed=pd.max_deploy_speed,
        error_deadband=pd.error_deadband,
    )
    engine = SimulationEngine(
        data_loader=loader,
        filter_algo=NoFilter(),
        predictor=ApogeePredict3D(params),
        controller=controller,
        wind_speed=sil["wind_speed"],
        gust_strength=sil["gust_strength"],
        plant_mass_scale=sil["plant_mass_scale"],
        plant_cd_scale=sil["plant_cd_scale"],
        wind_seed=wind_seed,
    )
    result = engine.run(report_brake_stats=False)
    metrics = Evaluator().evaluate(
        result,
        predictor_cls=ApogeePredict3D,
        controller_cls=PDController,
        target_apogee=target_apogee,
        reference_apogee=loader.reference_apogee(),
    )
    target_error = metrics.target_error if metrics.target_error is not None else float("inf")
    overshoot = metrics.max_overshoot if metrics.max_overshoot is not None else 0.0
    signal = np.array(result.logged_control_signal, dtype=float)
    mean_u_squared = float(np.mean(signal * signal)) if signal.size else 0.0
    brakes_on = float(np.mean(signal > 1e-6)) if signal.size else 0.0
    return target_error, overshoot, mean_u_squared, brakes_on


def _score(
    target_errors: list[float],
    overshoots: list[float],
    mean_u_squared: list[float],
) -> TrialResult | None:
    if not target_errors:
        return None
    arr = np.array(target_errors, dtype=float)
    mean_err = float(np.mean(arr))
    p95_err = float(np.percentile(arr, 95))
    max_overshoot = float(np.max(overshoots)) if overshoots else 0.0
    mean_u2 = float(np.mean(mean_u_squared)) if mean_u_squared else 0.0
    score = mean_err + 0.3 * p95_err + 50.0 * max_overshoot + 10.0 * mean_u2
    return mean_err, p95_err, max_overshoot, mean_u2, score


def evaluate_pd_grid(
    loader: DataLoader,
    *,
    target_apogee: float,
    kp_values: list[float],
    kd_values: list[float],
    deadband_values: list[float],
    seeds: int,
    sil_bounds: SilBounds,
    seed_offset: int = 0,
) -> list[TrialResult]:
    params = ModelParams()
    rng = random.Random(seed_offset)
    results: list[TrialResult] = []

    combos = list(itertools.product(kp_values, kd_values, deadband_values))
    total = len(combos) * seeds
    done = 0
    t0 = time.perf_counter()

    for kp, kd, deadband in combos:
        pd = PDControllerParams(
            target_apogee=target_apogee,
            kp=kp,
            kd=kd,
            error_deadband=deadband,
        )
        target_errors: list[float] = []
        overshoots: list[float] = []
        mean_u_squared: list[float] = []
        brakes_on: list[float] = []

        for trial in range(seeds):
            sil_params = sample_sil(rng, sil_bounds)
            sil = {
                "wind_speed": sil_params.wind_speed,
                "gust_strength": sil_params.gust_strength,
                "plant_mass_scale": sil_params.plant_mass_scale,
                "plant_cd_scale": sil_params.plant_cd_scale,
            }
            te, mo, mu2, bon = _run_once(
                loader,
                params,
                pd,
                target_apogee=target_apogee,
                sil=sil,
                wind_seed=seed_offset + trial,
            )
            target_errors.append(te)
            overshoots.append(mo)
            mean_u_squared.append(mu2)
            brakes_on.append(bon)
            done += 1
            if done % 20 == 0 or done == total:
                elapsed = time.perf_counter() - t0
                rate = done / elapsed if elapsed > 0 else 0.0
                print(
                    f"\r  {done}/{total} trials ({rate:.1f}/s)",
                    end="",
                    flush=True,
                )

        scored = _score(target_errors, overshoots, mean_u_squared)
        if scored is None:
            continue
        mean_err, p95_err, max_overshoot, mean_u2, score = scored
        results.append(
            TrialResult(
                kp=kp,
                kd=kd,
                error_deadband=deadband,
                mean_target_error=mean_err,
                p95_target_error=p95_err,
                max_overshoot=max_overshoot,
                mean_u_squared=mean_u2,
                score=score,
                brakes_engaged_fraction=float(np.mean(brakes_on)),
            )
        )

    print()
    results.sort(key=lambda item: item.score)
    return results


def _write_csv(path: Path, rows: list[TrialResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(rows[0]).keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _write_best_json(path: Path, rows: list[TrialResult], target_apogee: float) -> None:
    if not rows:
        return
    best = rows[0]
    payload = {
        "target_apogee": target_apogee,
        "kp": best.kp,
        "kd": best.kd,
        "error_deadband": best.error_deadband,
        "score": best.score,
        "mean_target_error": best.mean_target_error,
        "p95_target_error": best.p95_target_error,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _maybe_plot_heatmap(path: Path, rows: list[TrialResult], deadband: float) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    subset = [row for row in rows if abs(row.error_deadband - deadband) < 1e-9]
    if not subset:
        return

    kp_values = sorted({row.kp for row in subset})
    kd_values = sorted({row.kd for row in subset})
    grid = np.full((len(kd_values), len(kp_values)), np.nan)
    for row in subset:
        i = kd_values.index(row.kd)
        j = kp_values.index(row.kp)
        grid[i, j] = row.score

    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(grid, aspect="auto", origin="lower", cmap="viridis_r")
    ax.set_xticks(range(len(kp_values)), labels=[f"{v:g}" for v in kp_values])
    ax.set_yticks(range(len(kd_values)), labels=[f"{v:g}" for v in kd_values])
    ax.set_xlabel("kp")
    ax.set_ylabel("kd")
    ax.set_title(f"PD tune score (deadband={deadband:g} m)")
    fig.colorbar(im, ax=ax, label="score (lower is better)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=default_scenarios_path(),
        help="Calibration scenarios YAML (defaults, Monte Carlo bounds)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Boost trajectory CSV (default: astra_nominal from scenarios YAML)",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=None,
        help="Mission target apogee [m] (default: scenarios YAML)",
    )
    parser.add_argument(
        "--tuning-target",
        type=float,
        default=None,
        help="Target used during grid search (default: --target). "
        "Use a value below open-loop apogee (~2460 m) so brakes engage during tuning.",
    )
    parser.add_argument("--seeds", type=int, default=None, help="Monte Carlo seeds per PD combo")
    parser.add_argument("--quick", action="store_true", help="Small grid for smoke tests")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "calibration" / "results",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_calibration_config(args.scenarios)

    csv_path = args.csv
    if csv_path is None:
        flight = config.flights.get("astra_nominal")
        if flight is None:
            print("No --csv and no astra_nominal flight in scenarios YAML")
            return 1
        csv_path = flight.csv_path

    mission_target = args.target if args.target is not None else config.mission_target()
    tuning_target = (
        args.tuning_target
        if args.tuning_target is not None
        else config.tuning_target()
    )
    loader = DataLoader()
    loader.load_csv(csv_path)
    ref = loader.reference_apogee()
    print(f"Scenarios: {args.scenarios}")
    print(f"CSV: {csv_path}")
    print(f"OpenRocket reference apogee: {ref:.1f} m" if ref else "OpenRocket reference apogee: N/A")
    print(f"Mission target: {mission_target:.1f} m | tuning target: {tuning_target:.1f} m")

    if args.quick:
        kp_values = [0.06, 0.08, 0.10]
        kd_values = [0.0, 0.0005]
        deadband_values = [10.0]
        seeds = 3
    else:
        kp_values = [0.02, 0.04, 0.06, 0.08, 0.10]
        kd_values = [0.0, 0.0002, 0.0005, 0.001]
        deadband_values = [5.0, 10.0, 20.0]
        seeds = args.seeds if args.seeds is not None else config.monte_carlo_seeds()

    sil_bounds = config.monte_carlo_bounds()
    print(
        f"Grid: {len(kp_values)}×{len(kd_values)}×{len(deadband_values)} PD combos, "
        f"{seeds} SIL seeds each"
    )
    rows = evaluate_pd_grid(
        loader,
        target_apogee=tuning_target,
        kp_values=kp_values,
        kd_values=kd_values,
        deadband_values=deadband_values,
        seeds=seeds,
        sil_bounds=sil_bounds,
    )
    if not rows:
        print("No results.")
        return 1

    out_dir = args.output_dir
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_csv = out_dir / f"tune_pd_{stamp}.csv"
    json_path = out_dir / "best_pd.json"
    _write_csv(out_csv, rows)
    _write_best_json(json_path, rows, mission_target)

    best = rows[0]
    print("\nTop 3 PD sets (min score):")
    for row in rows[:3]:
        print(
            f"  kp={row.kp:g} kd={row.kd:g} deadband={row.error_deadband:g} "
            f"score={row.score:.2f} mean_err={row.mean_target_error:.1f}m "
            f"p95={row.p95_target_error:.1f}m brakes={row.brakes_engaged_fraction:.0%}"
        )
    print(f"\nWrote {out_csv}")
    print(f"Wrote {json_path} (mission target={mission_target:g} m)")

    heatmap_path = out_dir / f"heatmap_db{best.error_deadband:g}_{stamp}.png"
    _maybe_plot_heatmap(heatmap_path, rows, best.error_deadband)
    if heatmap_path.exists():
        print(f"Wrote {heatmap_path}")

    if abs(tuning_target - mission_target) > 1e-6:
        print(f"\nValidating best PD at mission target {mission_target:g} m (nominal SIL)...")
        pd = PDControllerParams(
            target_apogee=mission_target,
            kp=best.kp,
            kd=best.kd,
            error_deadband=best.error_deadband,
        )
        te, mo, mu2, bon = _run_once(
            loader,
            ModelParams(),
            pd,
            target_apogee=mission_target,
            sil={
                "wind_speed": 0.0,
                "gust_strength": 0.0,
                "plant_mass_scale": 1.0,
                "plant_cd_scale": 1.0,
            },
            wind_seed=0,
        )
        print(f"  target_error={te:.1f} m overshoot={mo:.3f} brakes={bon:.0%}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
