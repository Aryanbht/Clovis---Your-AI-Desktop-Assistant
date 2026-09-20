"""
tts.py – Text-to-speech for the voice assistant (Windows).

Engine priority
───────────────
  1. edge-tts  (online, high quality, Indian English neural voices)
  2. pyttsx3   (offline, system TTS — always available as last resort)

The public API is fully synchronous so main.py needs no async boilerplate:

    from tts import speak, set_voice

    speak("Hello, Shivansh!")
    set_voice("en-IN-PrabhatNeural")   # switch to male voice at runtime
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import ui
from config import TTS_FALLBACK_RATE, TTS_RATE

# ── Default voice configuration ────────────────────────────────────────────────

VOICE_FEMALE = "en-IN-NeerjaNeural"   # Indian English, female (default)
VOICE_MALE   = "en-IN-PrabhatNeural"  # Indian English, male

# Module-level mutable state — changed by set_voice()
_current_voice: str = VOICE_FEMALE


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def speak(text: str) -> None:
    """
    Speak *text* aloud using edge-tts (primary) or pyttsx3 (fallback).

    This function is synchronous — it blocks until speech finishes.
    All errors are caught internally; the function never raises.

    Parameters
    ----------
    text : str
        The text to be spoken.  Empty or whitespace-only strings are ignored.
    """
    if not text or not text.strip():
        return

    # Sanitise: edge-tts can choke on some unicode / markdown remnants
    clean = clean_for_tts(text)

    success = _speak_edge(clean)
    if not success:
        _speak_pyttsx3(clean)


def set_voice(voice_name: str) -> None:
    """
    Switch the edge-tts voice used by subsequent :func:`speak` calls.

    Parameters
    ----------
    voice_name : str
        A valid edge-tts voice name, e.g. ``'en-IN-NeerjaNeural'`` or
        ``'en-IN-PrabhatNeural'``.

    Common Indian English voices
    ----------------------------
    - ``en-IN-NeerjaNeural``  (female, default)
    - ``en-IN-PrabhatNeural`` (male)

    Call ``edge-tts --list-voices`` in a terminal to discover all voices.
    """
    global _current_voice
    _current_voice = voice_name.strip()
    ui.console.print(f"[dim cyan][TTS] Voice set to: {_current_voice}[/dim cyan]")


# ══════════════════════════════════════════════════════════════════════════════
# edge-tts engine  (primary)
# ══════════════════════════════════════════════════════════════════════════════

def _speak_edge(text: str) -> bool:
    """
    Synthesise *text* with edge-tts, save to a temp MP3, play it, then delete.

    Returns ``True`` on success, ``False`` on any failure.
    """
    try:
        import edge_tts  # type: ignore  # optional dependency
    except ImportError:
        ui.console.print("[dim yellow][TTS] edge-tts not installed — falling back to pyttsx3.[/dim yellow]")
        return False

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="va_tts_")
    os.close(tmp_fd)

    try:
        # Run the async synthesis synchronously
        asyncio.run(_edge_synthesise(text, tmp_path))
        _play_audio(tmp_path)
        return True

    except Exception as exc:
        ui.console.print(f"[dim yellow][TTS] edge-tts error: {exc} — falling back to pyttsx3.[/dim yellow]")
        return False

    finally:
        # Always clean up the temp file
        try:
            os.remove(tmp_path)
        except OSError:
            pass


async def _edge_synthesise(text: str, output_path: str) -> None:
    """Async helper: synthesise *text* and write MP3 bytes to *output_path*."""
    import edge_tts  # type: ignore

    communicate = edge_tts.Communicate(text, voice=_current_voice, rate=TTS_RATE)
    await communicate.save(output_path)


# ══════════════════════════════════════════════════════════════════════════════
# Audio playback
# ══════════════════════════════════════════════════════════════════════════════

def _play_audio(path: str) -> None:
    """
    Play an audio file at *path* synchronously.

    Strategy (in order):
      1. playsound  – cross-platform, blocks until done
      2. subprocess – platform-native player as fallback
    """
    # ── Try playsound first ────────────────────────────────────────────────────
    try:
        from playsound import playsound  # type: ignore  # optional dependency
        playsound(path)
        return
    except ImportError:
        pass  # playsound not installed — try subprocess
    except Exception as exc:
        ui.console.print(f"[dim yellow][TTS] playsound error: {exc} — trying subprocess player.[/dim yellow]")

    # ── Subprocess fallback ────────────────────────────────────────────────────
    _play_via_subprocess(path)


def _play_via_subprocess(path: str) -> None:
    """Use the OS-native command to play *path* synchronously."""
    try:
        if sys.platform == "win32":
            # Use Windows Media Player COM object which blocks until playback finishes.
            # WaitForCompletion(1) waits for the media to finish playing.
            subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    f"$p = New-Object -ComObject WScript.Shell; "
                    f"Add-Type -AssemblyName presentationCore; "
                    f"$player = New-Object System.Windows.Media.MediaPlayer; "
                    f"$player.Open([uri]'{os.path.abspath(path)}'); "
                    f"$player.PlaySync();",
                ],
                capture_output=True,
                timeout=30,
            )
        elif sys.platform == "darwin":
            subprocess.run(["afplay", path], check=True)
        else:
            # Linux: try common players in order
            for player in ("mpg123", "mpv", "ffplay", "aplay"):
                try:
                    subprocess.run([player, path], check=True, capture_output=True)
                    break
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
    except Exception as exc:
        ui.console.print(f"[dim red][TTS] Subprocess audio player error: {exc}[/dim red]")


# ══════════════════════════════════════════════════════════════════════════════
# pyttsx3 engine  (offline fallback)
# ══════════════════════════════════════════════════════════════════════════════

def _speak_pyttsx3(text: str) -> None:
    """
    Synthesise and play *text* with pyttsx3 (fully offline, blocking).
    Errors are caught and printed silently.
    """
    try:
        import pyttsx3  # type: ignore

        engine = pyttsx3.init()

        engine.setProperty("rate", TTS_FALLBACK_RATE)
        engine.setProperty("volume", 1.0)

        # Prefer a female voice on Windows SAPI if available
        voices = engine.getProperty("voices")
        if voices:
            female = next((v for v in voices if "zira" in v.name.lower()), None)
            if female:
                engine.setProperty("voice", female.id)

        engine.say(text)
        engine.runAndWait()
        engine.stop()

    except Exception as exc:
        ui.console.print(f"[dim red][TTS] pyttsx3 error: {exc}[/dim red]")


# ══════════════════════════════════════════════════════════════════════════════
# Text sanitisation
# ══════════════════════════════════════════════════════════════════════════════

def clean_for_tts(text: str) -> str:
    """
    Clean text for TTS by removing emojis, markdown, paths, URLs, and formatting tags.
    """
    import re

    # 1. Remove all emojis and non-ASCII symbols (except Hindi \u0900-\u097F)
    # ASCII is \x00-\x7F. We want to keep letters, numbers, punctuation.
    # Keep ASCII and Hindi range, remove everything else (like emojis).
    text = re.sub(r'[^\x00-\x7F\u0900-\u097F]+', ' ', text)

    # 2. Remove markdown bold/italic
    text = re.sub(r"\*{1,2}|_{1,2}", "", text)
    text = re.sub(r"`+", "", text)

    # 3. Replace dashes used as separators ( - – — ) with a comma and space
    text = re.sub(r"\s+[-–—]+\s+", ", ", text)

    # 4. Remove patterns like "path:" "result:" "status:" (case-insensitive)
    text = re.sub(r"\b(path|result|status|file|url|error):\s*", "", text, flags=re.IGNORECASE)

    # 5. Remove all URLs
    text = re.sub(r"https?://\S+", "", text)

    # 6. Remove all Windows file paths (C:\, D:\, C:/, D:/, etc.)
    text = re.sub(r"\b[A-Za-z]:[\\/]\S*", "", text)

    # 7. Remove square bracket tags like [FAST PATH], [LLM PATH], [ERROR]
    text = re.sub(r"\[.*?\]", "", text)

    # 8. Remove parentheses and their content if they contain technical info like paths or True/False
    # We will remove any (...) that contains a slash, backslash, or boolean
    text = re.sub(r"\([^)]*?[\\/][^)]*?\)", "", text)
    text = re.sub(r"\((True|False)\)", "", text, flags=re.IGNORECASE)

    # 9. Collapse multiple spaces and newlines into a single space
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)

    # 10. Strip leading and trailing whitespace
    return text.strip()
