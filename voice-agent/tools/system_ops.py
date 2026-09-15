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


def take_screenshot(save_path: str | None = None) -> str:
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
        return f"Screenshot saved to '{dest}'."
    except Exception as exc:
        return f"Failed to take screenshot: {exc}"


def folder_screenshot(folder_path: str) -> str:
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
        return f"Failed to create folder: {exc}"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = folder / f"screenshot_{timestamp}.png"

    try:
        time.sleep(0.3)
        img = pyautogui.screenshot()
        img.save(str(dest))
        return f"{folder_msg} Screenshot saved inside it as '{dest.name}'."
    except Exception as exc:
        return f"{folder_msg} But screenshot failed: {exc}"



def lock_screen() -> str:
    """
    Lock the Windows workstation immediately.
    Returns a success or failure message string.
    """
    if sys.platform != "win32":
        return "Screen locking via rundll32 is only supported on Windows."

    ret = os.system("rundll32.exe user32.dll,LockWorkStation")
    if ret == 0:
        return "Locking the screen. See you soon!"
    return f"Lock screen command returned exit code {ret}."


def open_app(app_name: str) -> str:
    """
    Launch any installed application by name using fully dynamic fuzzy matching.

    Delegates to app_finder.find_and_launch() which uses Get-StartApps to
    discover every installed app on this system (Win32, Store, Electron).
    No hardcoded app list — works for any app the user has installed.

    Returns a success or failure message string.
    """
    from tools.app_finder import find_and_launch
    return find_and_launch(app_name)
