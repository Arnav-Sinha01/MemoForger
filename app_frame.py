"""
app_frame.py
============
MemoForge — Module 3: Application Frame & Upload Hub
------------------------------------------------------
Responsibility: Render the main application window, accept document uploads
via drag-and-drop or file picker, display per-file status, collect generation
configuration from the user, and hand a fully-constructed GenerationConfig +
file paths list off to the pipeline layer (Module 5).

This module has ZERO knowledge of inference. The "Generate" button currently
prints a console summary — Module 5 will replace that stub with real threading.

Design Language: "Academic Brutalism"
--------------------------------------
Inspired by the raw physicality of a researcher's desk — exposed structure,
deliberate imperfection, ink-on-paper contrast, and zero decorative fluff.
Colour palette: deep graphite background, cream/off-white text, amber accent,
warm red error state. Typography: monospace headings (Courier New) for the
"working document" feel; clean sans-serif (Trebuchet MS) for body copy.

Dependencies
------------
    pip install customtkinter

Layout (annotated wireframe)
-----------------------------
┌─────────────────────────────────────────────────────────────────┐
│  ░ MEMOFORGE                               [light/dark toggle]  │  ← TitleBar
├──────────────────────────┬──────────────────────────────────────┤
│                          │                                      │
│   DROP ZONE              │   CONFIGURATION PANEL                │
│   ┌──────────────────┐   │   ┌──────────────────────────────┐   │
│   │  ⊕  Drop files   │   │   │  Task Mode   [▼ BOTH       ] │   │
│   │     here or      │   │   │  Max cards   [────●──────── ] │   │
│   │     click        │   │   │  Summary     [──●────────── ] │   │
│   └──────────────────┘   │   │  Temperature [────●──────── ] │   │
│                          │   │  Max tokens  [entry        ] │   │
│   FILE QUEUE             │   └──────────────────────────────┘   │
│   ┌──────────────────┐   │                                      │
│   │  doc.pdf  ✓      │   │   ┌──────────────────────────────┐   │
│   │  notes.docx ✓    │   │   │  [  ⚡  GENERATE FLASHCARDS ] │   │
│   │  data.xlsx ✗     │   │   └──────────────────────────────┘   │
│   └──────────────────┘   │                                      │
│                          │   STATUS BAR                         │
│   [CLEAR ALL]            │   ▓▓▓▓▓▓▓▓░░░░  4/7 chunks          │
│                          │                                      │
└──────────────────────────┴──────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import os
import sys
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

import customtkinter as ctk
from tkinter import filedialog, StringVar, IntVar, DoubleVar, BooleanVar
import tkinter as tk

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _HAS_DND = True
except ImportError:
    _HAS_DND = False

if _HAS_DND:
    class _BaseApp(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    class _BaseApp(ctk.CTk):
        pass

# ---------------------------------------------------------------------------
# Module-level logger — the UI does NOT configure logging itself; the
# application entry point at the bottom sets up basicConfig for dev runs.
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

_SETTINGS_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "MemoForge"
_SETTINGS_PATH = _SETTINGS_DIR / "ui_settings.json"
_DEFAULT_UI_SETTINGS: Dict[str, object] = {
    "appearance_mode": "Dark",
    "output_mode": "Flashcards + Summary",
    "model_id": "qwen3-vl:2b",
    "max_flashcards": 8,
    "summary_sentences": 5,
    "temperature": 0.3,
    "max_new_tokens": 1024,
    "vision_render_dpi": 150,
    "retry_on_parse_failure": True,
}

# ---------------------------------------------------------------------------
# Interface stubs for the backend modules.
# Module 5 will replace these imports with the real ones.
# ---------------------------------------------------------------------------
try:
    from vlm_pipeline import GenerationConfig, TaskType
except ImportError:
    # Graceful degradation so the UI can be developed / demoed without
    # the heavy ML stack installed.
    from enum import Enum, auto
    from dataclasses import dataclass, field

    class TaskType(Enum):
        FLASHCARDS = auto()   # vlm_pipeline.TaskType.FLASHCARDS
        SUMMARY    = auto()   # vlm_pipeline.TaskType.SUMMARY
        COMBINED   = auto()   # vlm_pipeline.TaskType.COMBINED (was BOTH — corrected)

    @dataclass
    class GenerationConfig:
        # Field names mirror the real GenerationConfig in vlm_pipeline.py.
        model_id:              str      = "qwen3-vl:2b"
        task_type:             TaskType = TaskType.COMBINED
        max_flashcards:        int      = 8
        max_new_tokens:        int      = 1024
        temperature:           float    = 0.3
        top_p:                 float    = 0.9
        repetition_penalty:    float    = 1.1
        summary_max_sentences: int      = 5
        vision_render_dpi:     int      = 150
        max_workers:           int      = 1
        retry_on_parse_failure: bool    = True
        anki_export:           bool     = False  # True only for Anki Deck Only

    logger.warning(
        "vlm_pipeline not found — running with stub types. "
        "Install Module 2 dependencies before production use."
    )


# ============================================================
# Design tokens
# ============================================================

class _Theme:
    """
    All visual constants live here.  The rest of the code references these
    names, never raw hex strings, so a palette swap is a one-file change.

    Every colour is a (dark_mode, light_mode) tuple.  CustomTkinter natively
    resolves these when appearance mode changes — no manual propagation needed.
    """

    # --- Colour palette: (dark, light) ---
    BG_ROOT        = ("#0d1117", "#ffffff")   # Premium dark / clean white
    BG_PANEL       = ("#161b22", "#f6f8fa")   # Sidebar / Panel
    BG_CARD        = ("#21262d", "#ffffff")   # Card / Input
    BG_DROPZONE    = ("#0d1117", "#f6f8fa")   # Dropzone
    BG_DROPZONE_HV = ("#1f2428", "#e1e4e8")   # Dropzone Hover

    ACCENT         = ("#2f81f7", "#0969da")   # Vibrant Blue
    ACCENT_HOVER   = ("#58a6ff", "#0550ae")
    ACCENT_PRESS   = ("#1f6feb", "#033d8b")

    TEXT_PRIMARY   = ("#e6edf3", "#24292f")
    TEXT_SECONDARY = ("#8b949e", "#57606a")
    TEXT_MONO      = ("#f0f6fc", "#24292f")

    SUCCESS        = ("#2ea043", "#1a7f37")
    ERROR          = ("#f85149", "#cf222e")
    WARNING        = ("#d29922", "#bf8700")

    BORDER         = ("#30363d", "#d0d7de")
    BORDER_FOCUS   = ("#58a6ff", "#0969da")

    BTN_TEXT_ON_ACCENT = ("#ffffff", "#ffffff")

    # --- Typography ---
    FONT_DISPLAY   = ("Segoe UI", 24, "bold")
    FONT_HEADING   = ("Segoe UI", 12, "bold")
    FONT_SUBHEAD   = ("Segoe UI", 12, "bold")
    FONT_BODY      = ("Segoe UI", 12)
    FONT_SMALL     = ("Segoe UI", 11)
    FONT_MONO      = ("Consolas", 11)
    FONT_BTN       = ("Segoe UI", 13, "bold")

    # --- Geometry ---
    CORNER_RADIUS  = 8    # modern rounded corners
    PAD_OUTER      = 24   # outer window padding
    PAD_INNER      = 16   # internal component padding
    PAD_SMALL      = 8    # tight gaps
    BTN_HEIGHT     = 44
    DROPZONE_H     = 180
    FILE_ROW_H     = 44
    SIDEBAR_W      = 340  # config panel fixed width


# ============================================================
# Supported file formats (mirrors ingestion_engine.py)
# ============================================================

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx", ".xlsx", ".pptx"}
EXTENSION_ICONS = {
    ".pdf":  "PDF",
    ".txt":  "TXT",
    ".docx": "DOC",
    ".xlsx": "XLS",
    ".pptx": "PPT",
}


# ============================================================
# FileEntry — represents one queued document
# ============================================================

class FileStatus:
    PENDING  = "pending"
    READY    = "ready"
    ERROR    = "error"


class FileEntry:
    """
    Lightweight data record for one file in the upload queue.

    Not a widget — the UI layer creates FileRowWidget instances that
    hold references to these objects.
    """

    def __init__(self, path: Path) -> None:
        self.path     = path
        self.name     = path.name
        self.ext      = path.suffix.lower()
        self.size_kb  = self._compute_size()
        self.status   = FileStatus.READY if self.ext in SUPPORTED_EXTENSIONS else FileStatus.ERROR
        self.message  = "" if self.status == FileStatus.READY else (
            f"Unsupported format '{self.ext}'"
        )

    def _compute_size(self) -> float:
        try:
            return self.path.stat().st_size / 1024
        except OSError:
            return 0.0

    @property
    def size_label(self) -> str:
        if self.size_kb < 1024:
            return f"{self.size_kb:.0f} KB"
        return f"{self.size_kb / 1024:.1f} MB"


# ============================================================
# FileRowWidget — one row in the file queue scrollable list
# ============================================================

class FileRowWidget(ctk.CTkFrame):
    """
    A single file entry rendered as a compact row card.

    Displays: [TYPE BADGE] [filename] [size] [status icon] [✕ remove]
    """

    def __init__(
        self,
        parent,
        entry: FileEntry,
        on_remove: Callable[[FileEntry], None],
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            fg_color    = _Theme.BG_CARD,
            corner_radius = _Theme.CORNER_RADIUS,
            **kwargs,
        )

        self.entry     = entry
        self.on_remove = on_remove

        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)

        # --- Type badge ---
        badge_color = (
            _Theme.ACCENT   if self.entry.status == FileStatus.READY else
            _Theme.ERROR
        )
        badge = ctk.CTkLabel(
            self,
            text         = EXTENSION_ICONS.get(self.entry.ext, "???"),
            font         = ("Courier New", 9, "bold"),
            text_color   = _Theme.BTN_TEXT_ON_ACCENT,  # always dark on coloured badge
            fg_color     = badge_color,
            corner_radius = 2,
            width        = 32,
            height       = 20,
        )
        badge.grid(row=0, column=0, padx=(8, 6), pady=10, sticky="w")

        # --- Filename ---
        # Truncate long names gracefully
        display_name = self.entry.name
        if len(display_name) > 36:
            display_name = display_name[:33] + "…"

        name_label = ctk.CTkLabel(
            self,
            text       = display_name,
            font       = _Theme.FONT_MONO,
            text_color = _Theme.TEXT_PRIMARY if self.entry.status == FileStatus.READY
                         else _Theme.ERROR,
            anchor     = "w",
        )
        name_label.grid(row=0, column=1, padx=(0, 8), sticky="ew")

        # --- Size or error message ---
        meta_text  = self.entry.message if self.entry.status == FileStatus.ERROR \
                     else self.entry.size_label
        meta_color = _Theme.ERROR if self.entry.status == FileStatus.ERROR \
                     else _Theme.TEXT_SECONDARY

        meta_label = ctk.CTkLabel(
            self,
            text       = meta_text,
            font       = _Theme.FONT_SMALL,
            text_color = meta_color,
            width      = 70,
            anchor     = "e",
        )
        meta_label.grid(row=0, column=2, padx=(0, 6), sticky="e")

        # --- Remove button ---
        remove_btn = ctk.CTkButton(
            self,
            text          = "✕",
            font          = ("Trebuchet MS", 11, "bold"),
            width         = 26,
            height        = 26,
            corner_radius = 2,
            fg_color      = "transparent",
            hover_color   = _Theme.BG_DROPZONE_HV,
            text_color    = _Theme.TEXT_SECONDARY,
            border_width  = 0,
            command       = lambda: self.on_remove(self.entry),
        )
        remove_btn.grid(row=0, column=3, padx=(0, 6), sticky="e")


# ============================================================
# DropZone — the central file-drop target
# ============================================================

class DropZoneWidget(ctk.CTkFrame):
    """
    A bordered rectangle that accepts click-to-browse and (on supported
    platforms) drag-and-drop of document files.

    Drag-and-drop is implemented via tkinterdnd2 when available.
    The widget degrades gracefully to click-only if tkinterdnd2 is absent.
    """

    def __init__(
        self,
        parent,
        on_files_added: Callable[[List[Path]], None],
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            fg_color      = _Theme.BG_DROPZONE,
            corner_radius = _Theme.CORNER_RADIUS,
            border_width  = 2,
            border_color  = _Theme.BORDER,
            **kwargs,
        )

        self.on_files_added = on_files_added
        self._dragging      = False

        self._build()
        self._bind_events()

    def _build(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Central content stack (icon + instructions)
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=0)

        # Large upload glyph — hand-crafted from ASCII to avoid image deps
        self._icon_label = ctk.CTkLabel(
            content,
            text       = "⊕",
            font       = ("Courier New", 48),
            text_color = _Theme.ACCENT,
        )
        self._icon_label.pack(pady=(0, 8))

        self._main_label = ctk.CTkLabel(
            content,
            text       = "DROP FILES HERE",
            font       = _Theme.FONT_HEADING,
            text_color = _Theme.TEXT_PRIMARY,
        )
        self._main_label.pack()

        self._sub_label = ctk.CTkLabel(
            content,
            text       = "or click to browse  ·  PDF · DOCX · XLSX · PPTX · TXT",
            font       = _Theme.FONT_SMALL,
            text_color = _Theme.TEXT_SECONDARY,
        )
        self._sub_label.pack(pady=(4, 0))

    def _bind_events(self) -> None:
        # Click to open file picker
        self.bind("<Button-1>", self._on_click)
        for child in self.winfo_children():
            child.bind("<Button-1>", self._on_click)
            # Recursively bind nested labels
            for grandchild in child.winfo_children():
                grandchild.bind("<Button-1>", self._on_click)

        # Hover effect
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

        # Attempt to register drag-and-drop via tkinterdnd2
        self._setup_dnd()

    def _setup_dnd(self) -> None:
        """Register DnD handlers if tkinterdnd2 is available."""
        if not globals().get("_HAS_DND"):
            logger.debug("tkinterdnd2 not available — DnD disabled, click-to-browse still works.")
            return

        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<DropEnter>>", self._on_dnd_enter)
            self.dnd_bind("<<DropLeave>>", self._on_dnd_leave)
            self.dnd_bind("<<Drop>>",      self._on_dnd_drop)
            logger.debug("Drag-and-drop registered successfully.")
        except Exception as e:
            logger.error(f"DnD registration failed: {e}")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_click(self, _event=None) -> None:
        paths = self._open_file_dialog()
        if paths:
            self.on_files_added(paths)

    def _on_enter(self, _event=None) -> None:
        self.configure(fg_color=_Theme.BG_DROPZONE_HV, border_color=_Theme.ACCENT)

    def _on_leave(self, _event=None) -> None:
        if not self._dragging:
            self.configure(fg_color=_Theme.BG_DROPZONE, border_color=_Theme.BORDER)

    def _on_dnd_enter(self, _event=None) -> None:
        self._dragging = True
        self.configure(fg_color=_Theme.BG_DROPZONE_HV, border_color=_Theme.ACCENT)

    def _on_dnd_leave(self, _event=None) -> None:
        self._dragging = False
        self.configure(fg_color=_Theme.BG_DROPZONE, border_color=_Theme.BORDER)

    def _on_dnd_drop(self, event) -> None:
        self._dragging = False
        self.configure(fg_color=_Theme.BG_DROPZONE, border_color=_Theme.BORDER)

        raw = event.data  # space-separated paths; curly-braced if they contain spaces
        paths = self._parse_dnd_paths(raw)
        if paths:
            self.on_files_added(paths)

    @staticmethod
    def _parse_dnd_paths(raw: str) -> List[Path]:
        """
        Parse the raw DnD path string from tkinterdnd2.

        tkinterdnd2 returns paths as a Tcl list:
          - Plain paths are space-separated.
          - Paths with spaces are wrapped in {curly braces}.
        """
        paths: List[Path] = []
        # Split on spaces that are NOT inside curly braces
        i = 0
        tokens: List[str] = []
        current = ""
        depth = 0
        while i < len(raw):
            c = raw[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    tokens.append(current.strip())
                    current = ""
                    i += 1
                    continue
            elif c == " " and depth == 0:
                if current.strip():
                    tokens.append(current.strip())
                current = ""
                i += 1
                continue
            if depth > 0:
                current += c
            elif c != "{":
                current += c
            i += 1
        if current.strip():
            tokens.append(current.strip())

        for token in tokens:
            p = Path(token)
            if p.exists() and p.is_file():
                paths.append(p)
        return paths

    @staticmethod
    def _open_file_dialog() -> List[Path]:
        """Open a native multi-file picker filtered to supported formats."""
        raw_paths = filedialog.askopenfilenames(
            title      = "Select Documents for MemoForge",
            filetypes  = [
                ("Supported Documents", "*.pdf *.docx *.xlsx *.pptx *.txt"),
                ("PDF Files",           "*.pdf"),
                ("Word Documents",      "*.docx"),
                ("Excel Spreadsheets",  "*.xlsx"),
                ("PowerPoint Decks",    "*.pptx"),
                ("Plain Text",          "*.txt"),
                ("All Files",           "*.*"),
            ],
        )
        return [Path(p) for p in raw_paths]


# ============================================================
# FileQueuePanel — scrollable list of queued documents
# ============================================================

class FileQueuePanel(ctk.CTkFrame):
    """
    The scrollable file list below the drop zone.

    Maintains an ordered list of FileEntry objects and renders one
    FileRowWidget per entry.  Exposes add_files() and clear() to the parent.
    """

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(
            parent,
            fg_color      = "transparent",
            **kwargs,
        )

        self._entries:  List[FileEntry]           = []
        self._rows:     Dict[str, FileRowWidget]  = {}  # keyed by str(path)

        self._build()

    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Section heading row ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, _Theme.PAD_SMALL))
        header_frame.grid_columnconfigure(0, weight=1)

        self._heading = ctk.CTkLabel(
            header_frame,
            text       = "DOCUMENT QUEUE",
            font       = _Theme.FONT_HEADING,
            text_color = _Theme.TEXT_SECONDARY,
            anchor     = "w",
        )
        self._heading.grid(row=0, column=0, sticky="w")

        self._count_label = ctk.CTkLabel(
            header_frame,
            text       = "0 files",
            font       = _Theme.FONT_SMALL,
            text_color = _Theme.TEXT_SECONDARY,
            anchor     = "e",
        )
        self._count_label.grid(row=0, column=1, sticky="e")

        # Thin separator line
        sep = ctk.CTkFrame(
            self,
            height        = 1,
            fg_color      = _Theme.BORDER,
            corner_radius = 0,
        )
        sep.grid(row=1, column=0, sticky="ew", pady=(0, _Theme.PAD_SMALL))

        # --- Scrollable list ---
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color      = "transparent",
            scrollbar_button_color = _Theme.BORDER,
            scrollbar_button_hover_color = _Theme.ACCENT,
        )
        self._scroll.grid(row=2, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        # --- Clear all button ---
        self._clear_btn = ctk.CTkButton(
            self,
            text          = "CLEAR ALL",
            font          = _Theme.FONT_MONO,
            height        = 28,
            corner_radius = _Theme.CORNER_RADIUS,
            fg_color      = "transparent",
            border_width  = 1,
            border_color  = _Theme.BORDER,
            hover_color   = _Theme.BG_CARD,
            text_color    = _Theme.TEXT_SECONDARY,
            command       = self.clear,
        )
        self._clear_btn.grid(row=3, column=0, sticky="ew", pady=(_Theme.PAD_SMALL, 0))
        self._update_clear_btn_visibility()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def add_files(self, paths: List[Path]) -> int:
        """
        Add files to the queue.  Duplicate paths are silently skipped.

        Returns the number of files actually added.
        """
        added = 0
        for path in paths:
            key = str(path.resolve())
            if key in self._rows:
                logger.debug("Duplicate file skipped: %s", path.name)
                continue

            entry = FileEntry(path)
            self._entries.append(entry)

            row = FileRowWidget(
                self._scroll,
                entry     = entry,
                on_remove = self._remove_entry,
            )
            row.grid(
                row    = len(self._rows),
                column = 0,
                sticky = "ew",
                pady   = (0, 3),
                padx   = 0,
            )
            self._rows[key] = row
            added += 1

        self._refresh_count()
        self._update_clear_btn_visibility()
        return added

    def clear(self) -> None:
        """Remove all entries from the queue."""
        for row in self._rows.values():
            row.destroy()
        self._entries.clear()
        self._rows.clear()
        self._refresh_count()
        self._update_clear_btn_visibility()

    @property
    def ready_paths(self) -> List[Path]:
        """Return only the files that passed format validation."""
        return [e.path for e in self._entries if e.status == FileStatus.READY]

    @property
    def total_count(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _remove_entry(self, entry: FileEntry) -> None:
        key = str(entry.path.resolve())
        if key in self._rows:
            self._rows[key].destroy()
            del self._rows[key]
        self._entries = [e for e in self._entries if str(e.path.resolve()) != key]
        # Re-grid remaining rows with consecutive indices
        for idx, row in enumerate(self._rows.values()):
            row.grid(row=idx, column=0, sticky="ew", pady=(0, 3))
        self._refresh_count()
        self._update_clear_btn_visibility()

    def _refresh_count(self) -> None:
        n        = len(self._entries)
        ready    = sum(1 for e in self._entries if e.status == FileStatus.READY)
        label    = f"{n} file{'s' if n != 1 else ''}"
        if n > 0 and ready < n:
            label += f"  ·  {n - ready} unsupported"
        self._count_label.configure(text=label)

    def _update_clear_btn_visibility(self) -> None:
        if self._entries:
            self._clear_btn.grid()
        else:
            self._clear_btn.grid_remove()


# ============================================================
# ConfigPanel — right-side generation settings
# ============================================================

class ConfigPanel(ctk.CTkFrame):
    """
    All user-configurable generation parameters in one panel.

    Exposes a single get_config() method that constructs and returns
    a fully-populated GenerationConfig ready to hand to Module 5.
    """

    # Slider ranges
    TEMP_MIN, TEMP_MAX   = 0.0,  1.0
    CARDS_MIN, CARDS_MAX = 1,    20
    SENT_MIN,  SENT_MAX  = 1,    12
    TOK_MIN,   TOK_MAX   = 256, 2048

    def __init__(self, parent, initial_state: Optional[Dict[str, object]] = None, **kwargs) -> None:
        super().__init__(
            parent,
            fg_color      = _Theme.BG_PANEL,
            corner_radius = _Theme.CORNER_RADIUS,
            border_width  = 1,
            border_color  = _Theme.BORDER,
            **kwargs,
        )
        self.grid_columnconfigure(0, weight=1)

        state = dict(_DEFAULT_UI_SETTINGS)
        if isinstance(initial_state, dict):
            state.update(initial_state)

        mode_options = {"Flashcards + Summary", "Flashcards Only", "Summary Only", "Anki Deck Only"}
        output_mode = str(state.get("output_mode", _DEFAULT_UI_SETTINGS["output_mode"])).strip()
        if output_mode not in mode_options:
            output_mode = str(_DEFAULT_UI_SETTINGS["output_mode"])

        model_id = str(state.get("model_id", _DEFAULT_UI_SETTINGS["model_id"])).strip() or "qwen3-vl:2b"

        def _int_value(key: str, default: int, low: int, high: int) -> int:
            try:
                return max(low, min(high, int(state.get(key, default))))
            except (TypeError, ValueError):
                return default

        def _float_value(key: str, default: float, low: float, high: float) -> float:
            try:
                return max(low, min(high, float(state.get(key, default))))
            except (TypeError, ValueError):
                return default

        # State variables (created before _build so widgets can bind to them)
        self._task_var      = StringVar(value=output_mode)
        self._model_var     = StringVar(value=model_id)
        self._cards_var     = IntVar(value=_int_value("max_flashcards", 8, self.CARDS_MIN, self.CARDS_MAX))
        self._summary_var   = IntVar(value=_int_value("summary_sentences", 5, self.SENT_MIN, self.SENT_MAX))
        self._temp_var      = DoubleVar(value=_float_value("temperature", 0.3, self.TEMP_MIN, self.TEMP_MAX))
        self._tokens_var    = StringVar(
            value=str(_int_value("max_new_tokens", 1024, self.TOK_MIN, self.TOK_MAX))
        )
        self._vision_dpi    = IntVar(value=_int_value("vision_render_dpi", 150, 72, 300))
        self._vision_dpi_var = StringVar(value=str(self._vision_dpi.get()))
        self._retry_var     = BooleanVar(value=bool(state.get("retry_on_parse_failure", True)))

        self._build()

    def _build(self) -> None:
        row = 0

        # === Section heading ===
        heading = ctk.CTkLabel(
            self,
            text       = "GENERATION CONFIG",
            font       = _Theme.FONT_HEADING,
            text_color = _Theme.ACCENT,
            anchor     = "w",
        )
        heading.grid(row=row, column=0, sticky="ew",
                     padx=_Theme.PAD_INNER, pady=(_Theme.PAD_INNER, _Theme.PAD_SMALL))
        row += 1

        sep = ctk.CTkFrame(self, height=1, fg_color=_Theme.BORDER, corner_radius=0)
        sep.grid(row=row, column=0, sticky="ew",
                 padx=_Theme.PAD_INNER, pady=(0, _Theme.PAD_INNER))
        row += 1

        # === Task mode ===
        row = self._add_label(row, "OUTPUT MODE")
        self._task_menu = ctk.CTkOptionMenu(
            self,
            values        = ["Flashcards + Summary", "Flashcards Only", "Summary Only", "Anki Deck Only"],
            variable      = self._task_var,
            font          = _Theme.FONT_BODY,
            dropdown_font = _Theme.FONT_BODY,
            fg_color      = _Theme.BG_CARD,
            button_color  = _Theme.ACCENT,
            button_hover_color = _Theme.ACCENT_HOVER,
            text_color    = _Theme.TEXT_PRIMARY,
            corner_radius = _Theme.CORNER_RADIUS,
            anchor        = "w",
            dynamic_resizing = False,
            width         = 210,
        )
        self._task_menu.grid(row=row, column=0, sticky="ew",
                             padx=_Theme.PAD_INNER, pady=(0, _Theme.PAD_INNER))
        row += 1

        # === Ollama model selector ===
        row = self._add_label(row, "OLLAMA MODEL")
        model_row = ctk.CTkFrame(self, fg_color="transparent")
        model_row.grid(row=row, column=0, sticky="ew",
                       padx=_Theme.PAD_INNER, pady=(0, _Theme.PAD_INNER))
        model_row.grid_columnconfigure(0, weight=1)

        model_values = self._fetch_ollama_models()
        if not model_values:
            model_values = ["qwen3-vl:2b"]
        if self._model_var.get() not in model_values:
            model_values.insert(0, self._model_var.get())

        self._model_combo = ctk.CTkComboBox(
            model_row,
            values=model_values,
            variable=self._model_var,
            font=_Theme.FONT_BODY,
            fg_color=_Theme.BG_CARD,
            border_color=_Theme.BORDER,
            text_color=_Theme.TEXT_PRIMARY,
            button_color=_Theme.ACCENT,
            button_hover_color=_Theme.ACCENT_HOVER,
            dropdown_fg_color=_Theme.BG_PANEL,
            dropdown_text_color=_Theme.TEXT_PRIMARY,
            dropdown_hover_color=_Theme.BG_DROPZONE_HV,
            corner_radius=_Theme.CORNER_RADIUS,
            height=34,
        )
        self._model_combo.grid(row=0, column=0, sticky="ew")

        self._refresh_models_btn = ctk.CTkButton(
            model_row,
            text="REFRESH",
            font=("Courier New", 9, "bold"),
            width=86,
            height=34,
            corner_radius=_Theme.CORNER_RADIUS,
            fg_color="transparent",
            hover_color=_Theme.BG_DROPZONE_HV,
            text_color=_Theme.TEXT_SECONDARY,
            border_width=1,
            border_color=_Theme.BORDER,
            command=self._refresh_models,
        )
        self._refresh_models_btn.grid(row=0, column=1, padx=(8, 0), sticky="e")
        row += 1

        # === Max flashcards slider ===
        row = self._add_label(row, "MAX FLASHCARDS PER CHUNK")
        self._cards_frame, self._cards_val_label = self._add_slider(
            row,
            var   = self._cards_var,
            from_ = self.CARDS_MIN,
            to    = self.CARDS_MAX,
            steps = self.CARDS_MAX - self.CARDS_MIN,
            fmt   = lambda v: str(int(v)),
        )
        row += 1

        # === Summary length slider ===
        row = self._add_label(row, "SUMMARY LENGTH  (sentences)")
        self._summary_frame, self._summary_val_label = self._add_slider(
            row,
            var   = self._summary_var,
            from_ = self.SENT_MIN,
            to    = self.SENT_MAX,
            steps = self.SENT_MAX - self.SENT_MIN,
            fmt   = lambda v: str(int(v)),
        )
        row += 1

        # === Temperature slider ===
        row = self._add_label(row, "TEMPERATURE  (creativity)")
        self._temp_frame, self._temp_val_label = self._add_slider(
            row,
            var   = self._temp_var,
            from_ = self.TEMP_MIN,
            to    = self.TEMP_MAX,
            steps = 20,
            fmt   = lambda v: f"{v:.2f}",
        )
        row += 1

        # === Max new tokens (validated entry) ===
        row = self._add_label(row, "MAX NEW TOKENS")
        tokens_frame = ctk.CTkFrame(self, fg_color="transparent")
        tokens_frame.grid(row=row, column=0, sticky="ew",
                          padx=_Theme.PAD_INNER, pady=(0, _Theme.PAD_INNER))
        tokens_frame.grid_columnconfigure(0, weight=1)

        self._tokens_entry = ctk.CTkEntry(
            tokens_frame,
            textvariable  = self._tokens_var,
            font          = _Theme.FONT_MONO,
            fg_color      = _Theme.BG_CARD,
            border_color  = _Theme.BORDER,
            text_color    = _Theme.TEXT_PRIMARY,
            corner_radius = _Theme.CORNER_RADIUS,
            height        = 34,
        )
        self._tokens_entry.grid(row=0, column=0, sticky="ew")
        self._tokens_entry.bind("<FocusOut>", self._validate_tokens)

        self._tokens_hint = ctk.CTkLabel(
            tokens_frame,
            text       = f"range {self.TOK_MIN}-{self.TOK_MAX}",
            font       = _Theme.FONT_SMALL,
            text_color = _Theme.TEXT_SECONDARY,
            anchor     = "e",
        )
        self._tokens_hint.grid(row=1, column=0, sticky="e")
        row += 1

        # === Vision DPI (compact option row) ===
        row = self._add_label(row, "VISION RENDER DPI")
        self._dpi_menu = ctk.CTkOptionMenu(
            self,
            values        = ["72", "100", "150", "200", "300"],
            variable      = self._vision_dpi_var,
            font          = _Theme.FONT_BODY,
            dropdown_font = _Theme.FONT_BODY,
            fg_color      = _Theme.BG_CARD,
            button_color  = _Theme.ACCENT,
            button_hover_color = _Theme.ACCENT_HOVER,
            text_color    = _Theme.TEXT_PRIMARY,
            corner_radius = _Theme.CORNER_RADIUS,
            anchor        = "w",
            dynamic_resizing = False,
            width         = 100,
            command       = self._set_vision_dpi,
        )
        self._dpi_menu.grid(row=row, column=0, sticky="w",
                            padx=_Theme.PAD_INNER, pady=(0, _Theme.PAD_INNER))
        row += 1

        # === Retry on parse failure toggle ===
        retry_row = ctk.CTkFrame(self, fg_color="transparent")
        retry_row.grid(row=row, column=0, sticky="ew",
                       padx=_Theme.PAD_INNER, pady=(0, _Theme.PAD_INNER))
        retry_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            retry_row,
            text       = "RETRY ON PARSE FAILURE",
            font       = _Theme.FONT_SMALL,
            text_color = _Theme.TEXT_SECONDARY,
            anchor     = "w",
        ).grid(row=0, column=0, sticky="w")

        self._retry_switch = ctk.CTkSwitch(
            retry_row,
            text            = "",
            variable        = self._retry_var,
            onvalue         = True,
            offvalue        = False,
            progress_color  = _Theme.ACCENT,
            button_color    = _Theme.TEXT_PRIMARY,
            button_hover_color = _Theme.ACCENT_HOVER,
            fg_color        = _Theme.BORDER,
            width           = 44,
            height          = 22,
        )
        self._retry_switch.grid(row=0, column=1, sticky="e")
        row += 1

        ctk.CTkLabel(
            self,
            text       = "Your theme and generation settings are saved automatically.",
            font       = _Theme.FONT_SMALL,
            text_color = _Theme.TEXT_SECONDARY,
            anchor     = "w",
            justify    = "left",
            wraplength = 280,
        ).grid(row=row, column=0, sticky="ew",
               padx=_Theme.PAD_INNER, pady=(0, _Theme.PAD_INNER))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable / disable all interactive config widgets.

        Called by MemoForgeApp.set_generating_state() to lock the panel
        while a pipeline run is in progress.
        """
        state = "normal" if enabled else "disabled"
        for widget in (
            self._task_menu,
            self._model_combo,
            self._refresh_models_btn,
            self._tokens_entry,
            self._dpi_menu,
            self._retry_switch,
        ):
            try:
                widget.configure(state=state)
            except Exception:
                pass
        # Sliders: CTkSlider state support varies across CTk versions
        for frame, _ in (
            (self._cards_frame, None),
            (self._summary_frame, None),
            (self._temp_frame, None),
        ):
            for child in frame.winfo_children():
                try:
                    child.configure(state=state)
                except Exception:
                    pass

    def get_config(self) -> GenerationConfig:
        """
        Read all widget states and construct a GenerationConfig.

        Called by the Generate button handler in MemoForgeApp.
        """
        # Maps dropdown label → (TaskType, anki_export flag).
        # "Anki Deck Only" reuses FLASHCARDS but sets anki_export=True so
        # Module 5 knows to write an .apkg instead of an in-app preview.
        task_map = {
            "Flashcards + Summary": (TaskType.COMBINED,   False),
            "Flashcards Only":      (TaskType.FLASHCARDS, False),
            "Summary Only":         (TaskType.SUMMARY,    False),
            "Anki Deck Only":       (TaskType.FLASHCARDS, True),
        }
        task_type, anki_export = task_map.get(
            self._task_var.get(), (TaskType.COMBINED, False)
        )

        # Validate tokens entry defensively
        try:
            tokens = int(self._tokens_var.get())
            tokens = max(self.TOK_MIN, min(self.TOK_MAX, tokens))
        except ValueError:
            tokens = 1024

        return GenerationConfig(
            model_id               = self._model_var.get().strip() or "qwen3-vl:2b",
            task_type              = task_type,
            max_flashcards         = int(self._cards_var.get()),
            max_new_tokens         = tokens,
            temperature            = round(float(self._temp_var.get()), 2),
            summary_max_sentences  = int(self._summary_var.get()),
            vision_render_dpi      = int(self._vision_dpi.get()),
            retry_on_parse_failure = bool(self._retry_var.get()),
            anki_export            = anki_export,
        )

    def get_ui_state(self) -> Dict[str, object]:
        """Return a serializable settings snapshot for app persistence."""
        try:
            tokens = int(self._tokens_var.get())
        except (TypeError, ValueError):
            tokens = 1024
        tokens = max(self.TOK_MIN, min(self.TOK_MAX, tokens))
        return {
            "output_mode": self._task_var.get(),
            "model_id": self._model_var.get().strip() or "qwen3-vl:2b",
            "max_flashcards": int(self._cards_var.get()),
            "summary_sentences": int(self._summary_var.get()),
            "temperature": round(float(self._temp_var.get()), 2),
            "max_new_tokens": tokens,
            "vision_render_dpi": int(self._vision_dpi.get()),
            "retry_on_parse_failure": bool(self._retry_var.get()),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _add_label(self, row: int, text: str) -> int:
        """Render a small section label and return the next row index."""
        label = ctk.CTkLabel(
            self,
            text       = text,
            font       = _Theme.FONT_SMALL,
            text_color = _Theme.TEXT_SECONDARY,
            anchor     = "w",
        )
        label.grid(row=row, column=0, sticky="w",
                   padx=_Theme.PAD_INNER, pady=(0, 2))
        return row + 1

    def _add_slider(
        self,
        row: int,
        var: tk.Variable,
        from_: float,
        to: float,
        steps: int,
        fmt: Callable,
    ) -> tuple[ctk.CTkFrame, ctk.CTkLabel]:
        """
        Render a labelled slider row (slider + live value readout).

        Returns (frame, value_label) so callers can adjust the label's
        position if needed.
        """
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew",
                   padx=_Theme.PAD_INNER, pady=(0, _Theme.PAD_INNER))
        frame.grid_columnconfigure(0, weight=1)

        val_label = ctk.CTkLabel(
            frame,
            text       = fmt(var.get()),
            font       = ("Courier New", 11, "bold"),
            text_color = _Theme.ACCENT,
            width      = 36,
            anchor     = "e",
        )
        val_label.grid(row=0, column=1, sticky="e", padx=(8, 0))

        def _on_slide(value):
            val_label.configure(text=fmt(value))

        slider = ctk.CTkSlider(
            frame,
            variable          = var,
            from_             = from_,
            to                = to,
            number_of_steps   = steps,
            command           = _on_slide,
            progress_color    = _Theme.ACCENT,
            fg_color          = _Theme.BORDER,
            button_color      = _Theme.ACCENT,
            button_hover_color= _Theme.ACCENT_HOVER,
            height            = 16,
        )
        slider.grid(row=0, column=0, sticky="ew")

        return frame, val_label

    def _validate_tokens(self, _event=None) -> None:
        """Clamp the token entry to the valid range on focus-out."""
        try:
            val = int(self._tokens_var.get())
            val = max(self.TOK_MIN, min(self.TOK_MAX, val))
            self._tokens_var.set(str(val))
            self._tokens_entry.configure(border_color=_Theme.BORDER)
        except ValueError:
            self._tokens_var.set("1024")
            self._tokens_entry.configure(border_color=_Theme.ERROR)

    def _set_vision_dpi(self, value: str) -> None:
        try:
            dpi_value = int(value)
        except (TypeError, ValueError):
            dpi_value = 150
        dpi_value = max(72, min(300, dpi_value))
        self._vision_dpi.set(dpi_value)
        self._vision_dpi_var.set(str(dpi_value))

    def _fetch_ollama_models(self) -> List[str]:
        """Return locally installed Ollama model names."""
        try:
            with urllib_request.urlopen("http://localhost:11434/api/tags", timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [m.get("name", "").strip() for m in payload.get("models", [])]
            return sorted({m for m in models if m})
        except (urllib_error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return []

    def _refresh_models(self) -> None:
        models = self._fetch_ollama_models()
        current = self._model_var.get().strip() or "qwen3-vl:2b"

        if not models:
            self._tokens_hint.configure(text="Ollama unavailable; type a model manually.")
            return

        if current not in models:
            models.insert(0, current)
        self._model_combo.configure(values=models)
        self._tokens_hint.configure(text=f"{len(models)} model(s) detected.")


# ============================================================
# StatusBar — progress + status message at the bottom of the sidebar
# ============================================================

class StatusBar(ctk.CTkFrame):
    """
    Displays a progress bar, a chunk counter, and a one-line status message.

    Module 5 will call update_progress() and set_status() as the pipeline runs.
    In this module the bar is idle by default.
    """

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(
            parent,
            fg_color      = _Theme.BG_PANEL,
            corner_radius = _Theme.CORNER_RADIUS,
            border_width  = 1,
            border_color  = _Theme.BORDER,
            **kwargs,
        )
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # ── Top row: status message + chunk/percentage counter ───────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew",
                    padx=_Theme.PAD_INNER, pady=(_Theme.PAD_INNER, 4))
        header.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            header,
            text       = "Ready",
            font       = _Theme.FONT_SMALL,
            text_color = _Theme.TEXT_SECONDARY,
            anchor     = "w",
        )
        self._status_label.grid(row=0, column=0, sticky="w")

        self._chunk_label = ctk.CTkLabel(
            header,
            text       = "",
            font       = ("Courier New", 10, "bold"),
            text_color = _Theme.ACCENT,
            anchor     = "e",
        )
        self._chunk_label.grid(row=0, column=1, sticky="e")

        # ── Progress bar (taller, clearly visible) ───────────────────────────
        self._bar = ctk.CTkProgressBar(
            self,
            mode           = "determinate",
            height         = 14,
            corner_radius  = 3,
            progress_color = _Theme.ACCENT,
            fg_color       = _Theme.BORDER,
        )
        self._bar.set(0)
        self._bar.grid(row=1, column=0, sticky="ew",
                       padx=_Theme.PAD_INNER, pady=(0, _Theme.PAD_INNER))

    # ------------------------------------------------------------------
    # Public API (called by Module 5)
    # ------------------------------------------------------------------

    def set_status(self, message: str, color: Optional[str] = None) -> None:
        """Update the one-line status message."""
        self._status_label.configure(
            text       = message,
            text_color = color or _Theme.TEXT_SECONDARY,
        )

    def update_progress(self, done: int, total: int) -> None:
        """Drive the progress bar, chunk counter, and percentage readout."""
        fraction = done / total if total > 0 else 0
        self._bar.set(fraction)
        if total > 0:
            pct = int(fraction * 100)
            self._chunk_label.configure(text=f"{done}/{total}  {pct}%")
        else:
            self._chunk_label.configure(text="")

    def reset(self) -> None:
        """Return the bar to its idle state."""
        self._bar.set(0)
        self._chunk_label.configure(text="")
        self._status_label.configure(text="Ready", text_color=_Theme.TEXT_SECONDARY)

    def set_indeterminate(self, running: bool) -> None:
        """
        Switch the bar between determinate and indeterminate (spinning) mode.

        Used by Module 5 during the model-loading phase before chunk counts
        are known.
        """
        self._bar.configure(mode="indeterminate" if running else "determinate")
        if running:
            self._bar.start()
        else:
            self._bar.stop()
            self._bar.set(0)


