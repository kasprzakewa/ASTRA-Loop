#!/usr/bin/env python3
"""Validate tuned PD parameters using YAML calibration scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.calibration_runner import (
    load_pd_from_json,
    load_top_pd_sets,
    run_suite_with_pd_sets,
    suite_results_to_json_rows,
)
from core.controllers.pd_controller import PDControllerParams
from core.calibration_scenarios import (
    default_scenarios_path,
    format_result_line,
    load_calibration_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=default_scenarios_path(),
        help="Calibration scenarios YAML",
    )
    parser.add_argument(
        "--suite",
        type=str,
        default="validation",
        help="Suite name inside scenarios YAML",
    )
    parser.add_argument(
        "--pd-json",
        type=Path,
        default=ROOT / "data" / "calibration" / "results" / "best_pd.json",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=None,
        help="Override mission target apogee [m]",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=1,
        help="Validate top N PD sets from latest tune_pd_*.csv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_calibration_config(args.scenarios)
    if args.suite not in config.suites:
        print(f"Unknown suite '{args.suite}'. Available: {', '.join(config.suites)}")
        return 1

    results_dir = args.pd_json.parent
    if args.top_n > 1:
        pd_sets = load_top_pd_sets(results_dir, args.top_n)
    else:
        pd_sets = [load_pd_from_json(args.pd_json)]

    if args.target is not None:
        pd_sets = [
            PDControllerParams(
                target_apogee=args.target,
                kp=pd.kp,
                kd=pd.kd,
                max_deploy_speed=pd.max_deploy_speed,
                error_deadband=pd.error_deadband,
            )
            for pd in pd_sets
        ]

    runs = run_suite_with_pd_sets(config, args.suite, pd_sets)
    for run in runs:
        pd = run.pd
        print(
            f"\n=== PD set {run.pd_index + 1}: kp={pd.kp:g} kd={pd.kd:g} "
            f"deadband={pd.error_deadband:g} target={pd.target_apogee:g} m ==="
        )
        for item in run.results:
            print(format_result_line(item))

    out_path = config.path.parent / "results" / "validation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(suite_results_to_json_rows(runs), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
