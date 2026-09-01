from __future__ import annotations

import json
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from core.calibration_runner import (
    load_pd_from_json,
    load_top_pd_sets,
    run_suite_with_pd_sets,
    suite_results_to_json_rows,
)
from core.calibration_scenarios import (
    CalibrationConfig,
    default_scenarios_path,
    load_calibration_config,
)
from core.controllers.pd_controller import PDControllerParams
from core.physics_utils import ModelParams
from gui.markdown_view import MarkdownView
from gui.results_table import (
    SUITE_COLUMNS,
    TUNE_COLUMNS,
    ResultsTable,
    suite_result_rows,
    tune_result_rows,
)
from gui.theme import (
    ACCENT_ORANGE,
    ACCENT_PINK,
    BG_DARK,
    DROPDOWN_HOVER,
    FRAME_BORDER,
    GRID_COLOR,
    SURFACE_GRAY,
    TEXT_MUTED,
    TEXT_PRIMARY,
)
from gui.yaml_editor import YamlEditorFrame

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PD_SOURCE_GUI = "Current GUI PD"
PD_SOURCE_YAML = "scenarios.yaml defaults"
PD_SOURCE_BEST = "best_pd.json"
PD_SOURCE_TOP3 = "Compare top 3 from last tune"

GUIDE_SCENARIOS = PROJECT_ROOT / "data" / "calibration" / "SCENARIOS_YAML.md"
GUIDE_WORKFLOW = PROJECT_ROOT / "data" / "calibration" / "README.md"


class CalibrateDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        *,
        model_params: ModelParams,
        pd_params: PDControllerParams,
        on_load_csv: Callable[[Path], None],
        on_pd_apply: Callable[[PDControllerParams], None],
    ) -> None:
        super().__init__(parent)

        self._model_params = model_params
        self._pd_params = pd_params
        self._on_load_csv = on_load_csv
        self._on_pd_apply = on_pd_apply
        self._config: CalibrationConfig | None = None
        self._last_suite_runs: list = []
        self._running_suite = False
        self._running_tune = False
        self._tune_process: subprocess.Popen | None = None

        self.title("Calibrate")
        self.geometry("960x720")
        self.minsize(800, 600)
        self.configure(fg_color=BG_DARK)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            header,
            text="Calibrate",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        path_row = ctk.CTkFrame(header, fg_color="transparent")
        path_row.pack(side="right", fill="x", expand=True, padx=(24, 0))

        self._path_var = tk.StringVar(value=str(default_scenarios_path()))
        ctk.CTkEntry(
            path_row,
            textvariable=self._path_var,
            fg_color=FRAME_BORDER,
            border_color=GRID_COLOR,
            text_color=TEXT_PRIMARY,
            placeholder_text="Scenarios YAML",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            path_row,
            text="Browse…",
            width=80,
            command=self._browse_yaml,
            fg_color=SURFACE_GRAY,
            hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            path_row,
            text="Reload",
            width=72,
            command=self._reload_config,
            fg_color=SURFACE_GRAY,
            hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
        ).pack(side="right", padx=(8, 0))

        self._tabs = ctk.CTkTabview(
            self,
            fg_color=BG_DARK,
            segmented_button_fg_color=FRAME_BORDER,
            segmented_button_selected_color=ACCENT_PINK,
            segmented_button_selected_hover_color="#D9436A",
            segmented_button_unselected_color=FRAME_BORDER,
            segmented_button_unselected_hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
        )
        self._tabs.pack(fill="both", expand=True, padx=16, pady=(4, 8))

        self._build_run_tab()
        self._build_tune_tab()
        self._build_scenarios_tab()
        self._build_guides_tab()

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(
            footer,
            text="Close",
            command=self._on_close,
            fg_color=FRAME_BORDER,
            hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
            width=100,
        ).pack(side="right")

        self._reload_config()

    def _scenarios_path(self) -> Path:
        return Path(self._path_var.get()).resolve()

    def _results_dir(self) -> Path:
        if self._config is not None:
            return self._config.path.parent / "results"
        return default_scenarios_path().parent / "results"

    def _browse_yaml(self) -> None:
        path = filedialog.askopenfilename(
            title="Select scenarios YAML",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
            initialdir=str(default_scenarios_path().parent),
        )
        if path:
            self._path_var.set(path)
            self._reload_config()

    def _reload_config(self) -> None:
        path = self._scenarios_path()
        try:
            self._config = load_calibration_config(path)
        except Exception as exc:
            self._config = None
            messagebox.showerror("YAML Error", f"Failed to load scenarios:\n{exc}", parent=self)
            return

        suite_names = sorted(self._config.suites.keys()) or ["—"]
        self._suite_menu.configure(values=suite_names)
        if self._suite_var.get() not in suite_names:
            self._suite_var.set(suite_names[0])
        self._on_suite_changed(self._suite_var.get())

        self._yaml_editor.load_path(path)
        self._update_tune_summary()
        self._load_guide(self._guide_var.get())

    def _on_scenarios_saved(self, path: Path) -> None:
        self._path_var.set(str(path))
        self._reload_config()

    def _build_run_tab(self) -> None:
        tab = self._tabs.add("Run")
        tab.configure(fg_color=BG_DARK)

        opts = ctk.CTkFrame(tab, fg_color=SURFACE_GRAY, corner_radius=8)
        opts.pack(fill="x", padx=4, pady=4)

        ctk.CTkLabel(opts, text="Suite", text_color=TEXT_MUTED).pack(anchor="w", padx=12, pady=(10, 2))
        self._suite_var = tk.StringVar(value="validation")
        self._suite_menu = ctk.CTkOptionMenu(
            opts,
            variable=self._suite_var,
            values=["validation"],
            fg_color=FRAME_BORDER,
            button_color=FRAME_BORDER,
            button_hover_color=DROPDOWN_HOVER,
            dropdown_fg_color=FRAME_BORDER,
            dropdown_hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
            command=self._on_suite_changed,
        )
        self._suite_menu.pack(fill="x", padx=12, pady=(0, 4))

        self._suite_desc = ctk.CTkLabel(
            opts,
            text="",
            text_color=TEXT_MUTED,
            wraplength=860,
            justify="left",
        )
        self._suite_desc.pack(anchor="w", padx=12, pady=(0, 8))

        row = ctk.CTkFrame(opts, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(row, text="PD source", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self._pd_source_var = tk.StringVar(value=PD_SOURCE_GUI)
        ctk.CTkOptionMenu(
            row,
            variable=self._pd_source_var,
            values=[PD_SOURCE_GUI, PD_SOURCE_YAML, PD_SOURCE_BEST, PD_SOURCE_TOP3],
            fg_color=FRAME_BORDER,
            button_color=FRAME_BORDER,
            button_hover_color=DROPDOWN_HOVER,
            dropdown_fg_color=FRAME_BORDER,
            dropdown_hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
            width=260,
        ).pack(side="left")

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=4, pady=4)

        self._run_suite_btn = ctk.CTkButton(
            btn_row,
            text="Run Suite",
            command=self._on_run_suite,
            fg_color=ACCENT_PINK,
            hover_color="#D9436A",
            text_color=TEXT_PRIMARY,
        )
        self._run_suite_btn.pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="Load selected CSV",
            command=self._on_load_selected_csv,
            fg_color=ACCENT_ORANGE,
            hover_color="#E08A4F",
            text_color=TEXT_PRIMARY,
        ).pack(side="right")

        ctk.CTkLabel(tab, text="Results", text_color=TEXT_MUTED).pack(anchor="w", padx=8, pady=(8, 2))
        self._suite_table = ResultsTable(tab, SUITE_COLUMNS)
        self._suite_table.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    def _build_tune_tab(self) -> None:
        tab = self._tabs.add("Tune")
        tab.configure(fg_color=BG_DARK)

        summary = ctk.CTkFrame(tab, fg_color=SURFACE_GRAY, corner_radius=8)
        summary.pack(fill="x", padx=4, pady=4)

        self._tune_summary = ctk.CTkLabel(
            summary,
            text="Load scenarios YAML to see targets.",
            text_color=TEXT_MUTED,
            wraplength=860,
            justify="left",
        )
        self._tune_summary.pack(anchor="w", padx=12, pady=10)

        adv = ctk.CTkFrame(tab, fg_color=SURFACE_GRAY, corner_radius=8)
        adv.pack(fill="x", padx=4, pady=4)

        ctk.CTkLabel(
            adv,
            text="Options",
            font=ctk.CTkFont(weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self._quick_tune_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            adv,
            text="Quick tune (small grid, smoke test)",
            variable=self._quick_tune_var,
            fg_color=ACCENT_PINK,
            hover_color="#D9436A",
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=12, pady=2)

        seeds_row = ctk.CTkFrame(adv, fg_color="transparent")
        seeds_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(seeds_row, text="Monte Carlo seeds (optional)", text_color=TEXT_MUTED).pack(side="left")
        self._seeds_var = tk.StringVar(value="")
        ctk.CTkEntry(
            seeds_row,
            textvariable=self._seeds_var,
            width=80,
            fg_color=FRAME_BORDER,
            border_color=GRID_COLOR,
            text_color=TEXT_PRIMARY,
            placeholder_text="YAML default",
        ).pack(side="left", padx=(8, 0))

        out_row = ctk.CTkFrame(adv, fg_color="transparent")
        out_row.pack(fill="x", padx=12, pady=(4, 10))
        ctk.CTkLabel(out_row, text="Output directory", text_color=TEXT_MUTED).pack(side="left")
        self._output_dir_var = tk.StringVar(value=str(default_scenarios_path().parent / "results"))
        ctk.CTkEntry(
            out_row,
            textvariable=self._output_dir_var,
            fg_color=FRAME_BORDER,
            border_color=GRID_COLOR,
            text_color=TEXT_PRIMARY,
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=4, pady=4)

        self._run_tune_btn = ctk.CTkButton(
            btn_row,
            text="Run Tune",
            command=self._on_run_tune,
            fg_color=ACCENT_PINK,
            hover_color="#D9436A",
            text_color=TEXT_PRIMARY,
        )
        self._run_tune_btn.pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="Apply best PD to GUI",
            command=self._on_apply_best_pd,
            fg_color=ACCENT_ORANGE,
            hover_color="#E08A4F",
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            btn_row,
            text="Open results folder",
            command=self._open_results_folder,
            fg_color=SURFACE_GRAY,
            hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
        ).pack(side="right")

        self._best_pd_label = ctk.CTkLabel(
            tab,
            text="",
            text_color=TEXT_MUTED,
            wraplength=860,
            justify="left",
        )
        self._best_pd_label.pack(anchor="w", padx=8, pady=(4, 2))

        ctk.CTkLabel(tab, text="Top tune results", text_color=TEXT_MUTED).pack(anchor="w", padx=8, pady=(4, 2))
        self._tune_table = ResultsTable(tab, TUNE_COLUMNS)
        self._tune_table.pack(fill="x", padx=4, pady=(0, 4))

        ctk.CTkLabel(tab, text="Log", text_color=TEXT_MUTED).pack(anchor="w", padx=8, pady=(4, 2))
        self._tune_log = ctk.CTkTextbox(
            tab,
            height=120,
            fg_color=BG_DARK,
            border_color=GRID_COLOR,
            border_width=1,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="none",
            activate_scrollbars=True,
        )
        self._tune_log.pack(fill="x", padx=4, pady=(0, 4))

    def _build_scenarios_tab(self) -> None:
        tab = self._tabs.add("Scenarios")
        tab.configure(fg_color=BG_DARK)

        ctk.CTkLabel(
            tab,
            text="Edit scenarios.yaml — test cases and suites used by Run and Tune.",
            text_color=TEXT_MUTED,
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=4, pady=(4, 8))

        self._yaml_editor = YamlEditorFrame(tab, on_saved=self._on_scenarios_saved)
        self._yaml_editor.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_guides_tab(self) -> None:
        tab = self._tabs.add("Guides")
        tab.configure(fg_color=BG_DARK)

        picker = ctk.CTkFrame(tab, fg_color="transparent")
        picker.pack(fill="x", padx=4, pady=4)

        self._guide_var = tk.StringVar(value="Scenarios scripting")
        ctk.CTkSegmentedButton(
            picker,
            values=["Scenarios scripting", "Calibration workflow"],
            variable=self._guide_var,
            command=self._on_guide_changed,
            fg_color=FRAME_BORDER,
            selected_color=ACCENT_PINK,
            selected_hover_color="#D9436A",
            unselected_color=SURFACE_GRAY,
            unselected_hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self._guide_view = MarkdownView(tab)
        self._guide_view.pack(fill="both", expand=True, padx=4, pady=4)

    def _on_suite_changed(self, value: str) -> None:
        if self._config is None:
            self._suite_desc.configure(text="")
            return
        suite = self._config.suites.get(value)
        if suite is None:
            self._suite_desc.configure(text="")
            return
        self._suite_desc.configure(text=f"{suite.description} ({len(suite.cases)} cases)")

    def _on_guide_changed(self, _value: str) -> None:
        self._load_guide(self._guide_var.get())

    def _load_guide(self, name: str) -> None:
        path = GUIDE_SCENARIOS if name == "Scenarios scripting" else GUIDE_WORKFLOW
        self._guide_view.load_file(path)

    def _update_tune_summary(self) -> None:
        if self._config is None:
            self._tune_summary.configure(text="Load scenarios YAML to see targets.")
            return
        self._tune_summary.configure(
            text=(
                f"Mission target: {self._config.mission_target():.0f} m  |  "
                f"Tuning target: {self._config.tuning_target():.0f} m  |  "
                f"Monte Carlo seeds: {self._config.monte_carlo_seeds()}"
            )
        )
        self._refresh_tune_results()

    def _resolve_pd_sets(self) -> list[PDControllerParams]:
        if self._config is None:
            return [self._pd_params]

        source = self._pd_source_var.get()
        results_dir = self._results_dir()

        if source == PD_SOURCE_GUI:
            return [self._pd_params]
        if source == PD_SOURCE_YAML:
            return [self._config.default_pd()]
        if source == PD_SOURCE_BEST:
            return [load_pd_from_json(results_dir / "best_pd.json")]
        if source == PD_SOURCE_TOP3:
            return load_top_pd_sets(results_dir, 3)
        return [self._pd_params]

    def _on_run_suite(self) -> None:
        if self._running_suite or self._config is None:
            return

        suite_name = self._suite_var.get()
        if suite_name not in self._config.suites:
            messagebox.showwarning("No suite", "Select a valid suite.", parent=self)
            return

        pd_sets = self._resolve_pd_sets()
        multi_pd = len(pd_sets) > 1

        self._running_suite = True
        self._run_suite_btn.configure(state="disabled", text="Running…")
        self._suite_table.set_rows([])

        def worker() -> None:
            try:
                runs = run_suite_with_pd_sets(
                    self._config,
                    suite_name,
                    pd_sets,
                    model_params=self._model_params,
                )
                out_path = self._results_dir() / "gui_validation.json"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(suite_results_to_json_rows(runs), indent=2) + "\n",
                    encoding="utf-8",
                )
                self.after(0, lambda: self._finish_suite_run(runs, multi_pd, out_path))
            except Exception as exc:
                self.after(0, lambda: self._fail_suite_run(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_suite_run(self, runs: list, multi_pd: bool, out_path: Path) -> None:
        self._last_suite_runs = runs
        self._running_suite = False
        self._run_suite_btn.configure(state="normal", text="Run Suite")
        self._suite_table.set_rows(suite_result_rows(runs, multi_pd=multi_pd))
        messagebox.showinfo(
            "Suite complete",
            f"Wrote {out_path.name}",
            parent=self,
        )

    def _fail_suite_run(self, message: str) -> None:
        self._running_suite = False
        self._run_suite_btn.configure(state="normal", text="Run Suite")
        messagebox.showerror("Suite failed", message, parent=self)

    def _on_load_selected_csv(self) -> None:
        row = self._suite_table.selected_row()
        if row is None:
            messagebox.showinfo("No selection", "Select a result row first.", parent=self)
            return

        item = row.get("_item")
        if item is None or row.get("_muted"):
            reason = row.get("_skip_reason") or "skipped"
            messagebox.showwarning("Cannot load", f"Case has no CSV ({reason}).", parent=self)
            return

        csv_path = row.get("_csv_path")
        if csv_path is None or not Path(csv_path).is_file():
            messagebox.showwarning("Cannot load", "CSV file not found.", parent=self)
            return

        self._on_load_csv(Path(csv_path))
        messagebox.showinfo("CSV loaded", f"Loaded {Path(csv_path).name}", parent=self)

    def _on_run_tune(self) -> None:
        if self._running_tune:
            return

        scenarios = self._scenarios_path()
        if not scenarios.is_file():
            messagebox.showwarning("No scenarios", "Select a valid scenarios YAML.", parent=self)
            return

        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "tune_pd.py"),
            "--scenarios",
            str(scenarios),
            "--output-dir",
            self._output_dir_var.get(),
        ]
        if self._quick_tune_var.get():
            cmd.append("--quick")
        seeds_text = self._seeds_var.get().strip()
        if seeds_text:
            try:
                cmd.extend(["--seeds", str(int(seeds_text))])
            except ValueError:
                messagebox.showerror("Invalid seeds", "Seeds must be an integer.", parent=self)
                return

        self._running_tune = True
        self._run_tune_btn.configure(state="disabled", text="Running…")
        self._tune_log.configure(state="normal")
        self._tune_log.delete("1.0", "end")
        self._tune_log.insert("1.0", "Starting tune_pd.py…\n")
        self._tune_log.configure(state="disabled")

        def worker() -> None:
            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                self._tune_process = process
                assert process.stdout is not None
                for line in process.stdout:
                    self.after(0, lambda text=line: self._append_tune_log(text))
                code = process.wait()
                self.after(0, lambda: self._finish_tune_run(code))
            except Exception as exc:
                self.after(0, lambda: self._fail_tune_run(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _append_tune_log(self, text: str) -> None:
        self._tune_log.configure(state="normal")
        self._tune_log.insert("end", text)
        self._tune_log.see("end")
        self._tune_log.configure(state="disabled")

    def _finish_tune_run(self, exit_code: int) -> None:
        self._running_tune = False
        self._tune_process = None
        self._run_tune_btn.configure(state="normal", text="Run Tune")
        self._refresh_tune_results()
        if exit_code != 0:
            messagebox.showerror("Tune failed", f"tune_pd.py exited with code {exit_code}.", parent=self)
        else:
            messagebox.showinfo("Tune complete", "See results table and best_pd.json.", parent=self)

    def _fail_tune_run(self, message: str) -> None:
        self._running_tune = False
        self._tune_process = None
        self._run_tune_btn.configure(state="normal", text="Run Tune")
        messagebox.showerror("Tune failed", message, parent=self)

    def _refresh_tune_results(self) -> None:
        results_dir = Path(self._output_dir_var.get())
        best_path = results_dir / "best_pd.json"
        if best_path.is_file():
            pd = load_pd_from_json(best_path)
            data = json.loads(best_path.read_text(encoding="utf-8"))
            score = data.get("score")
            score_s = f"{score:.2f}" if score is not None else "N/A"
            self._best_pd_label.configure(
                text=(
                    f"Best PD: kp={pd.kp:g}  kd={pd.kd:g}  deadband={pd.error_deadband:g}  "
                    f"target={pd.target_apogee:g} m  score={score_s}"
                )
            )
        else:
            self._best_pd_label.configure(text="No best_pd.json yet — run Tune first.")

        csv_files = sorted(results_dir.glob("tune_pd_*.csv"), reverse=True)
        if csv_files:
            self._tune_table.set_rows(tune_result_rows(csv_files[0]))
        else:
            self._tune_table.set_rows([])

    def _on_apply_best_pd(self) -> None:
        best_path = Path(self._output_dir_var.get()) / "best_pd.json"
        if not best_path.is_file():
            messagebox.showwarning("No results", "Run Tune first to create best_pd.json.", parent=self)
            return
        pd = load_pd_from_json(best_path)
        self._on_pd_apply(pd)
        messagebox.showinfo(
            "PD applied",
            f"Applied kp={pd.kp:g} kd={pd.kd:g} deadband={pd.error_deadband:g} "
            f"target={pd.target_apogee:g} m to main GUI.",
            parent=self,
        )

    def _open_results_folder(self) -> None:
        folder = Path(self._output_dir_var.get())
        folder.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(folder)])
        except OSError:
            messagebox.showinfo("Results folder", str(folder), parent=self)

    def _on_close(self) -> None:
        if self._yaml_editor.is_dirty() and not self._yaml_editor.confirm_discard():
            return
        if self._running_tune and self._tune_process is not None:
            if not messagebox.askyesno(
                "Tune running",
                "A tune job is still running. Close anyway?",
                parent=self,
            ):
                return
        self.destroy()


def open_calibrate_dialog(
    parent: ctk.CTk,
    *,
    model_params: ModelParams,
    pd_params: PDControllerParams,
    on_load_csv: Callable[[Path], None],
    on_pd_apply: Callable[[PDControllerParams], None],
) -> CalibrateDialog:
    return CalibrateDialog(
        parent,
        model_params=model_params,
        pd_params=pd_params,
        on_load_csv=on_load_csv,
        on_pd_apply=on_pd_apply,
    )
