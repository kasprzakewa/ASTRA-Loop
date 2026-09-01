"""Load and run PD calibration test cases from YAML scenario files."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Type

import yaml

from core.controllers.base import Controller
from core.controllers.pd_controller import PDController, PDControllerParams
from core.data_loader import DataLoader
from core.evaluator import EvaluationMetrics, Evaluator
from core.filters.base import Filter
from core.physics_utils import ModelParams
from core.predictors.base import Predictor
from core.registry import discover_plugins
from core.simulation_engine import SimulationEngine, SimulationResult


@dataclass(frozen=True)
class SilParams:
    wind_speed: float = 0.0
    gust_strength: float = 0.0
    plant_mass_scale: float = 1.0
    plant_cd_scale: float = 1.0
    wind_seed: int | None = None


@dataclass(frozen=True)
class SilBounds:
    wind_speed: tuple[float, float] = (0.0, 6.0)
    gust_strength: tuple[float, float] = (0.0, 2.0)
    plant_mass_scale: tuple[float, float] = (0.97, 1.03)
    plant_cd_scale: tuple[float, float] = (0.92, 1.08)


@dataclass(frozen=True)
class FlightRef:
    name: str
    csv_path: Path
    description: str = ""
    optional: bool = False


@dataclass(frozen=True)
class TestCaseDef:
    name: str
    flight: str
    sil: str = "nominal"
    description: str = ""
    skip_if_missing: bool = False


@dataclass(frozen=True)
class SuiteDef:
    name: str
    description: str
    cases: tuple[str, ...]


@dataclass
class CalibrationConfig:
    path: Path
    defaults: dict[str, Any]
    sil_presets: dict[str, SilParams]
    sil_bounds: dict[str, SilBounds]
    flights: dict[str, FlightRef]
    test_cases: dict[str, TestCaseDef]
    suites: dict[str, SuiteDef]

    def default_pd(self) -> PDControllerParams:
        pd = self.defaults.get("pd", {})
        return PDControllerParams(
            target_apogee=float(
                self.defaults.get("mission_target_apogee_m", pd.get("target_apogee", 2500.0))
            ),
            kp=float(pd.get("kp", 0.08)),
            kd=float(pd.get("kd", 0.0005)),
            max_deploy_speed=float(pd.get("max_deploy_speed", 200.0)),
            error_deadband=float(pd.get("error_deadband", 10.0)),
        )

    def mission_target(self) -> float:
        return float(self.defaults.get("mission_target_apogee_m", 2500.0))

    def tuning_target(self) -> float:
        return float(
            self.defaults.get(
                "tuning_target_apogee_m",
                self.defaults.get("mission_target_apogee_m", 2500.0),
            )
        )

    def monte_carlo_bounds(self) -> SilBounds:
        preset_name = self.defaults.get("monte_carlo", {}).get("bounds_preset", "monte_carlo")
        return self.sil_bounds.get(preset_name, SilBounds())

    def monte_carlo_seeds(self) -> int:
        return int(self.defaults.get("monte_carlo", {}).get("seeds", 20))


@dataclass
class TestCaseResult:
    case_name: str
    flight_name: str
    sil_name: str
    csv_path: Path
    metrics: EvaluationMetrics
    achieved_apogee_m: float
    or_apogee_m: float | None
    skipped: bool = False
    skip_reason: str | None = None
    result: SimulationResult | None = None


def _pair(value: Any, default: tuple[float, float]) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return float(value[0]), float(value[1])
    return default


def _sil_from_mapping(data: dict[str, Any]) -> SilParams:
    return SilParams(
        wind_speed=float(data.get("wind_speed", 0.0)),
        gust_strength=float(data.get("gust_strength", 0.0)),
        plant_mass_scale=float(data.get("plant_mass_scale", 1.0)),
        plant_cd_scale=float(data.get("plant_cd_scale", 1.0)),
        wind_seed=data.get("wind_seed"),
    )


def load_calibration_config(path: Path) -> CalibrationConfig:
    """Parse a calibration scenarios YAML file."""
    path = path.resolve()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid calibration YAML: {path}")

    base_dir = path.parent
    defaults = raw.get("defaults", {})

    sil_presets: dict[str, SilParams] = {}
    for name, preset in raw.get("sil_presets", {}).items():
        if isinstance(preset, dict):
            sil_presets[name] = _sil_from_mapping(preset)

    sil_bounds: dict[str, SilBounds] = {}
    for name, bounds in raw.get("sil_bounds", {}).items():
        if not isinstance(bounds, dict):
            continue
        sil_bounds[name] = SilBounds(
            wind_speed=_pair(bounds.get("wind_speed"), (0.0, 6.0)),
            gust_strength=_pair(bounds.get("gust_strength"), (0.0, 2.0)),
            plant_mass_scale=_pair(bounds.get("plant_mass_scale"), (0.97, 1.03)),
            plant_cd_scale=_pair(bounds.get("plant_cd_scale"), (0.92, 1.08)),
        )

    flights: dict[str, FlightRef] = {}
    for entry in raw.get("flights", []):
        if not isinstance(entry, dict) or "name" not in entry:
            continue
        csv_rel = entry.get("csv", "")
        csv_path = (base_dir / csv_rel).resolve() if csv_rel else base_dir
        flights[entry["name"]] = FlightRef(
            name=entry["name"],
            csv_path=csv_path,
            description=str(entry.get("description", "")),
            optional=bool(entry.get("optional", False)),
        )

    test_cases: dict[str, TestCaseDef] = {}
    for entry in raw.get("test_cases", []):
        if not isinstance(entry, dict) or "name" not in entry:
            continue
        test_cases[entry["name"]] = TestCaseDef(
            name=entry["name"],
            flight=str(entry.get("flight", "")),
            sil=str(entry.get("sil", "nominal")),
            description=str(entry.get("description", "")),
            skip_if_missing=bool(entry.get("skip_if_missing", False)),
        )

    suites: dict[str, SuiteDef] = {}
    for name, entry in raw.get("suites", {}).items():
        if not isinstance(entry, dict):
            continue
        cases = entry.get("cases", [])
        suites[name] = SuiteDef(
            name=name,
            description=str(entry.get("description", "")),
            cases=tuple(str(c) for c in cases),
        )

    return CalibrationConfig(
        path=path,
        defaults=defaults,
        sil_presets=sil_presets,
        sil_bounds=sil_bounds,
        flights=flights,
        test_cases=test_cases,
        suites=suites,
    )


def default_scenarios_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "calibration" / "scenarios.yaml"


def sample_sil(rng: random.Random, bounds: SilBounds) -> SilParams:
    return SilParams(
        wind_speed=rng.uniform(*bounds.wind_speed),
        gust_strength=rng.uniform(*bounds.gust_strength),
        plant_mass_scale=rng.uniform(*bounds.plant_mass_scale),
        plant_cd_scale=rng.uniform(*bounds.plant_cd_scale),
    )


def _resolve_plugins(
    config: CalibrationConfig,
) -> tuple[Type[Filter], Type[Predictor], Type[Controller], str]:
    filter_name = str(config.defaults.get("filter", "NoFilter"))
    predictor_name = str(config.defaults.get("predictor", "ApogeePredict3D"))
    controller_name = str(config.defaults.get("controller", "PDController"))
    solver = str(config.defaults.get("coast_solver", "euler"))

    filters = discover_plugins("core.filters", Filter)
    predictors = discover_plugins("core.predictors", Predictor)
    controllers = discover_plugins("core.controllers", Controller)

    filter_cls = filters.get(filter_name)
    predictor_cls = predictors.get(predictor_name)
    controller_cls = controllers.get(controller_name)
    if filter_cls is None or predictor_cls is None or controller_cls is None:
        raise ValueError(
            f"Unknown plugin in defaults: filter={filter_name}, "
            f"predictor={predictor_name}, controller={controller_name}"
        )
    return filter_cls, predictor_cls, controller_cls, solver


def run_test_case(
    config: CalibrationConfig,
    case: TestCaseDef,
    *,
    pd: PDControllerParams | None = None,
    model_params: ModelParams | None = None,
    target_apogee: float | None = None,
) -> TestCaseResult:
    """Run a single YAML test case."""
    pd_params = pd or config.default_pd()
    target = target_apogee if target_apogee is not None else pd_params.target_apogee
    params = model_params or ModelParams()

    flight = config.flights.get(case.flight)
    if flight is None:
        return TestCaseResult(
            case_name=case.name,
            flight_name=case.flight,
            sil_name=case.sil,
            csv_path=Path(),
            metrics=EvaluationMetrics(
                altitude_rmse=None,
                altitude_rmse_na_reason="unknown flight",
                apogee_error=None,
                apogee_error_na_reason="unknown flight",
                target_error=None,
                target_error_na_reason="unknown flight",
                max_overshoot=None,
                max_overshoot_na_reason="unknown flight",
                reference_apogee_error=None,
                reference_apogee_error_na_reason="unknown flight",
                mean_execution_time_ms=0.0,
                max_execution_time_ms=0.0,
            ),
            achieved_apogee_m=float("nan"),
            or_apogee_m=None,
            skipped=True,
            skip_reason=f"unknown flight '{case.flight}'",
        )

    if not flight.csv_path.is_file():
        if case.skip_if_missing or flight.optional:
            return TestCaseResult(
                case_name=case.name,
                flight_name=case.flight,
                sil_name=case.sil,
                csv_path=flight.csv_path,
                metrics=EvaluationMetrics(
                    altitude_rmse=None,
                    altitude_rmse_na_reason="missing csv",
                    apogee_error=None,
                    apogee_error_na_reason="missing csv",
                    target_error=None,
                    target_error_na_reason="missing csv",
                    max_overshoot=None,
                    max_overshoot_na_reason="missing csv",
                    reference_apogee_error=None,
                    reference_apogee_error_na_reason="missing csv",
                    mean_execution_time_ms=0.0,
                    max_execution_time_ms=0.0,
                ),
                achieved_apogee_m=float("nan"),
                or_apogee_m=None,
                skipped=True,
                skip_reason=f"missing CSV: {flight.csv_path}",
            )
        raise FileNotFoundError(flight.csv_path)

    sil = config.sil_presets.get(case.sil, SilParams())

    filter_cls, predictor_cls, controller_cls, solver = _resolve_plugins(config)
    loader = DataLoader()
    loader.load_csv(flight.csv_path)

    controller = controller_cls(
        target_apogee=target,
        kp=pd_params.kp,
        kd=pd_params.kd,
        max_deploy_speed=pd_params.max_deploy_speed,
        error_deadband=pd_params.error_deadband,
    ) if issubclass(controller_cls, PDController) else controller_cls()

    predictor_kwargs: dict[str, Any] = {}
    import inspect

    sig = inspect.signature(predictor_cls.__init__)
    if "params" in sig.parameters:
        predictor_kwargs["params"] = params
    if "solver" in sig.parameters:
        predictor_kwargs["solver"] = solver

    engine = SimulationEngine(
        data_loader=loader,
        filter_algo=filter_cls(),
        predictor=predictor_cls(**predictor_kwargs),
        controller=controller,
        wind_speed=sil.wind_speed,
        gust_strength=sil.gust_strength,
        plant_mass_scale=sil.plant_mass_scale,
        plant_cd_scale=sil.plant_cd_scale,
        wind_seed=sil.wind_seed,
    )
    result = engine.run(report_brake_stats=False)
    metrics = Evaluator().evaluate(
        result,
        predictor_cls=predictor_cls,
        controller_cls=controller_cls,
        target_apogee=target if issubclass(controller_cls, PDController) else None,
        reference_apogee=loader.reference_apogee(),
    )
    return TestCaseResult(
        case_name=case.name,
        flight_name=case.flight,
        sil_name=case.sil,
        csv_path=flight.csv_path,
        metrics=metrics,
        achieved_apogee_m=max(result.logged_altitude),
        or_apogee_m=loader.reference_apogee(),
        result=result,
    )


def run_suite(
    config: CalibrationConfig,
    suite_name: str,
    *,
    pd: PDControllerParams | None = None,
    model_params: ModelParams | None = None,
    target_apogee: float | None = None,
) -> list[TestCaseResult]:
    """Run all test cases listed in a named suite."""
    suite = config.suites.get(suite_name)
    if suite is None:
        raise KeyError(f"Unknown suite '{suite_name}' in {config.path}")

    results: list[TestCaseResult] = []
    for case_name in suite.cases:
        case = config.test_cases.get(case_name)
        if case is None:
            results.append(
                TestCaseResult(
                    case_name=case_name,
                    flight_name="",
                    sil_name="",
                    csv_path=Path(),
                    metrics=EvaluationMetrics(
                        altitude_rmse=None,
                        altitude_rmse_na_reason="unknown case",
                        apogee_error=None,
                        apogee_error_na_reason="unknown case",
                        target_error=None,
                        target_error_na_reason="unknown case",
                        max_overshoot=None,
                        max_overshoot_na_reason="unknown case",
                        reference_apogee_error=None,
                        reference_apogee_error_na_reason="unknown case",
                        mean_execution_time_ms=0.0,
                        max_execution_time_ms=0.0,
                    ),
                    achieved_apogee_m=float("nan"),
                    or_apogee_m=None,
                    skipped=True,
                    skip_reason=f"unknown test case '{case_name}'",
                )
            )
            continue
        results.append(
            run_test_case(
                config,
                case,
                pd=pd,
                model_params=model_params,
                target_apogee=target_apogee,
            )
        )
    return results


def format_result_line(item: TestCaseResult) -> str:
    if item.skipped:
        return f"SKIP {item.case_name:28} ({item.skip_reason})"
    te = item.metrics.target_error
    ore = item.metrics.reference_apogee_error
    te_s = f"{te:.1f}m" if te is not None else "N/A"
    ore_s = f"{ore:.1f}m" if ore is not None else "N/A"
    return (
        f"{item.case_name:28} {item.flight_name:16} {item.sil_name:12} "
        f"target_err={te_s:>8} OR_err={ore_s:>8} z={item.achieved_apogee_m:.1f}m"
    )
