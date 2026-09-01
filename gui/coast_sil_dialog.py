from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, fields
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

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


@dataclass
class CoastSilParams:
    wind_speed: float = 0.0
    gust_strength: float = 0.0
    plant_mass_scale: float = 1.0
    plant_cd_scale: float = 1.0


_FIELD_LABELS = {
    "wind_speed": "Wind speed [m/s]",
    "gust_strength": "Gust strength (vertical) [m/s]",
    "plant_mass_scale": "Plant mass scale (truth/model)",
    "plant_cd_scale": "Plant Cd scale (truth/model)",
}


class CoastSilParamsDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        params: CoastSilParams,
        on_save: Callable[[CoastSilParams], None],
    ) -> None:
        super().__init__(parent)

        self._on_save = on_save
        self._entries: dict[str, ctk.CTkEntry] = {}

        self.title("Coast SIL Parameters")
        self.geometry("460x360")
        self.resizable(False, False)
        self.configure(fg_color=BG_DARK)
        self.transient(parent)
        self.grab_set()

        header = ctk.CTkLabel(
            self,
            text="Coast SIL Parameters",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        header.pack(padx=20, pady=(20, 4))

        ctk.CTkLabel(
            self,
            text="Plant disturbances for closed-loop coast (predictor stays ideal).",
            text_color=TEXT_MUTED,
            wraplength=400,
            justify="left",
        ).pack(padx=20, pady=(0, 12), anchor="w")

        form = ctk.CTkFrame(self, fg_color=SURFACE_GRAY, corner_radius=8)
        form.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        for model_field in fields(CoastSilParams):
            row = ctk.CTkFrame(form, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=8)

            label = ctk.CTkLabel(
                row,
                text=_FIELD_LABELS.get(model_field.name, model_field.name),
                width=220,
                anchor="w",
                text_color=TEXT_MUTED,
            )
            label.pack(side="left")

            entry = ctk.CTkEntry(
                row, fg_color=FRAME_BORDER, border_color=GRID_COLOR, text_color=TEXT_PRIMARY
            )
            entry.insert(0, str(getattr(params, model_field.name)))
            entry.pack(side="right", fill="x", expand=True)
            self._entries[model_field.name] = entry

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkButton(
            buttons,
            text="Cancel",
            command=self.destroy,
            fg_color=FRAME_BORDER,
            hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
            width=100,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            buttons,
            text="Save",
            command=self._save,
            fg_color=ACCENT_PINK,
            hover_color="#D9436A",
            text_color=TEXT_PRIMARY,
            width=100,
        ).pack(side="right")

        ctk.CTkButton(
            buttons,
            text="Reset Defaults",
            command=lambda: self._load_values(CoastSilParams()),
            fg_color=ACCENT_ORANGE,
            hover_color="#E08A4F",
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

    def _load_values(self, params: CoastSilParams) -> None:
        for name, entry in self._entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, str(getattr(params, name)))

    def _save(self) -> None:
        try:
            values = {name: float(entry.get()) for name, entry in self._entries.items()}
            updated = CoastSilParams(**values)
        except ValueError:
            messagebox.showerror("Invalid Input", "All parameters must be numeric.", parent=self)
            return

        if updated.plant_mass_scale <= 0.0 or updated.plant_cd_scale <= 0.0:
            messagebox.showerror("Invalid Input", "Plant mass/Cd scales must be > 0.", parent=self)
            return

        self._on_save(updated)
        self.destroy()
