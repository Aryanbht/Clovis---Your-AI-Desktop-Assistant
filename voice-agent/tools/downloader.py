"""
tools/downloader.py – Download files from the internet with a tqdm progress bar.
All functions return a plain string suitable for TTS output.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from tqdm import tqdm

from config import DOWNLOADS_PATH


def download_file(url: str, destination: str = DOWNLOADS_PATH) -> str:
    """
    Download the file at *url* to *destination*.

    *destination* may be:
      • A directory path  → filename is inferred from the URL
      • A full file path  → used as-is

    Returns a success or failure message string.
    """
    dest = Path(destination)

    # ── Resolve final save path ────────────────────────────────────────────────
    filename = _filename_from_url(url)

    if dest.is_dir() or not dest.suffix:
        # destination is (or looks like) a directory
        dest.mkdir(parents=True, exist_ok=True)
        save_path = dest / filename
    else:
        # destination is a full file path
        dest.parent.mkdir(parents=True, exist_ok=True)
        save_path = dest

    # ── Stream download ────────────────────────────────────────────────────────
    print(f"[Downloader] Downloading '{filename}' from:\n  {url}")

    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
    except requests.exceptions.MissingSchema:
        return f"Invalid URL: '{url}'. Make sure it starts with http:// or https://."
    except requests.exceptions.ConnectionError:
        return f"Could not connect to '{url}'. Check your internet connection."
    except requests.exceptions.HTTPError as exc:
        return f"Download failed — server returned {exc.response.status_code}."
    except requests.exceptions.Timeout:
        return "Download timed out. The server took too long to respond."
    except Exception as exc:
        return f"Unexpected error while downloading: {exc}"

    total_bytes = int(response.headers.get("content-length", 0))

    try:
        with (
            open(save_path, "wb") as fh,
            tqdm(
                desc=filename,
                total=total_bytes,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                ncols=80,
            ) as bar,
        ):
            for chunk in response.iter_content(chunk_size=8_192):
                fh.write(chunk)
                bar.update(len(chunk))
    except PermissionError:
        return f"Permission denied: cannot write to '{save_path}'."
    except OSError as exc:
        return f"File write error: {exc}"

    size_str = _human_size(save_path.stat().st_size)
    return f"Downloaded '{filename}' ({size_str}) to '{save_path}'."


# ── Internal helpers ───────────────────────────────────────────────────────────

def _filename_from_url(url: str) -> str:
    """
    Infer a filename from *url*.
    Falls back to 'download' if nothing useful can be extracted.
    """
    parsed   = urlparse(url)
    raw_name = Path(parsed.path).name          # last path segment
    name     = unquote(raw_name).split("?")[0] # strip query string artifacts
    return name if name else "download"


def _human_size(n_bytes: int) -> str:
    """Convert a byte count to a human-readable string (e.g. '2.1 MB')."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} PB"
