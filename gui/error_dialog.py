from __future__ import annotations

from typing import Any

import customtkinter as ctk

from gui.theme import (
    ACCENT_ORANGE,
    ACCENT_PINK,
    BG_DARK,
    DROPDOWN_HOVER,
    GRID_COLOR,
    SURFACE_GRAY,
    TEXT_MUTED,
    TEXT_PRIMARY,
)


class ErrorDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        *,
        title: str,
        message: str,
        details: list[str],
        accent_color: str = ACCENT_PINK,
    ) -> None:
        super().__init__(parent)

        self.title(title)
        self.geometry("480x360")
        self.resizable(False, False)
        self.configure(fg_color=BG_DARK)
        self.transient(parent)
        self.grab_set()

        header = ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=accent_color,
        )
        header.pack(padx=20, pady=(20, 8), anchor="w")

        ctk.CTkLabel(
            self,
            text=message,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_PRIMARY,
            wraplength=440,
            justify="left",
        ).pack(padx=20, pady=(0, 12), anchor="w")

        details_box = ctk.CTkScrollableFrame(
            self,
            fg_color=SURFACE_GRAY,
            corner_radius=8,
            border_width=1,
            border_color=GRID_COLOR,
            height=180,
        )
        details_box.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        for detail in details:
            ctk.CTkLabel(
                details_box,
                text=f"• {detail}",
                anchor="w",
                justify="left",
                text_color=TEXT_MUTED,
                wraplength=400,
            ).pack(anchor="w", padx=12, pady=2)

        ctk.CTkButton(
            self,
            text="OK",
            command=self.destroy,
            fg_color=SURFACE_GRAY,
            hover_color=DROPDOWN_HOVER,
            border_width=1,
            border_color=GRID_COLOR,
            text_color=TEXT_PRIMARY,
            width=100,
        ).pack(pady=(0, 20))

    @classmethod
    def show(
        cls,
        parent: ctk.CTk,
        *,
        title: str,
        message: str,
        details: list[str],
        accent_color: str = ACCENT_PINK,
    ) -> None:
        cls(parent, title=title, message=message, details=details, accent_color=accent_color)
