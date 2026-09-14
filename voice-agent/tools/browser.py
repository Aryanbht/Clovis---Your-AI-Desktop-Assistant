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


def open_incognito(browser: str = "chrome") -> str:
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
            return f"Opening a private {browser} window."
        except Exception as exc:
            return f"Failed to open private {browser}: {exc}"
    return f"I couldn't find {browser} on this system."


def open_url(url: str, browser: str | None = None) -> str:
    """
    Open *url* in the system's default web browser.

    Automatically prepends 'https://' if no scheme is present.

    Returns a success or failure message string.
    """
    if not url.strip():
        return "No URL provided."

    # Ensure the URL has a scheme so webbrowser handles it correctly
    if not url.startswith(("http://", "https://", "ftp://")):
        url = "https://" + url

    try:
        _open_in_browser(url, browser)
        destination = f" in {browser}" if browser else " in your browser"
        return f"Opening {url}{destination}."
    except Exception as exc:
        return f"Failed to open browser: {exc}"


def search_web(query: str, browser: str | None = None, incognito: bool = False) -> str:
    """
    Search DuckDuckGo for *query* in the system's default web browser.

    Returns a success or failure message string.
    """
    if not query.strip():
        return "No search query provided."

    encoded = urllib.parse.quote_plus(query.strip())
    url     = f"https://duckduckgo.com/?q={encoded}"

    try:
        _open_in_browser(url, browser, incognito=incognito)
        mode = " incognito" if incognito else ""
        destination = f" in{mode} {browser}" if browser else f" in{mode} your browser"
        return f"Searching DuckDuckGo for: {query}{destination}."
    except Exception as exc:
        return f"Failed to open browser for search: {exc}"
