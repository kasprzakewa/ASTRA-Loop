"""Lightweight Markdown renderer for CustomTkinter guide panels."""

from __future__ import annotations

import re
from pathlib import Path

import customtkinter as ctk

from gui.theme import BG_DARK, FRAME_BORDER, GRID_COLOR, SURFACE_GRAY, TEXT_MUTED, TEXT_PRIMARY


class MarkdownView(ctk.CTkScrollableFrame):
    """Render a practical Markdown subset inside a scrollable frame."""

    def __init__(self, master: ctk.CTkBaseClass, **kwargs) -> None:
        super().__init__(master, fg_color=BG_DARK, **kwargs)
        self._heading_fonts = {
            1: ctk.CTkFont(size=20, weight="bold"),
            2: ctk.CTkFont(size=17, weight="bold"),
            3: ctk.CTkFont(size=14, weight="bold"),
        }
        self._body_font = ctk.CTkFont(size=13)
        self._mono_font = ctk.CTkFont(family="Consolas", size=12)
        self._muted_font = ctk.CTkFont(size=12)

    def load_file(self, path: Path) -> None:
        if path.is_file():
            self.load_text(path.read_text(encoding="utf-8"))
        else:
            self.load_text(f"*File not found:* `{path}`")

    def load_text(self, text: str) -> None:
        for child in self.winfo_children():
            child.destroy()

        blocks = _split_blocks(text)
        for block in blocks:
            self._render_block(block)

    def _render_block(self, block: dict) -> None:
        kind = block["kind"]
        if kind == "heading":
            level = block["level"]
            ctk.CTkLabel(
                self,
                text=block["text"],
                font=self._heading_fonts.get(level, self._heading_fonts[3]),
                text_color=TEXT_PRIMARY,
                anchor="w",
                justify="left",
                wraplength=860,
            ).pack(anchor="w", padx=8, pady=(14 if level == 1 else 10, 4))
        elif kind == "paragraph":
            ctk.CTkLabel(
                self,
                text=block["text"],
                font=self._body_font,
                text_color=TEXT_PRIMARY,
                anchor="w",
                justify="left",
                wraplength=860,
            ).pack(anchor="w", padx=8, pady=(0, 6))
        elif kind == "list":
            for item in block["items"]:
                ctk.CTkLabel(
                    self,
                    text=f"  •  {item}",
                    font=self._body_font,
                    text_color=TEXT_PRIMARY,
                    anchor="w",
                    justify="left",
                    wraplength=840,
                ).pack(anchor="w", padx=12, pady=1)
            ctk.CTkLabel(self, text="", height=4).pack()
        elif kind == "code":
            box = ctk.CTkTextbox(
                self,
                height=min(220, 24 + block["text"].count("\n") * 18),
                fg_color=FRAME_BORDER,
                border_color=GRID_COLOR,
                border_width=1,
                text_color=TEXT_PRIMARY,
                font=self._mono_font,
                wrap="none",
                activate_scrollbars=True,
            )
            box.pack(fill="x", padx=8, pady=(0, 8))
            box.insert("1.0", block["text"])
            box.configure(state="disabled")
        elif kind == "table":
            self._render_table(block["rows"])
        elif kind == "hr":
            sep = ctk.CTkFrame(self, height=1, fg_color=GRID_COLOR)
            sep.pack(fill="x", padx=8, pady=10)

    def _render_table(self, rows: list[list[str]]) -> None:
        if not rows:
            return
        frame = ctk.CTkFrame(self, fg_color=SURFACE_GRAY, corner_radius=6, border_width=1, border_color=GRID_COLOR)
        frame.pack(fill="x", padx=8, pady=(0, 10))

        for row_index, row in enumerate(rows):
            row_frame = ctk.CTkFrame(
                frame,
                fg_color=FRAME_BORDER if row_index == 0 else "transparent",
                corner_radius=0,
            )
            row_frame.pack(fill="x", padx=4, pady=1)
            for col_index, cell in enumerate(row):
                font = ctk.CTkFont(size=12, weight="bold") if row_index == 0 else self._muted_font
                color = TEXT_PRIMARY if row_index == 0 else TEXT_MUTED
                ctk.CTkLabel(
                    row_frame,
                    text=cell.strip(),
                    font=font,
                    text_color=color,
                    anchor="w",
                    width=140 if col_index == 0 else 120,
                ).grid(row=0, column=col_index, sticky="w", padx=6, pady=4)


def _strip_inline(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def _split_blocks(text: str) -> list[dict]:
    lines = text.splitlines()
    blocks: list[dict] = []
    index = 0

    while index < len(lines):
        line = lines[index]

        if line.strip() == "---":
            blocks.append({"kind": "hr"})
            index += 1
            continue

        if line.startswith("```"):
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            blocks.append({"kind": "code", "text": "\n".join(code_lines)})
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            blocks.append(
                {
                    "kind": "heading",
                    "level": len(heading_match.group(1)),
                    "text": _strip_inline(heading_match.group(2)),
                }
            )
            index += 1
            continue

        if "|" in line and index + 1 < len(lines) and re.match(r"^\s*\|?[\s\-:|]+\|?\s*$", lines[index + 1]):
            table_rows: list[list[str]] = []
            while index < len(lines) and "|" in lines[index]:
                if re.match(r"^\s*\|?[\s\-:|]+\|?\s*$", lines[index]):
                    index += 1
                    continue
                cells = [c.strip() for c in lines[index].strip().strip("|").split("|")]
                table_rows.append(cells)
                index += 1
            blocks.append({"kind": "table", "rows": table_rows})
            continue

        if re.match(r"^[\-\*]\s+", line):
            items: list[str] = []
            while index < len(lines) and re.match(r"^[\-\*]\s+", lines[index]):
                items.append(_strip_inline(re.sub(r"^[\-\*]\s+", "", lines[index])))
                index += 1
            blocks.append({"kind": "list", "items": items})
            continue

        if line.strip():
            para_lines = [line.strip()]
            index += 1
            while index < len(lines) and lines[index].strip() and not lines[index].startswith("#"):
                if lines[index].startswith("```") or re.match(r"^[\-\*]\s+", lines[index]):
                    break
                if "|" in lines[index]:
                    break
                para_lines.append(lines[index].strip())
                index += 1
            blocks.append({"kind": "paragraph", "text": _strip_inline(" ".join(para_lines))})
            continue

        index += 1

    return blocks
