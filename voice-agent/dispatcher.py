"""
dispatcher.py – Maps brain.py intents to tool function calls.

Usage
─────
    from dispatcher import dispatch

    result = brain.query(transcript)   # {"intent": ..., "params": ..., "response": ...}
    spoken = dispatch(result)          # executes the tool, returns text for TTS

Every dispatch is appended to agent.log with a timestamp.
"""

from __future__ import annotations

import logging

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from tools import browser, downloader, file_ops, gmail, messenger, system_ops, reminder
import ui


# ═══════════════════════════════════════════════════════════════════════════════
# Logger setup
# ═══════════════════════════════════════════════════════════════════════════════

_LOG_PATH = Path(__file__).parent / "agent.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",          # we build the line ourselves for full control
    handlers=[
        logging.FileHandler(_LOG_PATH, encoding="utf-8"),
    ],
)
_log = logging.getLogger("dispatcher")


def _log_event(intent: str, params: dict, tool_output: str, response: str) -> None:
    """Append a structured log line to agent.log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _log.info(
        "[%s] INTENT=%-20s | PARAMS=%s\n"
        "             TOOL_OUT=%-60s | SPOKEN=%s\n",
        ts, intent, params, tool_output[:120], response[:120],
    )
    ui.log_intent("LLM", intent, params)


# ═══════════════════════════════════════════════════════════════════════════════
# Intent -> tool function registry
# ═══════════════════════════════════════════════════════════════════════════════

# Each value is a callable that accepts **params from the brain result.
# Using lambdas keeps the mapping readable without wrapper functions.

_INTENT_MAP: dict[str, Callable[..., str]] = {
    # ── File operations ────────────────────────────────────────────────────────
    "create_folder": file_ops.create_folder,
    "create_file":   file_ops.create_file,
    "list_files":    file_ops.list_files,
    "delete_file":   file_ops.delete_file,
    "delete_folder": file_ops.delete_file,
    "move_file":     file_ops.move_file,

    # ── Downloader ─────────────────────────────────────────────────────────────
    "download_file": downloader.download_file,

    # ── Browser ────────────────────────────────────────────────────────────────
    "open_url":      browser.open_url,
    "search_web":    browser.search_web,

    # ── Gmail ──────────────────────────────────────────────────────────────────
    "open_gmail":    gmail.open_gmail,
    "compose_email": gmail.compose_email,

    # ── Messenger ───────────────────────────────────────────────
    "send_whatsapp":  messenger.send_whatsapp,
    "open_telegram":  messenger.open_telegram,
    "open_whatsapp":  lambda **_: system_ops.open_app("whatsapp"),

    # ── System (fast-path actions also route here) ─────────────────────────────
    "screenshot":         system_ops.take_screenshot,
    "folder_screenshot":  system_ops.folder_screenshot,
    "lock_screen":        system_ops.lock_screen,
    "open_app":           system_ops.open_app,
    "tell_time":          lambda **_: system_ops.tell_time(),
    "tell_date":          lambda **_: system_ops.tell_date(),

    # ── Reminders ──────────────────────────────────────────────────────────────
    "set_reminder":      reminder.set_reminder,
    "cancel_reminder":   reminder.cancel_reminder,
    "list_reminders":    lambda **_: reminder.list_reminders(),
    "whats_my_schedule": lambda **_: reminder.get_todays_schedule(),
    "snooze_reminder":   reminder.snooze_reminder,
}


# ════════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def dispatch(result: dict[str, Any], original_text: str = "") -> str:
    """
    Execute the tool implied by *result* and return the spoken response string.

    Parameters
    ----------
    result : dict
        A dict produced by ``brain.query()`` or ``router.fast_route()``.
        Expected keys:
          • ``"intent"``   – str, the action to perform
          • ``"params"``   – dict, keyword arguments forwarded to the tool
          • ``"response"`` – str, the text to speak after the action

    Returns
    -------
    str
        The ``"response"`` value from *result*, returned unchanged so the
        caller can pass it straight to ``tts.speak()``.

    Notes
    -----
    * Tool output (e.g. "File created at …") is logged but **not** spoken —
      the LLM's pre-composed ``response`` is used instead, keeping TTS
      output natural and consistent.
    * For ``"unknown"`` intent, no tool is called; the response is returned
      and logged as-is.
    * Any exception raised by a tool is caught, logged, and surfaced as the
      spoken response so the user always gets audible feedback.
    """
    intent:   str        = str(result.get("intent",   "unknown")).strip().lower()
    params:   dict       = result.get("params",   {}) or {}
    response: str        = str(result.get("response", "I'm not sure what to do.")).strip()

    # send_whatsapp now uses contact_name — no phone number required or checked.

    # ── Unknown intent ─────────────────────────────────────────────────────────
    if intent == "unknown":
        _log_event(intent, params, tool_output="(no tool called)", response=response)
        return response

    # ── Look up the tool ───────────────────────────────────────────────────────
    tool_fn = _INTENT_MAP.get(intent)

    if tool_fn is None:
        msg = f"No tool registered for intent '{intent}'."
        ui.console.print(f"[dim yellow][Dispatcher] {msg}[/dim yellow]")
        _log_event(intent, params, tool_output=msg, response=response)
        return response   # still speak the LLM's response; don't crash

    # ── Execute the tool ───────────────────────────────────────────────────────

    try:
        tool_result = tool_fn(**params)

        if isinstance(tool_result, dict) and "speak" in tool_result:
            ui.console.print(f"[dim]{tool_result['display']}[/dim]")  # rich output to console
            _log.info(tool_result["display"])    # log the display version
            tool_output_display = tool_result["display"]
            spoken = tool_result["speak"]        # clean version for TTS
        else:
            tool_result_str = str(tool_result or "(no output)")
            tool_output_display = tool_result_str
            spoken = tool_result_str

    except TypeError as exc:
        # Mismatched kwargs — likely a brain hallucination
        tool_output_display = f"Parameter error for '{intent}': {exc}"
        spoken = tool_output_display
        ui.show_error(tool_output_display)
    except Exception as exc:
        tool_output_display = f"Error executing '{intent}': {exc}"
        spoken = tool_output_display
        ui.show_error(tool_output_display)

    _first_line = tool_output_display.split("\n")[0][:120]

    # ── For data intents, the tool output IS the answer ────────────────────────
    # The LLM generates a vague summary before the tool runs, so it can't know
    # the actual content. For listing operations, print and return the real data.
    _DATA_INTENTS = {
        "list_files", "tell_time", "tell_date", 
        "set_reminder", "cancel_reminder", "list_reminders", 
        "whats_my_schedule", "snooze_reminder"
    }
    if intent in _DATA_INTENTS:
        _log_event(intent, params, tool_output=tool_output_display, response=spoken)
        return spoken          # chat.py / main.py prints this — no extra print here

    # ── Log and return ─────────────────────────────────────────────────────────
    _log_event(intent, params, tool_output=tool_output_display, response=response)
    return response


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_params(params: dict) -> str:
    """Format *params* as a compact kwarg-style string for console output."""
    if not params:
        return ""
    parts = [f"{k}={v!r}" for k, v in params.items()]
    return ", ".join(parts)