from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from core.simulation_engine import SimulationResult, slice_to_apogee
from gui.theme import ACCENT_ORANGE, ACCENT_PINK, BG_DARK, GRID_COLOR, TEXT_MUTED, TEXT_PRIMARY


class Visualizer:
    def __init__(self) -> None:
        plt.style.use("dark_background")
        self._figures: dict[str, Figure] = {}
        self._canvases: dict[str, FigureCanvasTkAgg] = {}

    def attach_tab(self, tab_frame: Any, tab_name: str) -> None:
        tab_frame.grid_rowconfigure(0, weight=1)
        tab_frame.grid_columnconfigure(0, weight=1)

        figure = Figure(figsize=(6, 4), dpi=100, facecolor=BG_DARK)
        canvas = FigureCanvasTkAgg(figure, master=tab_frame)
        canvas.get_tk_widget().configure(bg=BG_DARK)
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._figures[tab_name] = figure
        self._canvases[tab_name] = canvas

    def plot(self, result: SimulationResult, *, show_until_apogee: bool = False) -> None:
        plot_data = slice_to_apogee(result) if show_until_apogee else result

        self._plot_altitude(plot_data)
        self._plot_apogee(plot_data)
        self._plot_control(plot_data)

        for canvas in self._canvases.values():
            canvas.draw_idle()

    def _plot_altitude(self, result: SimulationResult) -> None:
        figure = self._figures.get("Altitude")
        if figure is None:
            return

        figure.clear()
        ax = figure.add_subplot(111)
        time = np.array(result.time)

        if self._has_valid_data(result.logged_true_altitude):
            self._glow_line(ax, time, result.logged_true_altitude, ACCENT_PINK, label="True Altitude")
        if self._has_valid_data(result.logged_altitude):
            self._glow_line(
                ax,
                time,
                result.logged_altitude,
                ACCENT_ORANGE,
                label="Computed Altitude",
                linestyle="--",
            )

        self._style_axes(ax, "Altitude vs Time", "Time [s]", "Altitude [m]")
        self._autoscale(ax)
        figure.tight_layout()

    def _plot_apogee(self, result: SimulationResult) -> None:
        figure = self._figures.get("Apogee")
        if figure is None:
            return

        figure.clear()
        ax = figure.add_subplot(111)
        time = np.array(result.time)

        self._glow_line(
            ax,
            time,
            result.logged_predicted_apogee,
            ACCENT_PINK,
            label="Predicted Apogee",
        )
        if self._has_valid_data(result.logged_altitude):
            self._glow_line(
                ax,
                time,
                result.logged_altitude,
                ACCENT_ORANGE,
                label="Computed Altitude",
                linestyle="--",
            )
        self._style_axes(ax, "Predicted Apogee vs Computed Altitude", "Time [s]", "Altitude [m]")
        self._autoscale(ax)
        figure.tight_layout()

    def _plot_control(self, result: SimulationResult) -> None:
        figure = self._figures.get("Control")
        if figure is None:
            return

        figure.clear()
        ax = figure.add_subplot(111)
        time = np.array(result.time)

        self._glow_line(ax, time, result.logged_control_signal, ACCENT_ORANGE, label="Control Signal")
        self._style_axes(ax, "Control Signal vs Time", "Time [s]", "Signal [0-1]")
        self._autoscale(ax)
        ax.set_ylim(-0.05, 1.05)
        figure.tight_layout()

    def _glow_line(
        self,
        ax: Axes,
        x: np.ndarray,
        y: list[float],
        color: str,
        label: str,
        linestyle: str = "-",
        linewidth: float = 1.8,
    ) -> None:
        y_arr = np.array(y, dtype=float)
        ax.plot(x, y_arr, color=color, linewidth=linewidth + 5, alpha=0.18, linestyle=linestyle)
        ax.plot(x, y_arr, color=color, linewidth=linewidth, linestyle=linestyle, label=label)

    def _style_axes(self, ax: Axes, title: str, xlabel: str, ylabel: str) -> None:
        ax.set_facecolor(BG_DARK)
        ax.set_title(title, color=TEXT_PRIMARY, fontsize=11, pad=10)
        ax.set_xlabel(xlabel, color=TEXT_MUTED)
        ax.set_ylabel(ylabel, color=TEXT_MUTED)
        ax.tick_params(colors=TEXT_MUTED, labelsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color(GRID_COLOR)
        ax.spines["left"].set_color(GRID_COLOR)
        ax.grid(True, color=GRID_COLOR, linestyle="--", alpha=0.45, linewidth=0.6)
        legend = ax.legend(facecolor=BG_DARK, edgecolor=GRID_COLOR, fontsize=9)
        for text in legend.get_texts():
            text.set_color(TEXT_PRIMARY)

    @staticmethod
    def _has_valid_data(values: list[float]) -> bool:
        arr = np.array(values, dtype=float)
        return bool(np.any(~np.isnan(arr)))

    @staticmethod
    def _autoscale(ax: Axes) -> None:
        ax.relim()
        ax.autoscale_view()

    def clear(self) -> None:
        for figure in self._figures.values():
            figure.clear()
        for canvas in self._canvases.values():
            canvas.draw_idle()
