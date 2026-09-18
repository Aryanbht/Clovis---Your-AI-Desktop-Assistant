"""
tools/gmail.py – Gmail shortcuts via the system browser.
All functions return a plain string suitable for TTS output.
"""

from __future__ import annotations

import urllib.parse
import webbrowser

_GMAIL_BASE    = "https://mail.google.com/mail/"
_COMPOSE_BASE  = _GMAIL_BASE + "?view=cm"


def open_gmail() -> dict:
    """
    Open the Gmail inbox in the system's default browser.

    Returns a success or failure message string.
    """
    try:
        webbrowser.open(_GMAIL_BASE + "#inbox")
        msg = "Opening Gmail inbox in your browser."
        return {"display": msg, "speak": "Opening Gmail for you."}
    except Exception as exc:
        msg = f"Failed to open Gmail: {exc}"
        return {"display": msg, "speak": "There was an error opening Gmail."}


def compose_email(to: str, subject: str = "", body: str = "") -> dict:
    """
    Open Gmail's compose window pre-filled with *to*, *subject*, and *body*.

    All parameters are URL-encoded before being appended to the compose URL.

    Returns a success or failure message string.
    """
    if not to.strip():
        return {"display": "Please provide a recipient email address.", "speak": "You didn't provide an email address."}

    params: dict[str, str] = {"to": to.strip()}

    if subject.strip():
        params["su"] = subject.strip()
    if body.strip():
        params["body"] = body.strip()

    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url          = f"{_COMPOSE_BASE}&{query_string}"

    try:
        webbrowser.open(url)
        msg = f"Opening compose window for {to}."
        return {"display": msg, "speak": "Composing email."}
    except Exception as exc:
        msg = f"Failed to open compose window: {exc}"
        return {"display": msg, "speak": "I couldn't open the email composer."}
