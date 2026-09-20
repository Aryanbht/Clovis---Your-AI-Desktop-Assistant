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

import importlib
import logging

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import ui


_lazy_modules: dict[str, Any] = {}


def _tool(module_name: str) -> Any:
    """Lazy-import a tool module on first use, cache for subsequent calls."""
    if module_name not in _lazy_modules:
        _lazy_modules[module_name] = importlib.import_module(f"tools.{module_name}")
    return _lazy_modules[module_name]


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
# Tool modules are lazily imported on first dispatch to keep startup fast.

_INTENT_MAP: dict[str, Callable[..., str]] = {
    # ── File operations ────────────────────────────────────────────────────────
    "create_folder": lambda **p: _tool("file_ops").create_folder(**p),
    "create_file":   lambda **p: _tool("file_ops").create_file(**p),
    "list_files":    lambda **p: _tool("file_ops").list_files(**p),
    "delete_file":   lambda **p: _tool("file_ops").delete_file(**p),
    "delete_folder": lambda **p: _tool("file_ops").delete_file(**p),
    "move_file":     lambda **p: _tool("file_ops").move_file(**p),

    # ── Downloader ─────────────────────────────────────────────────────────────
    "download_file": lambda **p: _tool("downloader").download_file(**p),

    # ── Browser ────────────────────────────────────────────────────────────────
    "open_url":      lambda **p: _tool("browser").open_url(**p),
    "search_web":    lambda **p: _tool("browser").search_web(**p),

    # ── Gmail ──────────────────────────────────────────────────────────────────
    "open_gmail":    lambda **p: _tool("gmail").open_gmail(**p),
    "compose_email": lambda **p: _tool("gmail").compose_email(**p),

    # ── Messenger ──────────────────────────────────────────────────────────────
    "send_whatsapp": lambda **p: _tool("messenger").send_whatsapp(**p),
    "open_telegram": lambda **p: _tool("messenger").open_telegram(**p),
    "open_whatsapp": lambda **_: _tool("system_ops").open_app("whatsapp"),

    # ── System (fast-path actions also route here) ─────────────────────────────
    "screenshot":         lambda **p: _tool("system_ops").take_screenshot(**p),
    "folder_screenshot":  lambda **p: _tool("system_ops").folder_screenshot(**p),
    "lock_screen":        lambda **p: _tool("system_ops").lock_screen(**p),
    "open_app":           lambda **p: _tool("system_ops").open_app(**p),
    "tell_time":          lambda **_: _tool("system_ops").tell_time(),
    "tell_date":          lambda **_: _tool("system_ops").tell_date(),

    # ── Reminders ──────────────────────────────────────────────────────────────
    "set_reminder":      lambda **p: _tool("reminder").set_reminder(**p),
    "cancel_reminder":   lambda **p: _tool("reminder").cancel_reminder(**p),
    "list_reminders":    lambda **_: _tool("reminder").list_reminders(),
    "whats_my_schedule": lambda **_: _tool("reminder").get_todays_schedule(),
    "snooze_reminder":   lambda **p: _tool("reminder").snooze_reminder(**p),
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
