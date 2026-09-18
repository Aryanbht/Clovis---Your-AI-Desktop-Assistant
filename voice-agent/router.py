"""
router.py – Core decision layer for the voice assistant.

Architecture
────────────
  fast_route(transcript)
      │
      ├─► FAST PATH  → handle_fast_intent()  → dict {"response", "action"}
      │                 (pure Python, no GPU, <5 ms)
      │
      └─► None  →  caller sends transcript to Ollama (LLM PATH)

Fast-path intents are detected via regex BEFORE touching the LLM, keeping
latency near-zero for common commands.
"""

from __future__ import annotations

import ast
import math
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TypedDict

import pyautogui

from config import DESKTOP_PATH


# ── Return type ────────────────────────────────────────────────────────────────

class RouteResult(TypedDict):
    response: str          # text to be spoken
    action:   str | None   # optional action tag for callers to react to


# ══════════════════════════════════════════════════════════════════════════════
# 1.  REGEX PATTERN TABLE
#     Keys   → intent name (str)
#     Values → compiled regex (re.Pattern); matched against lower-cased text
# ══════════════════════════════════════════════════════════════════════════════

_PATTERNS: dict[str, re.Pattern] = {
    # ── Greetings ──────────────────────────────────────────────────────────────
    "greet": re.compile(
        r"\b(hell+o+|hi+|hey+|good\s*(morning|afternoon|evening|night|day)|wassup|what'?s\s*up|howdy|greetings|yo)\b"
    ),

    # ── Time & Date ────────────────────────────────────────────────────────────
    "tell_time": re.compile(
        r"\b(what(\s*is|\s*'?s)?\s*the\s*time|current\s*time|tell\s*me\s*the\s*time"
        r"|what\s*time\s*is\s*it|time\s*now|what'?s?\s*time|time\s*is\s*it"
        r"|what\s*is\s*time|current\s*time\s*please|tell\s*time)"
    ),
    "tell_date": re.compile(
        r"\b(what(\s*is|\s*'?s)?\s*(the\s*)?(date|day)|today'?s?\s*date"
        r"|which\s*day|what\s*day\s*is\s*(it|today)|date\s*today"
        r"|what'?s?\s*(today|the\s*date)|tell\s*me\s*the\s*date)\b"
    ),

    # ── Quick math ─────────────────────────────────────────────────────────────
    "quick_math": re.compile(
        r"(?:"
        r"\b(what\s*is|calculate|compute|solve|evaluate)\b.*"
        r"(\d|zero|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
        r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
        r"eighty|ninety)\b"
        r"|^\s*[\d\(][\d\s\+\-\*\/\%\^\(\)\.]*[\+\-\*\/\%\^][\d\s\+\-\*\/\%\^\(\)\.]*[\d\)]\s*$"
        r")"
    ),

    # Private browser window
    "incognito": re.compile(
        r"\b(open|start|launch)\s+(?:an?\s+)?incognito"
        r"(?:\s+(?:window|mode))?(?:\s+(?:on|in))?\s*"
        r"(?:chrome|google\s+chrome|edge|firefox)?\b"
    ),

    # ── App launcher ───────────────────────────────────────────────────────────
    "open_app": re.compile(
        r"\b(?:could\s+you\s+(?:please\s+)?|please\s+|would\s+you\s+(?:mind\s+)?|can\s+you\s+(?:please\s+)?|just\s+)?"
        r"(?:open|launch|start|run)\s+"
        r"(?:the\s+)?"
        r"(chrome|google\s*chrome|firefox|edge|microsoft\s*edge|brave|chrome\s+browser|firefox\s+browser|edge\s+browser"
        r"|notepad|notepad\+\+"
        r"|vs\s*code|vscode|visual\s*studio\s*code"
        r"|calculator|calc|file\s*explorer|explorer"
        r"|task\s*manager|taskmgr"
        r"|whatsapp|telegram|discord|slack|zoom"
        r"|spotify|vlc|steam"
        r"|paint|word|excel|powerpoint|outlook|teams"
        r"|cmd|terminal|powershell|command\s*prompt|settings"
        r"|windows\s*terminal)\b"
    ),

    # ── Volume ─────────────────────────────────────────────────────────────────
    "volume_up": re.compile(
        r"\b(volume\s*up|increase\s*(the\s*)?volume|turn\s*(it\s*)?up|louder)\b"
    ),
    "volume_down": re.compile(
        r"\b(volume\s*down|decrease\s*(the\s*)?volume|turn\s*(it\s*)?down|quieter|softer)\b"
    ),
    "mute": re.compile(
        r"\b(mute|silence|shut\s*up|stop\s*(the\s*)?sound|unmute)\b"
    ),

    # -- Screenshot (ONLY standalone, simple commands go through fast path) ------
    # Complex commands like "create a folder and save screenshot there" must
    # fall through to the LLM so it can reason about all the steps.
    # The regex is anchored (^...$) so it only matches if the ENTIRE command
    # is essentially just "take a screenshot" with nothing else complex.
    "screenshot": re.compile(
        r"^\s*(?:please\s+)?(?:just\s+)?"
        r"(?:take|capture|grab|snap)\s+(?:a\s+)?(?:quick\s+)?screen\s*shot"
        r"\s*(?:please|now|for\s+me)?\s*$"
        r"|^\s*screenshot\s*(?:please|now)?\s*$",
        re.IGNORECASE,
    ),

    # ── Lock screen ────────────────────────────────────────────────────────────
    "lock_screen": re.compile(
        r"\b(lock\s*(the\s*)?((screen|computer|pc|system))?|lock\s*down)\b"
    ),

    # ── WhatsApp messaging ───────────────────────────────────────────────────────
    "send_whatsapp": re.compile(
        r"\b(send|message|msg|text)\s+"
        r"(?:"
        r"(?:a\s+)?(?:message\s+)?(?:to\s+)?[a-zA-Z\s]+?\s+(?:on\s+)?(?:whatsapp|wa)"
        r"|"
        r"(?:a\s+)?(?:message\s+)?(?:whatsapp|wa)\s+to\s+[a-zA-Z\s]+?"
        r")"
        r"\b",
        re.IGNORECASE,
    ),

    # ── Acknowledgements ───────────────────────────────────────────────────────
    "acknowledge": re.compile(
        r"\b(thanks?|thank\s*you|cheers|much\s*appreciated|great|awesome|perfect|nice\s*one|cool)\b"
    ),

    # ── Farewell ───────────────────────────────────────────────────────────────
    "farewell": re.compile(
        r"\b(bye|goodbye|see\s*you|later|that'?s?\s*all|stop\s*listening|go\s*to\s*sleep|dismiss)\b"
    ),
}


