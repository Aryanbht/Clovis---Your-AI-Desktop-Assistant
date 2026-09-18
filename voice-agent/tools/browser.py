"""
tools/browser.py – Open URLs and perform web searches using the system browser.
All functions return a plain string suitable for TTS output.
"""

from __future__ import annotations

import urllib.parse
import webbrowser
import os
import subprocess
from pathlib import Path


def _open_in_browser(url: str, browser: str | None = None, incognito: bool = False) -> None:
    """Open *url* in the requested browser when it can be located."""
    requested = (browser or "").strip().lower()
    if requested in {"chrome", "google chrome"}:
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        executable = next((p for p in candidates if p.exists()), None)
        if executable:
            args = [str(executable)]
            if incognito:
                args.append("--incognito")
            args.append(url)
            subprocess.Popen(args, shell=False)
            return

    if requested in {"edge", "microsoft edge"}:
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        executable = next((p for p in candidates if p.exists()), None)
        if executable:
            args = [str(executable)]
            if incognito:
                args.append("--inprivate")
            args.append(url)
            subprocess.Popen(args, shell=False)
            return

    webbrowser.open(url)


def open_incognito(browser: str = "chrome") -> dict:
    """Open a private browser window on Windows."""
    requested = browser.strip().lower()
    browser_specs = {
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
    candidates, flag = browser_specs.get(requested, ([], "--incognito"))
    executable = next((path for path in candidates if path.exists()), None)
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

    # Ensure the URL has a scheme so webbrowser handles it correctly
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
