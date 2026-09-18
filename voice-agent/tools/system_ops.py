"""
tools/system_ops.py – OS-level operations: screenshots, screen lock, app launch.
Windows-focused. All functions return a plain string suitable for TTS output.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pyautogui

from config import DESKTOP_PATH


def take_screenshot(save_path: str | None = None) -> dict:
    """
    Capture the full screen and save it as a PNG.

    Parameters
    ----------
    save_path : str | None
        Full path to save the file. If None, saves to Desktop with a
        timestamped filename.

    Returns a success or failure message string.
    """
    if save_path:
        dest = Path(save_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest      = Path(DESKTOP_PATH) / f"screenshot_{timestamp}.png"

    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        time.sleep(0.3)
        img = pyautogui.screenshot()
        img.save(str(dest))
        msg = f"Screenshot saved to '{dest}'."
        return {"display": msg, "speak": "Screenshot saved."}
    except Exception as exc:
        msg = f"Failed to take screenshot: {exc}"
        return {"display": msg, "speak": "I couldn't take a screenshot."}


def folder_screenshot(folder_path: str) -> dict:
    """
    Create a folder (if it doesn't exist) and save a screenshot inside it.
    Used when the user says something like
    'create a folder called X on desktop and take a screenshot and save it there'.

    Parameters
    ----------
    folder_path : str
        Full path of the folder to create, e.g.
        'C:/Users/bhatn/OneDrive/Desktop/screenshots'

    Returns a combined success/failure message.
    """
    folder = Path(folder_path)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        folder_msg = f"Folder '{folder.name}' ready."
    except Exception as exc:
        msg = f"Failed to create folder: {exc}"
        return {"display": msg, "speak": "I couldn't create the folder."}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = folder / f"screenshot_{timestamp}.png"

    try:
        time.sleep(0.3)
        img = pyautogui.screenshot()
        img.save(str(dest))
        msg = f"{folder_msg} Screenshot saved inside it as '{dest.name}'."
        return {"display": msg, "speak": "Screenshot saved in folder."}
    except Exception as exc:
        msg = f"{folder_msg} But screenshot failed: {exc}"
        return {"display": msg, "speak": "Folder created, but screenshot failed."}



def lock_screen() -> dict:
    """
    Lock the Windows workstation immediately.
    Returns a success or failure message string.
    """
    if sys.platform != "win32":
        msg = "Screen locking via rundll32 is only supported on Windows."
        return {"display": msg, "speak": "I can only lock Windows computers."}

    result = os.system("rundll32.exe user32.dll,LockWorkStation")
    if result == 0:
        return {"display": "Screen locked.", "speak": "Locking your screen now."}
    return {"display": "Failed to lock screen.", "speak": "I couldn't lock your screen."}


def tell_time() -> dict:
    """Return the current local time."""
    t_str = datetime.now().strftime("%#I:%M %p" if sys.platform == "win32" else "%-I:%M %p")
    clean_time = t_str.replace(":", " ")
    msg = f"It's {t_str} right now."
    return {"display": msg, "speak": f"It is {clean_time} right now."}


def tell_date() -> dict:
    """Return the current local date."""
    d_str = datetime.now().strftime("%A, %d %B %Y")
    msg = f"Today is {d_str}."
    return {"display": msg, "speak": msg}


def open_app(app_name: str) -> dict:
    """
    Launch any installed application by name using fully dynamic fuzzy matching.

    Delegates to app_finder.find_and_launch() which uses Get-StartApps to
    discover every installed app on this system (Win32, Store, Electron).
    No hardcoded app list — works for any app the user has installed.

    Returns a dict with success or failure message.
    """
    from tools.app_finder import find_and_launch
    res = find_and_launch(app_name)
    return {"display": res, "speak": res}
