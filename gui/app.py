from __future__ import annotations

import inspect
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Type

import customtkinter as ctk

from core.controllers.base import Controller
from core.data_loader import DataLoader
from core.evaluator import EvaluationMetrics, Evaluator
from core.filters.base import Filter
from core.physics_utils import ModelParams
from core.predictors.base import Predictor
from core.registry import discover_plugins
from core.simulation_engine import SimulationEngine, SimulationResult
from gui.params_dialog import ModelParamsDialog
from gui.theme import (
    ACCENT_ORANGE,
    ACCENT_PINK,
    BG_DARK,
    DROPDOWN_GRAY,
    DROPDOWN_HOVER,
    FRAME_BORDER,
    GRID_COLOR,
    LOGO_SIZE,
    SURFACE_GRAY,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WIDGET_CORNER_RADIUS,
)
from gui.visualizer import Visualizer

LOGO_PATH = Path(__file__).resolve().parent / "assets" / "astra_logo.png"


class AstraApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=BG_DARK)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("ASTRA Loop Simulator")
        self.geometry("1200x700")
        self.minsize(900, 600)

        self._data_loader = DataLoader()
        self._evaluator = Evaluator()
        self._visualizer = Visualizer()
        self._model_params = ModelParams()
        self._last_result: SimulationResult | None = None
        self._logo_image: ctk.CTkImage | None = None

        self._filters = discover_plugins("core.filters", Filter)
        self._predictors = discover_plugins("core.predictors", Predictor)
        self._controllers = discover_plugins("core.controllers", Controller)

        self._build_layout()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_plot_panel()

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color=BG_DARK, border_width=0)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(0, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            sidebar,
            fg_color=BG_DARK,
            scrollbar_fg_color=BG_DARK,
            scrollbar_button_color=DROPDOWN_GRAY,
            scrollbar_button_hover_color=DROPDOWN_HOVER,
        )
        scroll.grid(row=0, column=0, sticky="nsew")

        self._add_logo(scroll)

        self._build_csv_box(scroll)

        self._filter_var = tk.StringVar(value=self._default_key(self._filters, preferred="NoFilter"))
        self._predictor_var = tk.StringVar(value=self._default_key(self._predictors))
        self._controller_var = tk.StringVar(value=self._default_key(self._controllers))

        filter_options = sorted(self._filters.keys(), key=lambda name: (name != "NoFilter", name))
        self._add_selector(scroll, "Filter", self._filter_var, filter_options)
        self._add_selector(scroll, "Predictor", self._predictor_var, list(self._predictors.keys()))
        self._add_selector(scroll, "Controller", self._controller_var, list(self._controllers.keys()))

        self._params_btn = ctk.CTkButton(
            scroll,
            text="Model Parameters…",
            command=self._open_params_dialog,
            fg_color=SURFACE_GRAY,
            hover_color=DROPDOWN_HOVER,
            border_width=1,
            border_color=GRID_COLOR,
            text_color=TEXT_PRIMARY,
        )
        self._params_btn.pack(padx=16, pady=(8, 4), fill="x")

        self._show_until_apogee_var = tk.BooleanVar(value=False)
        self._show_until_apogee_cb = ctk.CTkCheckBox(
            scroll,
            text="Show until Apogee",
            variable=self._show_until_apogee_var,
            command=self._on_plot_options_changed,
            fg_color=ACCENT_PINK,
            hover_color=self._darken(ACCENT_PINK),
            border_color=ACCENT_ORANGE,
            checkmark_color=TEXT_PRIMARY,
            text_color=TEXT_PRIMARY,
        )
        self._show_until_apogee_cb.pack(padx=16, pady=(12, 8), anchor="w")

        self._run_btn = ctk.CTkButton(
            scroll,
            text="Run Simulation",
            command=self._on_run_simulation,
            fg_color=ACCENT_PINK,
            hover_color=self._darken(ACCENT_PINK),
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._run_btn.pack(padx=16, pady=(8, 8), fill="x")

        self._build_metrics_box(scroll)

    def _build_csv_box(self, parent: ctk.CTkFrame) -> None:
        box = ctk.CTkFrame(parent, fg_color=SURFACE_GRAY, corner_radius=8, border_width=1, border_color=GRID_COLOR)
        box.pack(padx=16, pady=(0, 16), fill="x")

        ctk.CTkLabel(
            box,
            text="Flight Data",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self._file_label = ctk.CTkLabel(
            box,
            text="No file selected",
            text_color=TEXT_MUTED,
            wraplength=210,
            justify="left",
        )
        self._file_label.pack(anchor="w", padx=12, pady=(0, 8))

        self._load_btn = ctk.CTkButton(
            box,
            text="Browse CSV…",
            command=self._on_load_csv,
            fg_color=DROPDOWN_GRAY,
            hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
            height=32,
            corner_radius=WIDGET_CORNER_RADIUS,
        )
        self._load_btn.pack(padx=12, pady=(0, 12), fill="x")

    def _build_metrics_box(self, parent: ctk.CTkFrame) -> None:
        box = ctk.CTkFrame(parent, fg_color=SURFACE_GRAY, corner_radius=8, border_width=1, border_color=GRID_COLOR)
        box.pack(padx=16, pady=(8, 24), fill="x")

        ctk.CTkLabel(
            box,
            text="Metrics",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self._metrics_text = ctk.CTkTextbox(
            box,
            fg_color=BG_DARK,
            border_color=GRID_COLOR,
            border_width=1,
            text_color=TEXT_MUTED,
            wrap="word",
            activate_scrollbars=True,
            height=140,
        )
        self._metrics_text.pack(padx=12, pady=(0, 12), fill="x")
        self._set_metrics_text("Run a simulation to see metrics.")

    def _build_plot_panel(self) -> None:
        panel = ctk.CTkFrame(self, fg_color=BG_DARK, border_width=1, border_color=FRAME_BORDER)
        panel.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        self._tabview = ctk.CTkTabview(
            panel,
            fg_color=BG_DARK,
            segmented_button_fg_color=FRAME_BORDER,
            segmented_button_selected_color=ACCENT_PINK,
            segmented_button_selected_hover_color=self._darken(ACCENT_PINK),
            segmented_button_unselected_color=FRAME_BORDER,
            segmented_button_unselected_hover_color=ACCENT_ORANGE,
            text_color=TEXT_PRIMARY,
        )
        self._tabview.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        for tab_name in ("Altitude", "Apogee", "Control"):
            tab = self._tabview.add(tab_name)
            tab.configure(fg_color=BG_DARK)
            self._visualizer.attach_tab(tab, tab_name)

    def _add_logo(self, parent: ctk.CTkFrame) -> None:
        logo_frame = ctk.CTkFrame(parent, fg_color="transparent")
        logo_frame.pack(pady=(16, 4))

        try:
            from PIL import Image

            if LOGO_PATH.is_file():
                pil_image = Image.open(LOGO_PATH)
                self._logo_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=LOGO_SIZE)
                ctk.CTkLabel(logo_frame, image=self._logo_image, text="").pack()
                return
        except Exception:
            pass

        ctk.CTkLabel(
            logo_frame,
            text="ASTRA-L",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=ACCENT_PINK,
        ).pack()

    def _add_selector(self, parent: ctk.CTkFrame, label: str, variable: tk.StringVar, options: list[str]) -> None:
        ctk.CTkLabel(parent, text=label, anchor="w", text_color=TEXT_PRIMARY).pack(padx=16, pady=(8, 2), anchor="w")
        menu = ctk.CTkOptionMenu(
            parent,
            variable=variable,
            values=options or ["—"],
            height=32,
            corner_radius=WIDGET_CORNER_RADIUS,
            fg_color=DROPDOWN_GRAY,
            button_color=DROPDOWN_GRAY,
            button_hover_color=DROPDOWN_HOVER,
            dropdown_fg_color=DROPDOWN_GRAY,
            dropdown_hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
        )
        menu.pack(padx=16, pady=(0, 4), fill="x")

    @staticmethod
    def _darken(hex_color: str, factor: float = 0.82) -> str:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"

    def _default_key(self, registry: dict[str, Type], preferred: str | None = None) -> str:
        if preferred and preferred in registry:
            return preferred
        if not registry:
            return "—"
        return next(iter(registry))

    def _open_params_dialog(self) -> None:
        ModelParamsDialog(self, self._model_params, on_save=self._on_params_saved)

    def _on_params_saved(self, params: ModelParams) -> None:
        self._model_params = params

    def _create_predictor(self, predictor_cls: Type[Predictor]) -> Predictor:
        signature = inspect.signature(predictor_cls.__init__)
        if "params" in signature.parameters:
            return predictor_cls(params=self._model_params)
        return predictor_cls()

    def _on_load_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            self._data_loader.load_csv(path)
            self._file_label.configure(text=Path(path).name, text_color=TEXT_PRIMARY)
        except Exception as exc:
            messagebox.showerror("Load Error", f"Failed to load CSV:\n{exc}")

    def _on_run_simulation(self) -> None:
        if not self._data_loader.is_loaded:
            messagebox.showwarning("No Data", "Load a CSV file before running the simulation.")
            return

        filter_cls = self._filters.get(self._filter_var.get())
        predictor_cls = self._predictors.get(self._predictor_var.get())
        controller_cls = self._controllers.get(self._controller_var.get())

        if not all([filter_cls, predictor_cls, controller_cls]):
            messagebox.showerror("Configuration Error", "Select valid filter, predictor, and controller.")
            return

        try:
            engine = SimulationEngine(
                data_loader=self._data_loader,
                filter_algo=filter_cls(),
                predictor=self._create_predictor(predictor_cls),
                controller=controller_cls(),
            )
            result = engine.run()
            self._last_result = result

            self._refresh_plots()
            metrics = self._evaluator.evaluate(result)
            self._update_metrics(metrics)

        except Exception as exc:
            messagebox.showerror("Simulation Error", f"Simulation failed:\n{exc}")

    def _on_plot_options_changed(self) -> None:
        self._refresh_plots()

    def _refresh_plots(self) -> None:
        if self._last_result is None:
            return
        self._visualizer.plot(
            self._last_result,
            show_until_apogee=self._show_until_apogee_var.get(),
        )

    def _set_metrics_text(self, text: str, *, highlight: bool = False) -> None:
        self._metrics_text.configure(state="normal")
        self._metrics_text.delete("1.0", "end")
        self._metrics_text.insert("1.0", text)
        self._metrics_text.configure(
            state="disabled",
            text_color=TEXT_PRIMARY if highlight else TEXT_MUTED,
        )

    def _update_metrics(self, metrics: EvaluationMetrics) -> None:
        text = (
            f"Altitude RMSE: {metrics.altitude_rmse:.2f} m\n"
            f"Apogee Error: {metrics.apogee_error:.2f} m\n"
            f"Max Overshoot: {metrics.max_overshoot:.3f}\n"
            f"Mean Exec Time: {metrics.mean_execution_time_ms:.3f} ms\n"
            f"Max Exec Time: {metrics.max_execution_time_ms:.3f} ms"
        )
        self._set_metrics_text(text, highlight=True)

    def run(self) -> None:
        self.mainloop()


def main() -> None:
    app = AstraApp()
    app.run()


if __name__ == "__main__":
    main()