# ============================================================
# TitleBar — custom window chrome
# ============================================================

class TitleBar(ctk.CTkFrame):
    """
    A thin top bar with the app name, document counter badge, and a
    light/dark mode toggle.

    No OS window-drag functionality is attempted here — that requires
    platform-specific code and is out of scope for this module.
    """

    def __init__(
        self,
        parent,
        on_close: Optional[Callable[[], None]] = None,
        on_theme_change: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            fg_color      = _Theme.BG_PANEL,
            corner_radius = 0,
            border_width  = 0,
            height        = 52,
            **kwargs,
        )
        self._on_close = on_close
        self._on_theme_change = on_theme_change
        self.grid_columnconfigure(1, weight=1)
        self._build()

    def _build(self) -> None:
        # App name
        title_label = ctk.CTkLabel(
            self,
            text       = "MEMOFORGE",
            font       = _Theme.FONT_DISPLAY,
            text_color = _Theme.ACCENT,
            anchor     = "w",
        )
        title_label.grid(row=0, column=0, padx=(_Theme.PAD_OUTER, 6), pady=0, sticky="w")

        # Subtitle / tagline
        sub_label = ctk.CTkLabel(
            self,
            text       = "local - private - academic",
            font       = ("Courier New", 9),
            text_color = _Theme.TEXT_SECONDARY,
            anchor     = "w",
        )
        sub_label.grid(row=0, column=1, padx=(0, 0), pady=0, sticky="w")

        # Theme toggle — label shows the mode you will switch TO, not the current mode.
        # Initial state is Dark (set in MemoForgeApp.__init__), so we offer "LIGHT".
        self._theme_btn = ctk.CTkButton(
            self,
            text          = "LIGHT",
            font          = _Theme.FONT_SMALL,
            width         = 88,
            height        = 28,
            corner_radius = _Theme.CORNER_RADIUS,
            fg_color      = "transparent",
            border_width  = 1,
            border_color  = _Theme.BORDER,
            hover_color   = _Theme.BG_CARD,
            text_color    = _Theme.TEXT_SECONDARY,
            command       = self._toggle_theme,
        )
        self._theme_btn.grid(row=0, column=2, padx=(_Theme.PAD_INNER, 8),
                             pady=0, sticky="e")

        self._close_btn = ctk.CTkButton(
            self,
            text          = "CLOSE",
            font          = _Theme.FONT_SMALL,
            width         = 92,
            height        = 28,
            corner_radius = _Theme.CORNER_RADIUS,
            fg_color      = "transparent",
            border_width  = 1,
            border_color  = _Theme.BORDER,
            hover_color   = _Theme.ERROR,
            text_color    = _Theme.TEXT_SECONDARY,
            command       = self._on_close_pressed,
        )
        self._close_btn.grid(row=0, column=3, padx=(0, _Theme.PAD_OUTER), pady=0, sticky="e")

        # Bottom border
        border = ctk.CTkFrame(self, height=1, fg_color=_Theme.BORDER, corner_radius=0)
        border.grid(row=1, column=0, columnspan=4, sticky="ew")
        self._sync_theme_button()

    def _sync_theme_button(self) -> None:
        if ctk.get_appearance_mode() == "Dark":
            self._theme_btn.configure(text="LIGHT")
        else:
            self._theme_btn.configure(text="DARK")

    def _toggle_theme(self) -> None:
        current = ctk.get_appearance_mode()
        if current == "Dark":
            next_mode = "Light"
        else:
            next_mode = "Dark"
        ctk.set_appearance_mode(next_mode)
        self._sync_theme_button()
        if self._on_theme_change:
            self._on_theme_change(next_mode)

    def _on_close_pressed(self) -> None:
        if self._on_close:
            self._on_close()


