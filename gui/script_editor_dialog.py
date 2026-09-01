from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
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
from gui.yaml_editor import validate_yaml_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Editable calibration / tuning files (label, path relative to project root).
EDITABLE_SCRIPTS: list[tuple[str, Path]] = [
    ("Scenarios YAML", PROJECT_ROOT / "data" / "calibration" / "scenarios.yaml"),
    ("Scenarios YAML guide", PROJECT_ROOT / "data" / "calibration" / "SCENARIOS_YAML.md"),
    ("tune_pd.py", PROJECT_ROOT / "scripts" / "tune_pd.py"),
    ("validate_pd.py", PROJECT_ROOT / "scripts" / "validate_pd.py"),
    ("Calibration README", PROJECT_ROOT / "data" / "calibration" / "README.md"),
]


def _validate_python(text: str) -> str | None:
    try:
        compile(text, "<editor>", "exec")
        return None
    except SyntaxError as exc:
        return f"Syntax error: {exc}"


class ScriptEditorDialog(ctk.CTkToplevel):
    """In-app text editor for YAML scenarios and calibration scripts."""

    def __init__(
        self,
        parent: ctk.CTk,
        *,
        initial_path: Path | None = None,
        on_saved: Callable[[Path], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._on_saved = on_saved
        self._current_path: Path | None = None
        self._dirty = False

        self.title("Script Editor")
        self.geometry("900x640")
        self.minsize(640, 480)
        self.configure(fg_color=BG_DARK)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        header = ctk.CTkLabel(
            self,
            text="Edit calibration scenarios and scripts",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        header.pack(padx=16, pady=(14, 8), anchor="w")

        picker = ctk.CTkFrame(self, fg_color=SURFACE_GRAY, corner_radius=8)
        picker.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(picker, text="File", text_color=TEXT_MUTED).pack(
            anchor="w", padx=12, pady=(10, 2)
        )

        row = ctk.CTkFrame(picker, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))

        preset_labels = [label for label, _ in EDITABLE_SCRIPTS]
        self._preset_var = tk.StringVar(value=preset_labels[0] if preset_labels else "")
        self._preset_menu = ctk.CTkOptionMenu(
            row,
            variable=self._preset_var,
            values=preset_labels or ["—"],
            command=self._on_preset_selected,
            fg_color=FRAME_BORDER,
            button_color=FRAME_BORDER,
            button_hover_color=DROPDOWN_HOVER,
            dropdown_fg_color=FRAME_BORDER,
            dropdown_hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
            width=200,
        )
        self._preset_menu.pack(side="left")

        ctk.CTkButton(
            row,
            text="Open preset",
            command=self._open_selected_preset,
            fg_color=SURFACE_GRAY,
            hover_color=DROPDOWN_HOVER,
            border_width=1,
            border_color=GRID_COLOR,
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            row,
            text="Browse…",
            command=self._browse_file,
            fg_color=SURFACE_GRAY,
            hover_color=DROPDOWN_HOVER,
            border_width=1,
            border_color=GRID_COLOR,
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(8, 0))

        self._path_label = ctk.CTkLabel(
            picker,
            text="No file loaded",
            text_color=TEXT_MUTED,
            wraplength=820,
            justify="left",
        )
        self._path_label.pack(anchor="w", padx=12, pady=(0, 10))

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
        self._editor.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._editor.bind("<KeyRelease>", self._mark_dirty)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=16, pady=(0, 14))

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
            text="Save As…",
            command=self._save_as,
            fg_color=ACCENT_ORANGE,
            hover_color="#E08A4F",
            text_color=TEXT_PRIMARY,
            width=100,
        ).pack(side="right", padx=(0, 8))

        ctk.CTkButton(
            buttons,
            text="Revert",
            command=self._revert,
            fg_color=SURFACE_GRAY,
            hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
            width=100,
        ).pack(side="right", padx=(0, 8))

        ctk.CTkButton(
            buttons,
            text="Close",
            command=self._on_close,
            fg_color=FRAME_BORDER,
            hover_color=DROPDOWN_HOVER,
            text_color=TEXT_PRIMARY,
            width=100,
        ).pack(side="left")

        if initial_path is not None and initial_path.is_file():
            self._load_file(initial_path)
        elif EDITABLE_SCRIPTS:
            self._open_selected_preset()

    def _preset_path(self, label: str) -> Path | None:
        for preset_label, path in EDITABLE_SCRIPTS:
            if preset_label == label:
                return path
        return None

    def _on_preset_selected(self, _value: str) -> None:
        pass

    def _open_selected_preset(self) -> None:
        path = self._preset_path(self._preset_var.get())
        if path is None:
            return
        if not self._confirm_discard():
            return
        if not path.is_file():
            messagebox.showerror("Missing file", f"File not found:\n{path}", parent=self)
            return
        self._load_file(path)

    def _browse_file(self) -> None:
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(
            title="Open script or YAML",
            initialdir=str(PROJECT_ROOT),
            filetypes=[
                ("Calibration files", "*.yaml *.yml *.py *.md"),
                ("YAML", "*.yaml *.yml"),
                ("Python", "*.py"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._load_file(Path(path))

    def _load_file(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Read error", str(exc), parent=self)
            return

        self._current_path = path.resolve()
        self._path_label.configure(text=str(self._current_path))
        self.title(f"Script Editor — {path.name}")

        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", text)
        self._dirty = False

        for label, preset_path in EDITABLE_SCRIPTS:
            if preset_path.resolve() == self._current_path:
                self._preset_var.set(label)
                break

    def _editor_text(self) -> str:
        return self._editor.get("1.0", "end-1c")

    def _mark_dirty(self, _event: object = None) -> None:
        self._dirty = True

    def _validate_before_save(self, path: Path, text: str) -> bool:
        if path.suffix == ".py":
            error = _validate_python(text)
            if error:
                return bool(
                    messagebox.askyesno(
                        "Python syntax error",
                        f"{error}\n\nSave anyway?",
                        parent=self,
                    )
                )
            return True

        if path.suffix in {".yaml", ".yml"}:
            error = validate_yaml_text(text)
            if error:
                return bool(
                    messagebox.askyesno(
                        "YAML syntax error",
                        f"{error}\n\nSave anyway?",
                        parent=self,
                    )
                )
        return True

    def _save(self) -> None:
        if self._current_path is None:
            self._save_as()
            return

        text = self._editor_text()
        if not self._validate_before_save(self._current_path, text):
            return

        try:
            self._current_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save error", str(exc), parent=self)
            return

        self._dirty = False
        if self._on_saved is not None:
            self._on_saved(self._current_path)

        if self._current_path.suffix in {".yaml", ".yml"}:
            try:
                from core.calibration_scenarios import load_calibration_config

                load_calibration_config(self._current_path)
            except Exception as exc:
                messagebox.showwarning(
                    "Saved with warnings",
                    f"File saved, but scenario structure check failed:\n{exc}",
                    parent=self,
                )
                return

        messagebox.showinfo("Saved", f"Saved:\n{self._current_path}", parent=self)

    def _save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save script as",
            initialdir=str(self._current_path.parent if self._current_path else PROJECT_ROOT),
            initialfile=self._current_path.name if self._current_path else "scenarios.yaml",
            defaultextension=".yaml",
            filetypes=[
                ("YAML", "*.yaml"),
                ("Python", "*.py"),
                ("Markdown", "*.md"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        self._current_path = Path(path).resolve()
        self._path_label.configure(text=str(self._current_path))
        self.title(f"Script Editor — {self._current_path.name}")
        self._save()

    def _revert(self) -> None:
        if self._current_path is None:
            return
        if self._dirty and not messagebox.askyesno(
            "Revert",
            "Discard unsaved changes?",
            parent=self,
        ):
            return
        self._load_file(self._current_path)

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        return bool(
            messagebox.askyesno(
                "Unsaved changes",
                "Discard unsaved changes?",
                parent=self,
            )
        )

    def _on_close(self) -> None:
        if self._confirm_discard():
            self.destroy()


def open_script_editor(
    parent: ctk.CTk,
    *,
    initial_path: Path | None = None,
    on_saved: Callable[[Path], None] | None = None,
) -> ScriptEditorDialog:
    return ScriptEditorDialog(parent, initial_path=initial_path, on_saved=on_saved)