# ══════════════════════════════════════════════════════════════════════════════
# 2.  HELPER UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def get_time_of_day() -> str:
    """Return 'morning', 'afternoon', or 'evening' based on the current hour."""
    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    return "evening"


def _now_time_str() -> str:
    """Return a human-readable current time string, e.g. '3:45 PM'."""
    return datetime.now().strftime("%-I:%M %p") if sys.platform != "win32" else \
           datetime.now().strftime("%#I:%M %p")


def _now_date_str() -> str:
    """Return a human-readable current date string, e.g. 'Monday, 13 September 2026'."""
    return datetime.now().strftime("%A, %d %B %Y")


def _eval_math(transcript: str) -> str | None:
    """
    Try to extract and evaluate a simple arithmetic expression from *transcript*.
    Converts spoken words to operators before eval-ing.
    Returns a formatted result string, or None if evaluation fails.
    """
    # Normalise spoken operators.
    text = transcript.lower()
    text = re.sub(r"\bplus\b",                                    "+",   text)
    text = re.sub(r"\bminus\b|\bsubtracted\s*by\b",              "-",   text)
    text = re.sub(r"\btimes\b|\btime\b|\bmultiply(ed)?\s*by\b|\bx\b", "*", text)
    text = re.sub(r"\bdivided?\s*by\b|\bover\b",                  "/",   text)
    text = re.sub(r"\bto\s*the\s*power\s*(of\s*)?\b|\bexponent\b|\braised?\s*to\b", "**", text)
    text = re.sub(r"\bmod(ulo)?\b",                               "%",   text)
    text = re.sub(r"\bsquare\s*root\s*(of\s*)?(\d+)",            r"sqrt(\2)", text)

    number_words = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
        "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90,
    }

    def _number_phrase(match: re.Match) -> str:
        total = 0
        current = 0
        for word in match.group(0).split():
            if word == "hundred":
                current = max(current, 1) * 100
            elif word == "thousand":
                total += max(current, 1) * 1000
                current = 0
            else:
                current += number_words[word]
        return str(total + current)

    word_pattern = (
        r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
        r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
        r"eighty|ninety|hundred|thousand)(?:\s+(?:zero|one|two|three|"
        r"four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
        r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
        r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
        r"thousand))*\b"
    )
    text = re.sub(word_pattern, _number_phrase, text)

    # Extract a safe-looking numeric expression
    # Start at a digit so whitespace after "what is" is never treated as the
    # expression. This keeps inputs such as "what is 890 + 890" reliable.
    match = re.search(r"[\d\(][\d\s\+\-\*\/\%\^\(\)\.]*[\d\)]|\d", text)
    if not match:
        return None

    expr = match.group().strip().replace("^", "**")
    # Treat spoken numbers such as "09" as ordinary decimal numbers.
    expr = re.sub(r"\b0+(\d+)\b", r"\1", expr)
    if not expr or expr in "+-*/":
        return None

    try:
        tree = ast.parse(expr, mode="eval")

        def _calculate(node: ast.AST) -> int | float:
            if isinstance(node, ast.Expression):
                return _calculate(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = _calculate(node.operand)
                return value if isinstance(node.op, ast.UAdd) else -value
            if isinstance(node, ast.BinOp):
                left = _calculate(node.left)
                right = _calculate(node.right)
                if isinstance(node.op, ast.Add):
                    return left + right
                if isinstance(node.op, ast.Sub):
                    return left - right
                if isinstance(node.op, ast.Mult):
                    return left * right
                if isinstance(node.op, ast.Div):
                    return left / right
                if isinstance(node.op, ast.Mod):
                    return left % right
                if isinstance(node.op, ast.Pow):
                    if abs(right) > 1000:
                        raise ValueError("exponent too large")
                    return left ** right
            raise ValueError("unsupported expression")

        result = _calculate(tree)
        # Format: drop .0 for whole numbers
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return str(result)
    except Exception:
        return None


def _extract_app_name(transcript: str) -> str:
    """Pull the app name from a 'open X' utterance."""
    match = re.search(
        r"\b(open|launch|start|run)\s+(.+?)(\s+for\s+me|\s+please|$)",
        transcript.lower()
    )
    app_name = match.group(2).strip() if match else transcript.strip()
    
    # Normalize common app name variations
    normalizations = {
        "chrome browser": "chrome",
        "google chrome browser": "chrome",
        "firefox browser": "firefox",
        "edge browser": "edge",
        "microsoft edge browser": "edge",
        "vs code": "vscode",
        "visual studio code": "vscode",
        "cmd": "command prompt",
        "terminal": "windows terminal",
    }
    return normalizations.get(app_name, app_name)


def _launch_app(app_name: str) -> str:
    """
    Delegate to system_ops.open_app — single source of truth for app launching.
    Returns 'launched' or 'not_found'.
    """
    from tools.system_ops import open_app as _sys_open_app
    result = _sys_open_app(app_name)
    
    if isinstance(result, dict):
        result = result.get("speak", str(result))
        
    # system_ops.open_app returns a human string; treat anything starting with
    # "Opening" or "Launched" as success, everything else as failure.
    if result.lower().startswith(("opening", "launched")):
        return "launched"
    return "not_found"


def _get_master_volume_endpoint():
    """Return Windows' default master-volume endpoint, or an error message."""
    if sys.platform != "win32":
        return None, "Direct volume control is only supported on Windows."

    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        device = AudioUtilities.GetSpeakers()

        # pycaw 2025+ exposes the endpoint directly. Keep the older fallback
        # for installations that still expose the Windows COM Activate method.
        endpoint = getattr(device, "EndpointVolume", None)
        if endpoint is not None:
            return endpoint, None

        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume)), None
    except ImportError:
        return None, "Volume control needs the 'pycaw' package. Run: pip install -r requirements.txt"
    except Exception as exc:
        return None, f"Couldn't access the Windows volume control: {exc}"


