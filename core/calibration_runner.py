"""Shared calibration run helpers for GUI and CLI."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from core.calibration_scenarios import (
    CalibrationConfig,
    TestCaseResult,
    run_suite,
)
from core.controllers.pd_controller import PDControllerParams
from core.physics_utils import ModelParams


@dataclass
class SuiteRunResult:
    pd_index: int
    pd: PDControllerParams
    results: list[TestCaseResult]


def load_pd_from_json(path: Path) -> PDControllerParams:
    if not path.is_file():
        return PDControllerParams()
    data = json.loads(path.read_text(encoding="utf-8"))
    return PDControllerParams(
        target_apogee=float(data.get("target_apogee", 2500.0)),
        kp=float(data["kp"]),
        kd=float(data["kd"]),
        error_deadband=float(data.get("error_deadband", 10.0)),
        max_deploy_speed=float(data.get("max_deploy_speed", 200.0)),
    )


def load_top_pd_sets(results_dir: Path, top_n: int) -> list[PDControllerParams]:
    csv_files = sorted(results_dir.glob("tune_pd_*.csv"), reverse=True)
    if not csv_files:
        return [load_pd_from_json(results_dir / "best_pd.json")]

    base = load_pd_from_json(results_dir / "best_pd.json")
    rows: list[PDControllerParams] = []
    with csv_files[0].open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            if index >= top_n:
                break
            rows.append(
                PDControllerParams(
                    target_apogee=base.target_apogee,
                    kp=float(row["kp"]),
                    kd=float(row["kd"]),
                    error_deadband=float(row["error_deadband"]),
                    max_deploy_speed=base.max_deploy_speed,
                )
            )
    return rows or [base]


def run_suite_with_pd_sets(
    config: CalibrationConfig,
    suite_name: str,
    pd_sets: list[PDControllerParams],
    *,
    model_params: ModelParams | None = None,
    target_apogee: float | None = None,
) -> list[SuiteRunResult]:
    """Run a suite once per PD parameter set."""
    output: list[SuiteRunResult] = []
    for pd_index, pd in enumerate(pd_sets):
        target = target_apogee if target_apogee is not None else pd.target_apogee
        resolved = PDControllerParams(
            target_apogee=target,
            kp=pd.kp,
            kd=pd.kd,
            max_deploy_speed=pd.max_deploy_speed,
            error_deadband=pd.error_deadband,
        )
        results = run_suite(
            config,
            suite_name,
            pd=resolved,
            model_params=model_params,
            target_apogee=target,
        )
        output.append(SuiteRunResult(pd_index=pd_index, pd=resolved, results=results))
    return output


def suite_results_to_json_rows(runs: list[SuiteRunResult]) -> list[dict]:
    rows: list[dict] = []
    for run in runs:
        for item in run.results:
            rows.append(
                {
                    "pd_set": run.pd_index + 1,
                    "kp": run.pd.kp,
                    "kd": run.pd.kd,
                    "error_deadband": run.pd.error_deadband,
                    "target_apogee_m": run.pd.target_apogee,
                    "case": item.case_name,
                    "flight": item.flight_name,
                    "sil": item.sil_name,
                    "skipped": item.skipped,
                    "skip_reason": item.skip_reason,
                    "target_error_m": item.metrics.target_error,
                    "reference_apogee_error_m": item.metrics.reference_apogee_error,
                    "achieved_apogee_m": item.achieved_apogee_m,
                    "or_apogee_m": item.or_apogee_m,
                    "csv": str(item.csv_path),
                }
            )
    return rows
