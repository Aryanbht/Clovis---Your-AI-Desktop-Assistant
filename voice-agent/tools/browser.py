"""
tools/browser.py – Open URLs and perform web searches using the system browser.
All functions return a plain string suitable for TTS output.
"""

from __future__ import annotations

import urllib.parse
import webbrowser


def open_url(url: str) -> str:
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
        webbrowser.open(url)
        return f"Opening {url} in your browser."
    except Exception as exc:
        return f"Failed to open browser: {exc}"


def search_web(query: str) -> str:
    """
    Search DuckDuckGo for *query* in the system's default web browser.

    Returns a success or failure message string.
    """
    if not query.strip():
        return "No search query provided."

    encoded = urllib.parse.quote_plus(query.strip())
    url     = f"https://duckduckgo.com/?q={encoded}"

    try:
        webbrowser.open(url)
        return f"Searching DuckDuckGo for: {query}"
    except Exception as exc:
        return f"Failed to open browser for search: {exc}"