def _change_master_volume(delta: int) -> tuple[int, int] | tuple[None, str]:
    """Change master volume by an exact number of percentage points."""
    endpoint, error = _get_master_volume_endpoint()
    if endpoint is None:
        return None, error

    current = round(endpoint.GetMasterVolumeLevelScalar() * 100)
    target = max(0, min(100, current + delta))
    endpoint.SetMasterVolumeLevelScalar(target / 100, None)
    return current, target


def _volume_amount(transcript: str) -> int:
    """Extract a requested percentage-point change, defaulting to 10."""
    match = re.search(r"\b(?:by\s+)?(\d{1,3})\b", transcript)
    if not match:
        return 10
    return max(0, min(int(match.group(1)), 100))


def _handle_website_in_browser(transcript: str) -> RouteResult | None:
    """Normalize website-and-browser wording to one URL-opening action."""
    match = re.search(
        r"\b(?:open|search|browse|visit|go\s+to)\s+"
        r"(?P<site>youtube|gmail|google|facebook|instagram|twitter|x)"
        r"(?:\.com)?\s+(?:on|in|using)\s+"
        r"(?P<browser>chrome|google\s+chrome|edge|microsoft\s+edge|firefox)\b",
        transcript.lower(),
    )
    if not match:
        return None

    urls = {
        "youtube": "https://www.youtube.com",
        "gmail": "https://mail.google.com",
        "google": "https://www.google.com",
        "facebook": "https://www.facebook.com",
        "instagram": "https://www.instagram.com",
        "twitter": "https://twitter.com",
        "x": "https://x.com",
    }
    from tools.browser import open_url

    site = match.group("site")
    browser = match.group("browser")
    result = open_url(urls[site], browser)
    return RouteResult(response=result, action="open_url")


