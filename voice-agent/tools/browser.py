"""
tools/browser.py – Open URLs and perform web searches using the system browser.
All functions return a dict with 'display' and 'speak' keys for UI/TTS.
"""

from __future__ import annotations

import urllib.parse
import webbrowser
import os
import subprocess
from pathlib import Path


_BROWSER_SPECS: dict[str, tuple[list[Path], str]] = {
    "chrome": (
        [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ],
        "--incognito",
    ),
    "google chrome": (
        [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ],
        "--incognito",
    ),
    "edge": (
        [
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        ],
        "--inprivate",
    ),
    "microsoft edge": (
        [
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        ],
        "--inprivate",
    ),
    "firefox": (
        [Path(os.environ.get("PROGRAMFILES", "")) / "Mozilla Firefox/firefox.exe"],
        "-private-window",
    ),
}


def _find_browser_executable(browser: str) -> Path | None:
    """Return the first existing executable path for *browser*, or None."""
    specs = _BROWSER_SPECS.get(browser.strip().lower())
    if not specs:
        return None
    return next((p for p in specs[0] if p.exists()), None)


def _open_in_browser(url: str, browser: str | None = None, incognito: bool = False) -> None:
    """Open *url* in the requested browser when it can be located."""
    requested = (browser or "").strip().lower()
    specs = _BROWSER_SPECS.get(requested)
    if specs is None:
        webbrowser.open(url)
        return

    candidates, flag = specs
    executable = next((p for p in candidates if p.exists()), None)
    if executable:
        args = [str(executable)]
        if incognito:
            args.append(flag)
        args.append(url)
        subprocess.Popen(args, shell=False)
        return

    webbrowser.open(url)


def open_incognito(browser: str = "chrome") -> dict:
    """Open a private browser window on Windows."""
    requested = browser.strip().lower()
    specs = _BROWSER_SPECS.get(requested)
    if not specs:
        msg = f"I couldn't find {browser} on this system."
        return {"display": msg, "speak": f"I couldn't find {browser} on your PC."}

    candidates, flag = specs
    executable = next((p for p in candidates if p.exists()), None)
    if executable:
        try:
            subprocess.Popen([str(executable), flag], shell=False)
            msg = f"Opening a private {browser} window."
            return {"display": msg, "speak": "Opening incognito mode."}
        except Exception as exc:
            msg = f"Failed to open private {browser}: {exc}"
            return {"display": msg, "speak": "I couldn't open the browser in private mode."}
    msg = f"I couldn't find {browser} on this system."
    return {"display": msg, "speak": f"I couldn't find {browser} on your PC."}


def open_url(url: str, browser: str | None = None) -> dict:
    """
    Open *url* in the system's default web browser.

    Automatically prepends 'https://' if no scheme is present.

    Returns a success or failure message string.
    """
    if not url.strip():
        return {"display": "No URL provided.", "speak": "You didn't give me a URL to open."}

    if not url.startswith(("http://", "https://", "ftp://")):
        url = "https://" + url

    try:
        _open_in_browser(url, browser)
        destination = f" in {browser}" if browser else " in your browser"
        msg = f"Opening {url}{destination}."
        return {"display": msg, "speak": "Opening URL."}
    except Exception as exc:
        msg = f"Failed to open browser: {exc}"
        return {"display": msg, "speak": "There was an error opening the browser."}


def search_web(query: str, browser: str | None = None, incognito: bool = False) -> dict:
    """
    Search DuckDuckGo for *query* in the system's default web browser.

    Returns a success or failure message string.
    """
    if not query.strip():
        return {"display": "No search query provided.", "speak": "You didn't tell me what to search for."}

    encoded = urllib.parse.quote_plus(query.strip())
    url     = f"https://duckduckgo.com/?q={encoded}"

    try:
        _open_in_browser(url, browser, incognito=incognito)
        mode = " incognito" if incognito else ""
        destination = f" in{mode} {browser}" if browser else f" in{mode} your browser"
        msg = f"Searching DuckDuckGo for: {query}{destination}."
        return {"display": msg, "speak": "Searching for that on the web."}
    except Exception as exc:
        msg = f"Failed to open browser for search: {exc}"
        return {"display": msg, "speak": "There was an error opening the browser to search."}
