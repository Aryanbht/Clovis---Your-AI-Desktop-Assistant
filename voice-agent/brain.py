"""
brain.py – LLM communication layer for the voice assistant.

Responsibilities
────────────────
  • Load the system prompt from prompts/system_prompt.txt
  • POST transcripts to the local Ollama API
  • Extract and parse the JSON object embedded in the LLM response
  • Return a structured dict: {"intent": str, "params": dict, "response": str}
  • Expose is_ollama_running() for pre-flight health checks
"""

from __future__ import annotations

import json
import re
import socket
import urllib.parse
from pathlib import Path
from typing import TypedDict

import requests

from config import OLLAMA_MODEL, OLLAMA_URL


# ── Types ──────────────────────────────────────────────────────────────────────

class LLMResult(TypedDict):
    intent:   str
    params:   dict
    response: str


# ── Constants ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.txt"
_OLLAMA_TIMEOUT     = 60   # seconds before giving up on a generation request
_HEALTH_TIMEOUT     = 3    # seconds for the ping check

_FALLBACK: LLMResult = {
    "intent":   "unknown",
    "params":   {},
    "response": "Sorry, I didn't get that.",
}


# ══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

def _load_system_prompt() -> str:
    """
    Read the system prompt from disk.
    Falls back to a minimal inline prompt if the file is missing.
    """
    try:
        text = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
        if text:
            return text
    except FileNotFoundError:
        print(f"[Brain] ⚠️  System prompt not found at '{_SYSTEM_PROMPT_PATH}'. Using fallback.")
    except OSError as exc:
        print(f"[Brain] ⚠️  Could not read system prompt: {exc}. Using fallback.")

    return (
        "You are Clovis, a helpful voice assistant. "
        "Always reply with a JSON object containing: "
        "intent (string), params (object), response (string). "
        "Be concise — responses are spoken aloud."
    )


def _build_prompt(system_prompt: str, transcript: str) -> str:
    """Combine system prompt and user transcript into a single prompt string."""
    return f"{system_prompt}\n\nUser: {transcript}"


def _extract_json(raw: str) -> LLMResult:
    """
    Find and parse the first valid JSON object in *raw*.

    Uses a balanced-brace scan instead of a non-greedy regex so nested
    objects (e.g. ``{"params": {"path": "…"}}``) are captured correctly.
    Returns ``_FALLBACK`` on any failure.
    """
    # Strip markdown fences the model might add
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()

    # Find the first '{' and scan forward matching braces
    start = cleaned.find("{")
    if start == -1:
        print("[Brain] ⚠️  No JSON object found in LLM response.")
        print(f"[Brain]    Raw: {raw[:300]!r}")
        return dict(_FALLBACK)

    depth   = 0
    in_str  = False
    escape  = False
    end     = -1

    for i, ch in enumerate(cleaned[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        print("[Brain] ⚠️  Unbalanced braces in LLM response.")
        print(f"[Brain]    Raw: {raw[:300]!r}")
        return dict(_FALLBACK)

    json_str = cleaned[start:end]

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        print(f"[Brain] ⚠️  JSON decode error: {exc}")
        print(f"[Brain]    Attempted: {json_str[:300]!r}")
        return dict(_FALLBACK)

    # Normalise keys — handle both schemas the LLM might return:
    #   Expected:  {"intent":…, "params":…, "response":…}
    #   Fallback:  {"tool":…,   "action":…, "args":…}      (old prompt format)
    intent   = (
        data.get("intent")
        or data.get("tool")
        or data.get("action")
        or "unknown"
    )
    params   = (
        data.get("params")
        or data.get("args")
        or {}
    )
    response = (
        data.get("response")
        or data.get("message")
        or _FALLBACK["response"]
    )

    result: LLMResult = {
        "intent":   str(intent).strip().lower(),
        "params":   params if isinstance(params, dict) else {},
        "response": str(response).strip(),
    }
    return result



# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def is_ollama_running() -> bool:
    """
    Ping the Ollama server to check if it is reachable.

    Parses the host/port from ``OLLAMA_URL`` in config.py so there is no
    hard-coded address.

    Returns
    -------
    bool
        ``True`` if a TCP connection succeeds, ``False`` otherwise.
    """
    try:
        parsed = urllib.parse.urlparse(OLLAMA_URL)
        host   = parsed.hostname or "localhost"
        port   = parsed.port     or 11434

        with socket.create_connection((host, port), timeout=_HEALTH_TIMEOUT):
            return True

    except (OSError, socket.timeout):
        return False


def query(transcript: str) -> LLMResult:
    """
    Send *transcript* to the local Ollama LLM and return a structured result.

    Parameters
    ----------
    transcript : str
        The user's spoken command, already transcribed to text.

    Returns
    -------
    LLMResult
        A dict with keys ``intent`` (str), ``params`` (dict),
        and ``response`` (str).  Never raises — returns ``_FALLBACK`` on
        any error.
    """
    system_prompt = _load_system_prompt()
    full_prompt   = _build_prompt(system_prompt, transcript)

    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,
    }

    print(f"[Brain] Querying Ollama ({OLLAMA_MODEL}) …")

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=_OLLAMA_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("[Brain] ❌ Could not connect to Ollama. Is it running?  (ollama serve)")
        fallback = dict(_FALLBACK)
        fallback["response"] = (
            "I can't reach my language model right now. "
            "Please make sure Ollama is running."
        )
        return fallback
    except requests.exceptions.Timeout:
        print(f"[Brain] ❌ Ollama request timed out after {_OLLAMA_TIMEOUT} s.")
        fallback = dict(_FALLBACK)
        fallback["response"] = "The language model took too long to respond. Please try again."
        return fallback
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        if status == 404:
            print(
                f"[Brain] ❌ Ollama 404 — model '{OLLAMA_MODEL}' not found.\n"
                f"         Run this to download it:  ollama pull {OLLAMA_MODEL}"
            )
            fallback = dict(_FALLBACK)
            fallback["response"] = (
                f"The model {OLLAMA_MODEL} isn't downloaded yet. "
                f"Open a terminal and run: ollama pull {OLLAMA_MODEL}"
            )
            return fallback
        print(f"[Brain] ❌ Ollama HTTP error {status}: {exc}")
        return dict(_FALLBACK)
    except Exception as exc:
        print(f"[Brain] ❌ Unexpected error during LLM request: {exc}")
        return dict(_FALLBACK)

    try:
        body = resp.json()
    except json.JSONDecodeError:
        print("[Brain] ❌ Ollama returned non-JSON HTTP body.")
        return dict(_FALLBACK)

    raw_output: str = body.get("response", "")

    if not raw_output.strip():
        print("[Brain] ⚠️  Ollama returned an empty response field.")
        return dict(_FALLBACK)

    result = _extract_json(raw_output)
    print(f"[Brain] intent='{result['intent']}' | response='{result['response'][:80]}'")
    return result