def _handle_search_incognito(transcript: str) -> RouteResult | None:
    """Search a query in a private browser window without relying on Ollama."""
    match = re.search(
        r"\b(?:search|look\s+up|find)\s+(?P<query>.+?)\s+"
        r"(?:in|on)\s+(?:an?\s+)?incognito(?:\s+(?:mode|window))?\s+"
        r"(?:on|in|using)\s+(?P<browser>chrome|google\s+chrome|edge|microsoft\s+edge|firefox)\b",
        transcript.lower(),
    )
    if not match:
        return None

    from tools.browser import search_web
    result = search_web(
        match.group("query").strip(),
        browser=match.group("browser"),
        incognito=True,
    )
    return RouteResult(response=result, action="search_incognito")


def _is_standalone_greeting(transcript: str) -> bool:
    """Return True only when the complete input is a greeting, not a command."""
    return bool(re.fullmatch(
        r"\s*(?:hell+o+|hi+|hey+|howdy|greetings|yo|wassup|"
        r"what'?s\s*up|good\s*(?:morning|afternoon|evening|night|day))"
        r"(?:\s+clovis)?[\s!,.?]*",
        transcript.lower(),
    ))


def _handle_folder_screenshot_sequence(transcript: str) -> RouteResult | None:
    """
    Handle compound commands that ask to:
      1. Create a folder (on the Desktop)
      2. Take a screenshot
      3. Save it in that folder

    Handles any word order and natural phrasings, e.g.:
      - "create a folder called X on desktop and take a screenshot and save it there"
      - "create a folder on my desktop named X and take a screenshot and save"
      - "make a folder named screenshots on the desktop, take a screenshot and save it in that folder"
    """
    low = transcript.lower()

    # Must mention: folder creation, screenshot, and saving
    has_folder    = bool(re.search(r"\b(create|make)\b.{0,20}\bfolder\b", low))
    has_screenshot = bool(re.search(r"\b(take|capture|save)?\s*(a\s+)?screenshot\b", low))
    has_save      = bool(re.search(r"\b(save|store|put)\b", low))

    if not (has_folder and has_screenshot):
        return None

    # Extract folder name — try multiple patterns to cover common phrasings
    folder_name: str | None = None

    name_patterns = [
        # "folder called/named X on desktop"
        r"\bfolder\s+(?:called|named|by\s+(?:the\s+name\s+)?(?:of\s+)?)\s*['\"]?(?P<name>[a-zA-Z0-9_ \-]+?)['\"]?\s+(?:on|in|to)\b",
        # "folder on [my/the] desktop called/named X"
        r"\bfolder\s+(?:on|in)\s+(?:my|the)\s+desktop\s+(?:called|named|by\s+(?:the\s+name\s+)?(?:of\s+)?)\s*['\"]?(?P<name>[a-zA-Z0-9_ \-]+?)['\"]?\s+(?:and|,|\.|$)",
        # "folder named/called X" (no location qualifier)
        r"\bfolder\s+(?:called|named)\s+['\"]?(?P<name>[a-zA-Z0-9_ \-]+?)['\"]?\s+(?:on|in|and|,|to|\.|$)",
        # "a folder [by the name] X"
        r"\ba\s+folder\s+(?:by\s+(?:the\s+name\s+(?:of\s+)?)?)?['\"]?(?P<name>[a-zA-Z0-9_ \-]+?)['\"]?\s+(?:on|in|and|,|to|\.|$)",
    ]

    for pat in name_patterns:
        m = re.search(pat, low)
        if m:
            folder_name = m.group("name").strip(" .")
            break

    if not folder_name:
        return None

    from tools import file_ops, system_ops

    folder_path   = Path(DESKTOP_PATH) / folder_name
    folder_result = file_ops.create_folder(str(folder_path))
    if folder_result.lower().startswith(("permission denied", "failed")):
        return RouteResult(response=folder_result, action=None)

    timestamp       = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = folder_path / f"screenshot_{timestamp}.png"
    screenshot_result = system_ops.take_screenshot(str(screenshot_path))

    return RouteResult(
        response=f"{folder_result} {screenshot_result}",
        action="folder_screenshot_sequence",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 3.  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def fast_route(transcript: str) -> RouteResult | None:
    """
    Try to match *transcript* against fast-path patterns.

    Returns a :class:`RouteResult` dict if a fast intent is found,
    or ``None`` to signal that the caller should use the LLM path.
    """
    import string
    lower = transcript.lower().strip().strip(string.punctuation)

    private_search_result = _handle_search_incognito(lower)
    if private_search_result is not None:
        return private_search_result

    website_result = _handle_website_in_browser(lower)
    if website_result is not None:
        return website_result

    # Compound operations must run before the single-action regex table.  For
    # example, otherwise the word "screenshot" would cause the folder request
    # earlier in the sentence to be ignored.
    compound_result = _handle_folder_screenshot_sequence(lower)
    if compound_result is not None:
        return compound_result

    for intent, pattern in _PATTERNS.items():
        if pattern.search(lower):
            # A greeting word may occur in a message body, e.g. "send ...
            # on WhatsApp: hii bhai". It must not override the actual command.
            if intent == "greet" and not _is_standalone_greeting(lower):
                continue
            return handle_fast_intent(intent, transcript)

    return None  # → LLM PATH


def handle_fast_intent(intent: str, transcript: str) -> RouteResult:
    """
    Dispatch *intent* to the appropriate handler and return a RouteResult.

    Each handler is a private function below that returns (response, action).
    """
    handlers = {
        "greet":          _handle_greet,
        "tell_time":      _handle_tell_time,
        "tell_date":      _handle_tell_date,
        "quick_math":     _handle_quick_math,
        "incognito":      _handle_incognito,
        "open_app":       _handle_open_app,
        "volume_up":      _handle_volume_up,
        "volume_down":    _handle_volume_down,
        "mute":           _handle_mute,
        "screenshot":     _handle_screenshot,
        "lock_screen":    _handle_lock_screen,
        "send_whatsapp":  _handle_send_whatsapp,
        "acknowledge":    _handle_acknowledge,
        "farewell":       _handle_farewell,
    }
    handler = handlers.get(intent, _handle_unknown)
    response, action = handler(transcript)
    return RouteResult(response=response, action=action)


# ══════════════════════════════════════════════════════════════════════════════
# 4.  INDIVIDUAL INTENT HANDLERS
#     Signature: (transcript: str) -> tuple[str, str | None]
#                                            ↑ response  ↑ action tag
# ══════════════════════════════════════════════════════════════════════════════

def _handle_greet(transcript: str) -> tuple[str, None]:
    tod = get_time_of_day()
    return f"Hey Aryan, good {tod}. What do you need?", None


def _handle_tell_time(transcript: str) -> tuple[str, None]:
    t_str = _now_time_str().replace(":", " ")
    return f"It is {t_str} right now.", None


def _handle_tell_date(transcript: str) -> tuple[str, None]:
    return f"Today is {_now_date_str()}.", None


def _handle_quick_math(transcript: str) -> tuple[str, None]:
    result = _eval_math(transcript)
    if result is not None:
        return f"The answer is {result}.", None
    return "Sorry, I couldn't work that out. Could you rephrase it?", None


def _handle_incognito(transcript: str) -> tuple[str, str | None]:
    match = re.search(
        r"\b(?:on|in)\s+(chrome|google\s+chrome|edge|firefox)\b",
        transcript.lower(),
    )
    browser = match.group(1) if match else "chrome"

    from tools.browser import open_incognito
    response = open_incognito(browser)
    if isinstance(response, dict):
        return response["speak"], "incognito"
    return response, "incognito" if response.lower().startswith("opening") else None


def _handle_open_app(transcript: str) -> tuple[str, str]:
    app_name = _extract_app_name(transcript)
    status   = _launch_app(app_name)
    if status == "launched":
        return f"Opening {app_name.title()}.", "open_app"
    return f"I couldn't find {app_name.title()} on your PC.", None


def _handle_volume_up(transcript: str) -> tuple[str, str]:
    amount = _volume_amount(transcript)
    current, result = _change_master_volume(amount)
    if current is None:
        return result, None
    return "Volume increased.", "volume_up"


def _handle_volume_down(transcript: str) -> tuple[str, str]:
    amount = _volume_amount(transcript)
    current, result = _change_master_volume(-amount)
    if current is None:
        return result, None
    return "Volume decreased.", "volume_down"


def _handle_mute(transcript: str) -> tuple[str, str]:
    pyautogui.press("volumemute")
    return "Muted.", "mute"


def _handle_screenshot(transcript: str) -> tuple[str, str]:
    import time
    from config import DESKTOP_PATH

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = os.path.join(DESKTOP_PATH, f"screenshot_{timestamp}.png")

    time.sleep(0.3)  # small delay so the assistant UI doesn't appear in shot
    img = pyautogui.screenshot()
    img.save(save_path)
    return "Screenshot saved.", "screenshot"


def _handle_lock_screen(_transcript: str) -> tuple[str, str]:
    if sys.platform == "win32":
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return "Locking your screen.", "lock_screen"
    return "Screen locking is only supported on Windows.", None


def _handle_send_whatsapp(transcript: str) -> tuple[str, str | None]:
    """Extract contact name and message from WhatsApp send command.
    
    Handles multiple patterns:
    - "send message to John on whatsapp hello"
    - "message John on whatsapp hello"
    - "send whatsapp to John saying hello"
    - "can you send a whatsapp to John saying hello"
    - "send a message to John on whatsapp hello"
    """
    # Patterns in priority order
    patterns = [
        # Pattern 1: "send whatsapp to NAME saying MESSAGE" (handles "a whatsapp to")
        r"\b(send|message|msg|text)\s+(?:a\s+)?(?:message\s+)?(?:whatsapp|wa)\s+to\s+([a-zA-Z\s]+?)\s+(?:saying|with\s+message\s+)\s+(.+)",
        # Pattern 2: "send whatsapp to NAME MESSAGE" (no saying keyword)
        r"\b(send|message|msg|text)\s+(?:a\s+)?(?:message\s+)?(?:whatsapp|wa)\s+to\s+([a-zA-Z\s]+?)\s+(.+)",
        # Pattern 3: "send message to NAME on whatsapp MESSAGE"
        r"\b(send|message|msg|text)\s+(?:a\s+)?(?:message\s+)?(?:to\s+)?([a-zA-Z\s]+?)\s+(?:on\s+)?(?:whatsapp|wa)\s+(.+)",
    ]
    
    contact_name = None
    message = None
    
    for pattern in patterns:
        match = re.search(pattern, transcript, re.IGNORECASE)
        if match:
            contact_name = match.group(2).strip().title()
            message = match.group(3).strip()
            break
    
    if not contact_name or not message:
        return "I couldn't understand the WhatsApp message. Try: 'message John on whatsapp hello'", None

    from tools.messenger import send_whatsapp
    result = send_whatsapp(contact_name, message)
    if isinstance(result, dict):
        return result["speak"], "send_whatsapp"
    return result, "send_whatsapp"


def _handle_acknowledge(_transcript: str) -> tuple[str, None]:
    return "Anytime Aryan.", None


def _handle_farewell(_transcript: str) -> tuple[str, str]:
    return "Going quiet. Call me when you need me.", "farewell"


def _handle_unknown(_transcript: str) -> tuple[str, None]:
    return "I am not sure how to handle that directly. Let me think.", None
