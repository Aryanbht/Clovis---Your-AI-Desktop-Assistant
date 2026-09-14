"""
tools/messenger.py – Messaging platform shortcuts via the system browser.
All functions return a plain string suitable for TTS output.
"""

from __future__ import annotations

import urllib.parse
import webbrowser

_WHATSAPP_BASE = "https://web.whatsapp.com/send"
_TELEGRAM_URL  = "https://web.telegram.org"


def send_whatsapp(phone_number: str, message: str) -> str:
    """
    Open WhatsApp Web with a pre-filled message to *phone_number*.

    Parameters
    ----------
    phone_number : str
        Must include the country code, digits only.
        Examples: '919876543210' (India), '14155552671' (USA).
    message : str
        The message text to pre-fill in the chat box.

    Returns a success or failure message string.

    Note
    ----
    WhatsApp Web must already be logged in on the browser.
    The message is NOT sent automatically — the user still presses Enter.
    """
    # Strip any stray characters (spaces, +, dashes) the user might include
    clean_phone = phone_number.strip().lstrip("+").replace(" ", "").replace("-", "")

    if not clean_phone.isdigit():
        return (
            f"Invalid phone number '{phone_number}'. "
            "Please provide digits only with country code, e.g. 919876543210."
        )

    params = urllib.parse.urlencode(
        {"phone": clean_phone, "text": message.strip()},
        quote_via=urllib.parse.quote,
    )
    url = f"{_WHATSAPP_BASE}?{params}"

    try:
        webbrowser.open(url)
        return f"Opening WhatsApp chat with +{clean_phone}. Press Enter to send."
    except Exception as exc:
        return f"Failed to open WhatsApp Web: {exc}"


def open_telegram() -> str:
    """
    Open Telegram Web in the system's default browser.

    Returns a success or failure message string.
    """
    try:
        webbrowser.open(_TELEGRAM_URL)
        return "Opening Telegram Web in your browser."
    except Exception as exc:
        return f"Failed to open Telegram: {exc}"
