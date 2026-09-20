# -*- coding: utf-8 -*-
"""
setup_check.py — Pre-flight environment validator for Clovis.

Run this to quickly verify that everything is in order before starting the
voice assistant:

    python setup_check.py

Exit codes:
    0 — All checks passed (warnings are OK)
    1 — One or more critical checks failed
"""

from __future__ import annotations

import importlib
import shutil
import socket
import sys

# Ensure UTF-8 output so Unicode box-drawing characters render correctly
# even when PYTHONIOENCODING is not set by the user.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Formatting helpers ─────────────────────────────────────────────────────────

OK   = "  [OK]  "
WARN = "  [WARN]"
FAIL = "  [FAIL]"
INFO = "  [INFO]"

_failures: list[str] = []
_warnings: list[str] = []


def _ok(msg: str) -> None:
    print(f"{OK}  {msg}")


def _warn(msg: str) -> None:
    print(f"{WARN} {msg}")
    _warnings.append(msg)


def _fail(msg: str) -> None:
    print(f"{FAIL}  {msg}")
    _failures.append(msg)


def _info(msg: str) -> None:
    print(f"{INFO} {msg}")


def _header(title: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {title}")
    print(f"{'─' * 50}")


# ══════════════════════════════════════════════════════════════════════════════
# Checks
# ══════════════════════════════════════════════════════════════════════════════

def check_python() -> None:
    _header("Python")
    major, minor = sys.version_info[:2]
    ver = f"{major}.{minor}.{sys.version_info[2]}"
    if major < 3 or (major == 3 and minor < 10):
        _fail(f"Python 3.10+ required — found {ver}")
    else:
        _ok(f"Python {ver}")

    if sys.platform != "win32":
        _warn("Not running on Windows. Some features (pycaw, winreg) won't work.")
    else:
        _ok("Running on Windows")


def check_packages() -> None:
    _header("Python Packages")

    required = {
        "faster_whisper": "faster-whisper",
        "sounddevice":    "sounddevice",
        "scipy":          "scipy",
        "numpy":          "numpy",
        "requests":       "requests",
        "pyttsx3":        "pyttsx3",
        "edge_tts":       "edge-tts",
        "pyautogui":      "pyautogui",
        "tqdm":           "tqdm",
    }
    optional = {
        "ollama":        "ollama (Python client, optional)",
        "playsound":     "playsound",
        "pycaw":         "pycaw (volume control)",
        "win32api":      "pywin32 (required by pycaw)",
        "pyperclip":     "pyperclip (WhatsApp messaging)",
    }

    for module, label in required.items():
        try:
            importlib.import_module(module)
            _ok(label)
        except ImportError:
            _fail(f"{label} — not installed  (pip install {label})")

    for module, label in optional.items():
        try:
            importlib.import_module(module)
            _ok(f"{label} (optional)")
        except ImportError:
            _warn(f"{label} not installed — some features may not work")


def check_microphone() -> None:
    _header("Microphone")
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        inputs = [d for d in devices if d["max_input_channels"] > 0]
        if inputs:
            default = sd.query_devices(kind="input")
            _ok(f"Default input: {default['name']}")
            _info(f"{len(inputs)} input device(s) found")
        else:
            _warn("No microphone detected — text mode will still work")
    except Exception as exc:
        _warn(f"Could not query audio devices: {exc}")


def check_ollama() -> None:
    _header("Ollama (LLM)")

    # Check if the binary is in PATH
    if shutil.which("ollama") is None:
        _warn(
            "Ollama binary not found in PATH.\n"
            f"{' ' * 7}Install from https://ollama.com — LLM features will be unavailable."
        )
        return
    _ok("Ollama binary found in PATH")

    # Check TCP reachability
    try:
        with socket.create_connection(("localhost", 11434), timeout=3):
            _ok("Ollama server is running (port 11434 reachable)")
    except (OSError, socket.timeout):
        _warn(
            "Ollama server not reachable on localhost:11434.\n"
            f"{' ' * 7}Start it with:  ollama serve"
        )
        return

    # Check model availability
    try:
        import requests  # noqa: PLC0415
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.ok:
            tags = resp.json().get("models", [])
            names = [m.get("name", "") for m in tags]
            target = "qwen2.5:3b-instruct"
            if any(target in n for n in names):
                _ok(f"Model '{target}' is available")
            else:
                _warn(
                    f"Model '{target}' not found.\n"
                    f"{' ' * 7}Pull it with:  ollama pull {target}"
                )
                if names:
                    _info(f"Available models: {', '.join(names)}")
    except Exception as exc:
        _warn(f"Could not check model list: {exc}")


def check_config() -> None:
    _header("Configuration (config.py)")
    try:
        import config  # noqa: PLC0415
        _ok(f"USERNAME      = {config.USERNAME!r}")
        _ok(f"WAKE_WORD     = {config.WAKE_WORD!r}")
        _ok(f"OLLAMA_MODEL  = {config.OLLAMA_MODEL!r}")
        _ok(f"WHISPER_MODEL = {config.WHISPER_MODEL_SIZE!r}")
        _ok(f"DESKTOP_PATH  = {config.DESKTOP_PATH!r}")
        _ok(f"DOWNLOADS_PATH= {config.DOWNLOADS_PATH!r}")
    except Exception as exc:
        _fail(f"Failed to import config.py: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print()
    print("=" * 50)
    print("  Clovis -- Setup Validator")
    print("=" * 50)

    check_python()
    check_packages()
    check_microphone()
    check_ollama()
    check_config()

    print()
    print("=" * 50)
    if _failures:
        print(f"  [FAIL] {len(_failures)} critical issue(s) found:")
        for f in _failures:
            print(f"         - {f}")
        print()
        print("  Fix the issues above before running Clovis.")
        sys.exit(1)
    elif _warnings:
        print(f"  [WARN] {len(_warnings)} warning(s) -- Clovis can still run,")
        print("         but some features may be limited.")
        print()
        print("  Run Clovis:  python main.py --text   (text mode)")
        print("               python main.py           (voice mode)")
    else:
        print("  [OK]  All checks passed -- you're good to go!")
        print()
        print("  Run Clovis:  start_clovis.bat   (voice)")
        print("               start_text.bat      (text mode, no mic)")
    print("=" * 50)
    print()


if __name__ == "__main__":
    main()
