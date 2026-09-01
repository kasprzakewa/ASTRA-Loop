"""Tabular result widgets for the Calibrate dialog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import customtkinter as ctk

from gui.theme import (
    ACCENT_PINK,
    BG_DARK,
    FRAME_BORDER,
    GRID_COLOR,
    SURFACE_GRAY,
    TEXT_MUTED,
    TEXT_PRIMARY,
)


@dataclass(frozen=True)
class TableColumn:
    key: str
    title: str
    width: int = 100


def _fmt_m(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f} m"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0%}"


class ResultsTable(ctk.CTkFrame):
    """Selectable table built from CTk frames (no ttk dependency)."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        columns: list[TableColumn],
        *,
        on_select: Callable[[int], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color=BG_DARK, **kwargs)
        self._columns = columns
        self._on_select = on_select
        self._rows: list[dict[str, Any]] = []
        self._selected_index: int | None = None
        self._row_frames: list[ctk.CTkFrame] = []

        header = ctk.CTkFrame(self, fg_color=SURFACE_GRAY, corner_radius=4)
        header.pack(fill="x", pady=(0, 4))
        for col_index, column in enumerate(columns):
            ctk.CTkLabel(
                header,
                text=column.title,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=TEXT_PRIMARY,
                width=column.width,
                anchor="w",
            ).grid(row=0, column=col_index, sticky="w", padx=6, pady=6)

        self._body = ctk.CTkScrollableFrame(self, fg_color=BG_DARK, height=220)
        self._body.pack(fill="both", expand=True)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._selected_index = None
        for child in self._body.winfo_children():
            child.destroy()
        self._row_frames.clear()

        if not rows:
            ctk.CTkLabel(
                self._body,
                text="No results yet.",
                text_color=TEXT_MUTED,
            ).pack(anchor="w", padx=8, pady=8)
            return

        for row_index, row in enumerate(rows):
            muted = bool(row.get("_muted", False))
            frame = ctk.CTkFrame(
                self._body,
                fg_color=FRAME_BORDER if row_index == self._selected_index else "transparent",
                corner_radius=4,
            )
            frame.pack(fill="x", pady=1)
            self._row_frames.append(frame)

            for col_index, column in enumerate(self._columns):
                value = row.get(column.key, "")
                ctk.CTkLabel(
                    frame,
                    text=str(value),
                    font=ctk.CTkFont(size=12),
                    text_color=TEXT_MUTED if muted else TEXT_PRIMARY,
                    width=column.width,
                    anchor="w",
                ).grid(row=0, column=col_index, sticky="w", padx=6, pady=4)

            for widget in frame.winfo_children():
                widget.bind(
                    "<Button-1>",
                    lambda _e, idx=row_index: self._select_row(idx),
                )
            frame.bind("<Button-1>", lambda _e, idx=row_index: self._select_row(idx))

    def selected_index(self) -> int | None:
        return self._selected_index

    def selected_row(self) -> dict[str, Any] | None:
        if self._selected_index is None:
            return None
        return self._rows[self._selected_index]

    def _select_row(self, index: int) -> None:
        self._selected_index = index
        for row_index, frame in enumerate(self._row_frames):
            frame.configure(
                fg_color=ACCENT_PINK if row_index == index else "transparent",
            )
        if self._on_select is not None:
            self._on_select(index)


SUITE_COLUMNS = [
    TableColumn("pd_set", "PD", 36),
    TableColumn("case", "Case", 140),
    TableColumn("flight", "Flight", 100),
    TableColumn("sil", "SIL", 90),
    TableColumn("target_err", "Target err", 88),
    TableColumn("or_err", "OR err", 80),
    TableColumn("apogee", "Apogee", 80),
    TableColumn("status", "Status", 56),
]

TUNE_COLUMNS = [
    TableColumn("rank", "Rank", 44),
    TableColumn("kp", "kp", 64),
    TableColumn("kd", "kd", 72),
    TableColumn("deadband", "Deadband", 80),
    TableColumn("score", "Score", 72),
    TableColumn("mean_err", "Mean err", 80),
    TableColumn("brakes", "Brakes", 64),
]


def suite_result_rows(
    runs: list,
    *,
    multi_pd: bool = False,
) -> list[dict[str, Any]]:
    """Build table rows from SuiteRunResult list or flat TestCaseResult list."""
    rows: list[dict[str, Any]] = []

    if runs and hasattr(runs[0], "results"):
        for run in runs:
            for item in run.results:
                rows.append(_suite_row_from_item(item, pd_set=run.pd_index + 1 if multi_pd else None))
    else:
        for item in runs:
            rows.append(_suite_row_from_item(item, pd_set=None))

    return rows


def _suite_row_from_item(item, pd_set: int | None) -> dict[str, Any]:
    skipped = item.skipped
    return {
        "pd_set": str(pd_set) if pd_set is not None else "—",
        "case": item.case_name,
        "flight": item.flight_name,
        "sil": item.sil_name,
        "target_err": "—" if skipped else _fmt_m(item.metrics.target_error),
        "or_err": "—" if skipped else _fmt_m(item.metrics.reference_apogee_error),
        "apogee": "—" if skipped else _fmt_m(item.achieved_apogee_m),
        "status": "SKIP" if skipped else "OK",
        "_muted": skipped,
        "_skip_reason": item.skip_reason,
        "_csv_path": item.csv_path,
        "_item": item,
    }


def tune_result_rows(csv_path) -> list[dict[str, Any]]:
    import csv
    from pathlib import Path

    path = Path(csv_path)
    if not path.is_file():
        return []

    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            if index >= 5:
                break
            brakes = float(row.get("brakes_engaged_fraction", 0))
            rows.append(
                {
                    "rank": str(index + 1),
                    "kp": row["kp"],
                    "kd": row["kd"],
                    "deadband": row["error_deadband"],
                    "score": f"{float(row['score']):.2f}",
                    "mean_err": _fmt_m(float(row["mean_target_error"])),
                    "brakes": f"{brakes:.0%}",
                }
            )
    return rows
