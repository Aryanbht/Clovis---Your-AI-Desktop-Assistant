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
from tools.file_ops import _human_size


def download_file(url: str, destination: str = DOWNLOADS_PATH) -> dict:
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
        msg = f"Invalid URL: '{url}'. Make sure it starts with http:// or https://."
        return {"display": msg, "speak": "That URL is invalid."}
    except requests.exceptions.ConnectionError:
        msg = f"Could not connect to '{url}'. Check your internet connection."
        return {"display": msg, "speak": "I couldn't connect to the internet."}
    except requests.exceptions.HTTPError as exc:
        msg = f"Download failed — server returned {exc.response.status_code}."
        return {"display": msg, "speak": "The download failed."}
    except requests.exceptions.Timeout:
        msg = "Download timed out. The server took too long to respond."
        return {"display": msg, "speak": "The download timed out."}
    except Exception as exc:
        msg = f"Unexpected error while downloading: {exc}"
        return {"display": msg, "speak": "An unexpected error occurred while downloading."}

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
        msg = f"Permission denied: cannot write to '{save_path}'."
        return {"display": msg, "speak": "Permission denied. I couldn't save the file."}
    except OSError as exc:
        msg = f"File write error: {exc}"
        return {"display": msg, "speak": "There was an error saving the file."}

    size_str = _human_size(save_path.stat().st_size)
    msg = f"Downloaded '{filename}' ({size_str}) to '{save_path}'."
    return {"display": msg, "speak": "Download complete."}


# ── Internal helpers ───────────────────────────────────────────────────────────

def _filename_from_url(url: str) -> str:
    """
    Infer a filename from *url*.
    Falls back to 'download' if nothing useful can be extracted.
    """
    parsed   = urlparse(url)
    raw_name = Path(parsed.path).name
    name     = unquote(raw_name).split("?")[0]
    return name if name else "download"
