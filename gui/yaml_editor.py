"""Embedded YAML editor widget for calibration scenarios."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from gui.theme import (
    ACCENT_PINK,
    BG_DARK,
    DROPDOWN_HOVER,
    FRAME_BORDER,
    GRID_COLOR,
    SURFACE_GRAY,
    TEXT_MUTED,
    TEXT_PRIMARY,
)


def validate_yaml_text(text: str) -> str | None:
    try:
        import yaml

        yaml.safe_load(text)
        return None
    except Exception as exc:
        return str(exc)


class YamlEditorFrame(ctk.CTkFrame):
    """Edit and save a scenarios YAML file in-place."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        on_saved: Callable[[Path], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color=BG_DARK, **kwargs)
        self._on_saved = on_saved
        self._current_path: Path | None = None
        self._dirty = False

        self._path_label = ctk.CTkLabel(
            self,
            text="No scenarios file loaded",
            text_color=TEXT_MUTED,
            wraplength=820,
            justify="left",
        )
        self._path_label.pack(anchor="w", padx=4, pady=(4, 8))

        self._editor = ctk.CTkTextbox(
            self,
            fg_color=BG_DARK,
            border_color=GRID_COLOR,
            border_width=1,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none",
            activate_scrollbars=True,
        )
        self._editor.pack(fill="both", expand=True, pady=(0, 8))
        self._editor.bind("<KeyRelease>", self._mark_dirty)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x")

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
            text="Revert",
            command=self._revert,
            fg_color=SURFACE_GRAY,
            hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
            width=100,
        ).pack(side="right", padx=(0, 8))

    def load_path(self, path: Path) -> None:
        if not path.is_file():
            self._path_label.configure(text=f"File not found: {path}")
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Read error", str(exc), parent=self.winfo_toplevel())
            return

        self._current_path = path.resolve()
        self._path_label.configure(text=str(self._current_path))
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", text)
        self._dirty = False

    def is_dirty(self) -> bool:
        return self._dirty

    def confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        return bool(
            messagebox.askyesno(
                "Unsaved changes",
                "Discard unsaved scenario edits?",
                parent=self.winfo_toplevel(),
            )
        )

    def _editor_text(self) -> str:
        return self._editor.get("1.0", "end-1c")

    def _mark_dirty(self, _event: object = None) -> None:
        self._dirty = True

    def _save(self) -> None:
        if self._current_path is None:
            return

        text = self._editor_text()
        error = validate_yaml_text(text)
        if error:
            if not messagebox.askyesno(
                "YAML syntax error",
                f"{error}\n\nSave anyway?",
                parent=self.winfo_toplevel(),
            ):
                return

        try:
            self._current_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save error", str(exc), parent=self.winfo_toplevel())
            return

        self._dirty = False

        try:
            from core.calibration_scenarios import load_calibration_config

            load_calibration_config(self._current_path)
        except Exception as exc:
            messagebox.showwarning(
                "Saved with warnings",
                f"File saved, but scenario structure check failed:\n{exc}",
                parent=self.winfo_toplevel(),
            )
        else:
            messagebox.showinfo(
                "Saved",
                f"Scenarios saved:\n{self._current_path.name}",
                parent=self.winfo_toplevel(),
            )

        if self._on_saved is not None:
            self._on_saved(self._current_path)

    def _revert(self) -> None:
        if self._current_path is None:
            return
        if self._dirty and not messagebox.askyesno(
            "Revert",
            "Discard unsaved changes?",
            parent=self.winfo_toplevel(),
        ):
            return
        self.load_path(self._current_path)
