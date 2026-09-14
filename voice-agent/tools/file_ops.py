"""
tools/file_ops.py – File and folder operations using pathlib + os.
All functions return a plain string suitable for TTS output.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from config import DESKTOP_PATH, DOCUMENTS_PATH, DOWNLOADS_PATH


# ── Path resolution ────────────────────────────────────────────────────────────
# The LLM sometimes generates wrong base paths (e.g. C:/Users/bhatn/Desktop
# instead of C:/Users/bhatn/OneDrive/Desktop). _resolve_path detects any path
# that mentions "desktop", "downloads", or "documents" as a component and
# rewrites it to the real path from config.py.

def _resolve_path(path: str) -> str:
    """
    Rewrite *path* so that known folder shortcuts always point to the real
    location read from the Windows registry (via config.py).

    Examples
    --------
    "C:/Users/bhatn/Desktop/foo"          → "<DESKTOP_PATH>/foo"
    "C:/Users/anyone/Downloads/file.zip"  → "<DOWNLOADS_PATH>/file.zip"
    "desktop"                             → DESKTOP_PATH
    "downloads/file.zip"                  → "<DOWNLOADS_PATH>/file.zip"
    """
    p       = Path(path)
    parts   = p.parts          # e.g. ('C:\\', 'Users', 'bhatn', 'Desktop', 'foo')
    lower   = [pt.lower() for pt in parts]

    _ROOTS = {
        "desktop":   Path(DESKTOP_PATH),
        "downloads": Path(DOWNLOADS_PATH),
        "documents": Path(DOCUMENTS_PATH),
    }

    for keyword, real_root in _ROOTS.items():
        if keyword in lower:
            idx  = lower.index(keyword)
            rest = Path(*parts[idx + 1:]) if idx + 1 < len(parts) else Path()
            return str(real_root / rest)

    return path   # no known folder found — return unchanged


def create_folder(path: str) -> str:
    """
    Create a folder (and any missing parents) at *path*.

    Returns a success or failure message string.
    """
    try:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        return f"Folder created: {target}"
    except PermissionError:
        return f"Permission denied: cannot create folder at '{path}'."
    except Exception as exc:
        return f"Failed to create folder '{path}': {exc}"


def create_file(path: str, content: str = "") -> str:
    """
    Create a file at *path* with optional *content*.
    Parent directories are created automatically.

    Returns a success or failure message string.
    """
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"File created: {target}"
    except PermissionError:
        return f"Permission denied: cannot write to '{path}'."
    except Exception as exc:
        return f"Failed to create file '{path}': {exc}"


def list_files(path: str) -> str:
    """
    List the contents of *path*.

    Returns a formatted newline-separated string of entry names,
    with a trailing summary line, or an error message.
    """
    try:
        target = Path(path)

        if not target.exists():
            return f"'{path}' does not exist."
        if not target.is_dir():
            return f"'{path}' is a file, not a folder."

        entries = sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))

        if not entries:
            return f"'{path}' is empty."

        lines: list[str] = []
        folders = [e for e in entries if e.is_dir()]
        files   = [e for e in entries if e.is_file()]

        for folder in folders:
            lines.append(f"[DIR]  {folder.name}")
        for file in files:
            size = file.stat().st_size
            lines.append(f"[FILE] {file.name}  ({_human_size(size)})")

        summary = f"\n{len(folders)} folder(s), {len(files)} file(s) in '{target.name}'."
        return "\n".join(lines) + summary

    except PermissionError:
        return f"Permission denied: cannot read '{path}'."
    except Exception as exc:
        return f"Failed to list '{path}': {exc}"


def delete_file(path: str) -> str:
    """
    Delete a file or folder at *path*.
    Directories are removed recursively.

    Returns a success or failure message string.
    """
    try:
        target = Path(path)

        if not target.exists():
            return f"'{path}' does not exist."

        if target.is_dir():
            shutil.rmtree(target)
            return f"Folder deleted: {target}"
        else:
            target.unlink()
            return f"File deleted: {target}"

    except PermissionError:
        return f"Permission denied: cannot delete '{path}'."
    except Exception as exc:
        return f"Failed to delete '{path}': {exc}"


def move_file(src: str, dest: str) -> str:
    """
    Move or rename the file/folder at *src* to *dest*.
    Creates destination parent directories if needed.

    Returns a success or failure message string.
    """
    try:
        source      = Path(src)
        destination = Path(dest)

        if not source.exists():
            return f"Source '{src}' does not exist."

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return f"Moved '{source.name}' → '{destination}'."

    except PermissionError:
        return f"Permission denied: cannot move '{src}'."
    except Exception as exc:
        return f"Failed to move '{src}' to '{dest}': {exc}"


# ── Internal helper ────────────────────────────────────────────────────────────

def _human_size(n_bytes: int) -> str:
    """Convert a byte count to a human-readable string (e.g. '1.4 MB')."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} PB"
