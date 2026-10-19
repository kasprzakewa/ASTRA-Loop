from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import fields
from tkinter import messagebox

import customtkinter as ctk

from core.controllers.pd_controller import PDControllerParams
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

_FIELD_LABELS = {
    "target_apogee": "Target apogee [m]",
    "kp": "Kp",
    "kd": "Kd",
    "max_deploy_speed": "Max deploy speed [m/s]",
    "error_deadband": "Error deadband [m]",
}


class PDParamsDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        params: PDControllerParams,
        on_save: Callable[[PDControllerParams], None],
    ) -> None:
        super().__init__(parent)

        self._on_save = on_save
        self._entries: dict[str, ctk.CTkEntry] = {}

        self.title("PD Controller Parameters")
        self.geometry("460x380")
        self.minsize(460, 380)
        self.resizable(True, False)
        self.configure(fg_color=BG_DARK)
        self.transient(parent)
        self.grab_set()
        self.bind("<Return>", lambda _event: self._save())
        self.bind("<Escape>", lambda _event: self.destroy())

        header = ctk.CTkLabel(
            self,
            text="PD Controller Parameters",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        header.pack(padx=20, pady=(20, 12))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=20, pady=(0, 20))

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
            command=lambda: self._load_values(PDControllerParams()),
            fg_color=ACCENT_ORANGE,
            hover_color="#E08A4F",
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        form = ctk.CTkScrollableFrame(self, fg_color=SURFACE_GRAY, corner_radius=8)
        form.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        for model_field in fields(PDControllerParams):
            row = ctk.CTkFrame(form, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=6)

            label = ctk.CTkLabel(
                row,
                text=_FIELD_LABELS.get(
                    model_field.name, model_field.name.replace("_", " ").title()
                ),
                width=200,
                anchor="w",
                text_color=TEXT_MUTED,
            )
            label.pack(side="left")

            entry = ctk.CTkEntry(
                row, fg_color=FRAME_BORDER, border_color=GRID_COLOR, text_color=TEXT_PRIMARY
            )
            entry.insert(0, str(getattr(params, model_field.name)))
            entry.pack(side="right", fill="x", expand=True)
            entry.bind("<Return>", lambda _event: self._save())
            self._entries[model_field.name] = entry

        self.after(100, lambda: next(iter(self._entries.values())).focus_set())

    def _load_values(self, params: PDControllerParams) -> None:
        for name, entry in self._entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, str(getattr(params, name)))

    def _save(self) -> None:
        try:
            values = {name: float(entry.get()) for name, entry in self._entries.items()}
            updated = PDControllerParams(**values)
        except ValueError:
            messagebox.showerror("Invalid Input", "All parameters must be numeric.", parent=self)
            return

        if updated.max_deploy_speed <= 0.0:
            messagebox.showerror("Invalid Input", "Max deploy speed must be > 0.", parent=self)
            return

        self._on_save(updated)
        self.destroy()
