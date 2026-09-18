"""
tools/messenger.py – Messaging platform shortcuts.
Prefers the installed WhatsApp desktop app; falls back to WhatsApp Web.
All functions return a plain string suitable for TTS output.
"""

from __future__ import annotations

import subprocess
import time
import webbrowser

import pyautogui
import pyperclip


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_whatsapp_installed() -> bool:
    """
    Return True if WhatsApp desktop app is installed on this Windows system.
    Uses Get-StartApps (same source as app_finder) — no extra dependencies.
    """
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-StartApps | Where-Object { $_.Name -like '*WhatsApp*' } | "
                "ConvertTo-Json -Compress"
            ],
            capture_output=True, text=True, timeout=8
        )
        output = result.stdout.strip()
        return bool(output) and output not in ("null", "[]", "")
    except Exception:
        return False


def _launch_whatsapp_app() -> None:
    """Launch the WhatsApp desktop app via app_finder (reuses existing logic)."""
    from tools.app_finder import find_and_launch
    find_and_launch("whatsapp")


# ── Public API ────────────────────────────────────────────────────────────────

def send_whatsapp(contact_name: str, message: str) -> dict:
    """
    Send a WhatsApp message to *contact_name*.

    Priority:
      1. WhatsApp desktop app (if installed) — no browser needed.
      2. WhatsApp Web — fallback when the desktop app is absent.

    Parameters
    ----------
    contact_name : str
        The contact's name as it appears in WhatsApp (e.g. "Shivansh Goyal").
    message : str
        The message text to send.

    Returns a success or failure message string.
    """
    if not contact_name or not contact_name.strip():
        return {"display": "Please provide a contact name.", "speak": "You didn't provide a contact name."}
    if not message or not message.strip():
        return {"display": "Please provide a message to send.", "speak": "You didn't provide a message to send."}

    contact_name = contact_name.strip()
    message      = message.strip()

    if _is_whatsapp_installed():
        return _send_via_desktop_app(contact_name, message)
    else:
        return _send_via_web(contact_name, message)


def open_telegram() -> dict:
    """
    Open Telegram Web in the system's default browser.
    Returns a success or failure message string.
    """
    try:
        webbrowser.open("https://web.telegram.org")
        msg = "Opening Telegram Web in your browser."
        return {"display": msg, "speak": "Opening Telegram."}
    except Exception as exc:
        msg = f"Failed to open Telegram: {exc}"
        return {"display": msg, "speak": "I couldn't open Telegram."}


# ── Private implementations ───────────────────────────────────────────────────

def _send_via_desktop_app(contact_name: str, message: str) -> dict:
    """
    Automate the WhatsApp desktop app:
      1. Launch / bring to foreground.
      2. Press Ctrl+F to focus the search bar.
      3. Type the contact name and press Enter.
      4. Type the message and press Enter to send.
    """
    try:
        print(f"[Messenger] WhatsApp desktop app detected — launching …")
        _launch_whatsapp_app()
        time.sleep(4)          # wait for the app window to appear / come to front

        # Focus the search bar (Ctrl+F works in the WhatsApp Windows app)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.8)

        # Clear any previous text and type the contact name
        pyautogui.hotkey("ctrl", "a")
        pyperclip.copy(contact_name)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(2.0)        # let search results populate

        # Select the first result and open the chat
        pyautogui.press("down")
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(1.2)

        # Type and send the message
        pyperclip.copy(message)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyautogui.press("enter")

        msg = f"Message sent to {contact_name} on WhatsApp."
        return {"display": msg, "speak": f"Message sent to {contact_name}."}

    except Exception as exc:
        msg = f"Failed to send WhatsApp message via desktop app: {exc}"
        return {"display": msg, "speak": "I couldn't send the message."}


def _send_via_web(contact_name: str, message: str) -> dict:
    """
    Fallback: open WhatsApp Web, search for the contact by name, and send.
    """
    try:
        print(f"[Messenger] WhatsApp desktop not found — using WhatsApp Web …")
        webbrowser.open("https://web.whatsapp.com")
        time.sleep(6)          # wait for WhatsApp Web to fully load

        # Focus the search bar (Ctrl+/ is the WhatsApp Web shortcut)
        pyautogui.hotkey("ctrl", "/")
        time.sleep(0.8)

        pyautogui.hotkey("ctrl", "a")
        pyperclip.copy(contact_name)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(2.5)

        pyautogui.press("down")
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(1.5)

        pyperclip.copy(message)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyautogui.press("enter")

        msg = f"Message sent to {contact_name} on WhatsApp."
        return {"display": msg, "speak": f"Message sent to {contact_name}."}

    except Exception as exc:
        msg = f"Failed to send WhatsApp message via web: {exc}"
        return {"display": msg, "speak": "I couldn't send the message."}