# ============================================================
# MemoForgeApp — the root application class
# ============================================================

class MemoForgeApp(_BaseApp):
    """
    The top-level application window.

    Composes all sub-widgets and owns the application lifecycle.

    Layout
    ------
    Row 0 : TitleBar (full width, fixed height)
    Row 1 : Left panel (DropZone + FileQueue) + Right panel (Config + Generate + Status)

    Module 5 public surface
    -----------------------
    The following attributes / methods form the documented contract that
    MemoForgeController (main.py) relies on:

        self._on_generate()              — stub; overridden by controller
        self.status_bar                  — StatusBar instance
          .set_status(text, color)       — update status label
          .update_progress(done, total)  — drive progress bar
          .set_indeterminate(bool)       — toggle spinner mode
        self.get_generation_inputs()     — returns (List[Path], GenerationConfig)
        self.set_generating_state(bool)  — lock / unlock UI during pipeline run
        self._shake_button()             — border-flash error animation
    """

    APP_TITLE  = "MemoForge"
    MIN_WIDTH  = 960
    MIN_HEIGHT = 640

    def __init__(self) -> None:
        self._ui_settings = self._load_ui_settings()
        ctk.set_appearance_mode(
            self._normalise_appearance_mode(self._ui_settings.get("appearance_mode"))
        )
        ctk.set_default_color_theme("dark-blue")

        super().__init__()
        self._closing = False
        self._settings_save_job: Optional[str] = None

        self.title(self.APP_TITLE)
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.geometry(f"{self.MIN_WIDTH}x{self.MIN_HEIGHT + 80}")
        self.configure(fg_color=_Theme.BG_ROOT)
        self.protocol("WM_DELETE_WINDOW", self._request_close)

        # Allow the window to resize nicely
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_layout()
        self._center_window()

        logger.info("MemoForgeApp initialised.")

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        # ── Row 0: Title bar ─────────────────────────────────────────
        self.title_bar = TitleBar(
            self,
            on_close=self._request_close,
            on_theme_change=self._on_theme_changed,
        )
        self.title_bar.grid(row=0, column=0, sticky="ew")

        # ── Row 1: Main content (left + right panels) ────────────────
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew",
                  padx=_Theme.PAD_OUTER, pady=_Theme.PAD_OUTER)
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)   # left panel expands
        main.grid_columnconfigure(1, minsize=_Theme.SIDEBAR_W)  # right panel fixed

        self._build_left_panel(main)
        self._build_right_panel(main)

        # Wire the task dropdown so the Generate button label updates live.
        # This is done after both panels exist so both sides are accessible.
        self.config_panel._task_menu.configure(
            command=self._on_output_mode_changed
        )
        # Set the initial button label to match the default task selection.
        self._update_generate_btn_label()
        self._register_settings_watchers()

    def _build_left_panel(self, parent) -> None:
        """Drop zone + file queue."""
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew",
                  padx=(0, _Theme.PAD_INNER))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # Drop zone
        self.drop_zone = DropZoneWidget(
            left,
            on_files_added = self._on_files_added,
            height         = _Theme.DROPZONE_H,
        )
        self.drop_zone.grid(row=0, column=0, sticky="ew",
                            pady=(0, _Theme.PAD_INNER))

        # File queue panel
        self.queue_panel = FileQueuePanel(left)
        self.queue_panel.grid(row=1, column=0, sticky="nsew")

    def _build_right_panel(self, parent) -> None:
        """Configuration, generate button, and status bar."""
        right = ctk.CTkFrame(parent, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)   # config panel expands vertically
        right.grid_columnconfigure(0, weight=1)

        # Config panel
        self.config_panel = ConfigPanel(right, initial_state=self._ui_settings)
        self.config_panel.grid(row=0, column=0, sticky="nsew",
                               pady=(0, _Theme.PAD_INNER))

        # Generate button
        self._generate_btn = ctk.CTkButton(
            right,
            text          = "GENERATE",
            font          = _Theme.FONT_BTN,
            height        = _Theme.BTN_HEIGHT,
            corner_radius = _Theme.CORNER_RADIUS,
            fg_color      = _Theme.ACCENT,
            hover_color   = _Theme.ACCENT_HOVER,
            text_color    = _Theme.BTN_TEXT_ON_ACCENT,  # always dark on amber
            command       = self._on_generate,
        )
        self._generate_btn.grid(row=1, column=0, sticky="ew",
                                pady=(0, _Theme.PAD_INNER))

        # Status bar
        self.status_bar = StatusBar(right)
        self.status_bar.grid(row=2, column=0, sticky="ew")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    # Task dropdown label → generate button text (mirrors ConfigPanel._task_var values)
    _TASK_BTN_LABELS = {
        "Flashcards + Summary": "GENERATE",
        "Flashcards Only":      "GENERATE CARDS",
        "Summary Only":         "GENERATE SUMMARY",
        "Anki Deck Only":       "GENERATE ANKI DECK",
    }

    def _update_generate_btn_label(self) -> None:
        """
        Sync the Generate button's text with the currently selected task.

        Called on startup and whenever the task dropdown value changes so the
        button always reflects the active mode.  Also called by
        set_generating_state(False) so the correct label is restored after a run.
        """
        selection = self.config_panel._task_var.get()
        label = self._TASK_BTN_LABELS.get(selection, "GENERATE")
        self._generate_btn.configure(text=label)

    def _on_output_mode_changed(self, _value: str) -> None:
        self._update_generate_btn_label()
        self._schedule_settings_save()

    def _register_settings_watchers(self) -> None:
        watched_vars = (
            self.config_panel._task_var,
            self.config_panel._model_var,
            self.config_panel._cards_var,
            self.config_panel._summary_var,
            self.config_panel._temp_var,
            self.config_panel._tokens_var,
            self.config_panel._vision_dpi_var,
            self.config_panel._retry_var,
        )
        for variable in watched_vars:
            variable.trace_add("write", self._schedule_settings_save)

    def _schedule_settings_save(self, *_args) -> None:
        if self._closing:
            return
        if self._settings_save_job is not None:
            try:
                self.after_cancel(self._settings_save_job)
            except Exception:
                pass
            self._settings_save_job = None
        self._settings_save_job = self.after(400, self._flush_scheduled_settings_save)

    def _flush_scheduled_settings_save(self) -> None:
        self._settings_save_job = None
        self._save_ui_settings()

    def _on_files_added(self, paths: List[Path]) -> None:
        """
        Receive new paths from the drop zone or file picker and add
        them to the queue.
        """
        added = self.queue_panel.add_files(paths)
        ready = len(self.queue_panel.ready_paths)
        total = self.queue_panel.total_count

        if added == 0:
            self.status_bar.set_status("No new files added (duplicates skipped).",
                                       _Theme.WARNING)
        elif total > ready:
            self.status_bar.set_status(
                f"{added} file(s) added - {total - ready} unsupported format(s).",
                _Theme.WARNING,
            )
        else:
            self.status_bar.set_status(
                f"{added} file(s) queued - {ready} ready for generation.",
                _Theme.SUCCESS,
            )

        logger.info("Files added: %d (total ready: %d)", added, ready)

    def _on_generate(self) -> None:
        """
        ── MODULE 5 INTEGRATION SEAM ──

        This stub is intentionally empty.  MemoForgeController (main.py) subclasses
        MemoForgeApp and overrides this single method with the real threaded pipeline.
        Leaving the body as ``pass`` means the button does nothing in isolation,
        which is the correct behaviour for a UI-only module test.
        """
        pass  # Overridden by MemoForgeController in main.py
    # ------------------------------------------------------------------
    # Animation helpers
    # ------------------------------------------------------------------

    def _shake_button(self) -> None:
        """
        Flash the Generate button border amber→red→amber to signal an error.

        Uses border-colour animation rather than position/place() so the grid
        layout is never disturbed.  Guards against concurrent invocations with
        a simple flag so rapid double-clicks don't stack animations.
        """
        if getattr(self, "_shaking", False):
            return
        self._shaking = True

        btn    = self._generate_btn
        colors = [_Theme.ERROR, _Theme.ACCENT] * 3  # 6 flashes total

        def _flash(remaining_colors: list) -> None:
            if not remaining_colors:
                # Restore normal appearance and clear the guard flag.
                btn.configure(border_width=0, border_color=_Theme.BORDER)
                self._shaking = False
                return
            btn.configure(border_width=2, border_color=remaining_colors[0])
            self.after(80, lambda: _flash(remaining_colors[1:]))

        _flash(colors)

    # ------------------------------------------------------------------
    # Window helpers
    # ------------------------------------------------------------------

    def _center_window(self) -> None:
        """Place the window in the centre of the primary monitor on startup."""
        self.update_idletasks()
        w  = self.winfo_width()
        h  = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    @staticmethod
    def _normalise_appearance_mode(value: object) -> str:
        mode = str(value or "").strip().title()
        return mode if mode in {"Dark", "Light", "System"} else "Dark"

    def _load_ui_settings(self) -> Dict[str, object]:
        if not _SETTINGS_PATH.exists():
            return dict(_DEFAULT_UI_SETTINGS)
        try:
            payload = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return dict(_DEFAULT_UI_SETTINGS)
        if not isinstance(payload, dict):
            return dict(_DEFAULT_UI_SETTINGS)
        merged = dict(_DEFAULT_UI_SETTINGS)
        merged.update(payload)
        merged["appearance_mode"] = self._normalise_appearance_mode(
            merged.get("appearance_mode")
        )
        return merged

    def _collect_ui_settings(self) -> Dict[str, object]:
        snapshot = dict(_DEFAULT_UI_SETTINGS)
        snapshot["appearance_mode"] = self._normalise_appearance_mode(
            ctk.get_appearance_mode()
        )
        if hasattr(self, "config_panel"):
            snapshot.update(self.config_panel.get_ui_state())
        return snapshot

    def _save_ui_settings(self) -> None:
        try:
            _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            settings = self._collect_ui_settings()
            _SETTINGS_PATH.write_text(
                json.dumps(settings, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._ui_settings = settings
        except OSError as exc:
            logger.warning("Unable to persist UI settings: %s", exc)

    def _on_theme_changed(self, mode: str) -> None:
        self._ui_settings["appearance_mode"] = self._normalise_appearance_mode(mode)
        self._save_ui_settings()

    def _request_close(self) -> None:
        """
        Close the app cleanly from either the OS close button or in-app close button.
        """
        if self._closing:
            return
        self._closing = True
        if self._settings_save_job is not None:
            try:
                self.after_cancel(self._settings_save_job)
            except Exception:
                pass
            self._settings_save_job = None
        self._save_ui_settings()
        try:
            self.quit()
            self.destroy()
        except tk.TclError:
            os._exit(0)

    # ------------------------------------------------------------------
    # Module 5 public surface (documented here so Module 5 dev knows the API)
    # ------------------------------------------------------------------

    def set_generating_state(self, is_generating: bool) -> None:
        """
        Lock / unlock the UI while inference is running.

        Called by Module 5:
            app.set_generating_state(True)   # before pipeline.run()
            app.set_generating_state(False)  # in finally / on_done block

        IMPORTANT: This method must NOT touch the indeterminate progress bar.
        Module 5 drives set_indeterminate() independently (during model-load
        phase) via self.after(0, ...) calls from the worker thread.
        """
        if is_generating:
            self._generate_btn.configure(
                state    = "disabled",
                text     = "GENERATING...",
                fg_color = _Theme.BORDER,
            )
            # Disable config panel widgets so the user cannot change settings
            # while a pipeline run is in progress.
            self.config_panel.set_enabled(False)
        else:
            # Restore the generate button label to match the currently selected
            # task mode — do NOT hardcode "GENERATE FLASHCARDS" because the
            # user may have chosen "Summary Only" or "Anki Deck Only".
            self._update_generate_btn_label()
            self._generate_btn.configure(
                state    = "normal",
                fg_color = _Theme.ACCENT,
            )
            self.config_panel.set_enabled(True)

    def get_generation_inputs(self) -> tuple:
        """
        Convenience accessor for Module 5 / MemoForgeController.

        Returns
        -------
        (ready_paths, config) : tuple[List[Path], GenerationConfig]
            ready_paths : List[Path]
                File paths from the queue that passed format validation.
            config : GenerationConfig
                Fully-populated config built from the current widget state.
                ``config.task_type`` reflects the selected task mode;
                ``config.anki_export`` is True only for "Anki Deck Only".
        """
        return self.queue_panel.ready_paths, self.config_panel.get_config()


# ============================================================
# Application entry point
# ============================================================

def run_app() -> None:
    """
    Configure logging and launch the MemoForge UI event loop.

    Import and call this from main.py or directly:
        python app_frame.py
    """
    logging.basicConfig(
        level  = logging.DEBUG,
        format = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        stream = sys.stdout,
    )

    try:
        if _HAS_DND:
            logger.info("tkinterdnd2 detected — drag-and-drop enabled.")
        else:
            logger.info("tkinterdnd2 not installed — drag-and-drop disabled; using click-to-browse.")

        app = MemoForgeApp()
        app.mainloop()

    except KeyboardInterrupt:
        logger.info("Application closed by user (KeyboardInterrupt).")
    except Exception as exc:
        logger.exception("Fatal error in MemoForge UI: %s", exc)
        raise


if __name__ == "__main__":
    print(
        "\n"
        "============================================================\n"
        " ⚠️ WARNING: RUNNING VIA UI MODULE DIRECTLY\n"
        "============================================================\n"
        " You have executed 'app_frame.py' directly. We are automatically\n"
        " forwarding this launch to 'main.py' to ensure the backend\n"
        " pipeline is properly attached!\n"
        "============================================================\n"
    )
    import main
    main.run_app()
