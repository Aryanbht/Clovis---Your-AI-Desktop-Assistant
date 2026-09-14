"""
tts.py – Text-to-speech for the voice assistant (Windows).

Engine priority
───────────────
  1. edge-tts  (online, high quality, Indian English neural voices)
  2. pyttsx3   (offline, system TTS — always available as last resort)

The public API is fully synchronous so main.py needs no async boilerplate:

    from tts import speak, set_voice

    speak("Hello, Aryan!")
    set_voice("en-IN-PrabhatNeural")   # switch to male voice at runtime
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile

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
    clean = _sanitise(text)

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
    print(f"[TTS] Voice set to: {_current_voice}")


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
        print("[TTS] edge-tts not installed — falling back to pyttsx3.")
        return False

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="va_tts_")
    os.close(tmp_fd)

    try:
        # Run the async synthesis synchronously
        asyncio.run(_edge_synthesise(text, tmp_path))
        _play_audio(tmp_path)
        return True

    except Exception as exc:
        print(f"[TTS] edge-tts error: {exc} — falling back to pyttsx3.")
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

    communicate = edge_tts.Communicate(text, voice=_current_voice)
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
        print(f"[TTS] playsound error: {exc} — trying subprocess player.")

    # ── Subprocess fallback ────────────────────────────────────────────────────
    _play_via_subprocess(path)


def _play_via_subprocess(path: str) -> None:
    """Use the OS-native command to play *path* synchronously."""
    try:
        if sys.platform == "win32":
            # PowerShell's MediaPlayer blocks until playback finishes
            ps_cmd = (
                f"(New-Object Media.SoundPlayer).Play(); "
                f"Add-Type -AssemblyName presentationCore; "
                f"$player = New-Object System.Windows.Media.MediaPlayer; "
                f"$player.Open([System.Uri]::new('{os.path.abspath(path)}')); "
                f"$player.Play(); Start-Sleep -Seconds 10"
            )
            # Simpler and more reliable: use wmplayer via cmd
            subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    f"$p=New-Object System.Windows.Media.MediaPlayer;"
                    f"$p.Open([uri]'{os.path.abspath(path)}');"
                    f"$p.Play();"
                    f"Start-Sleep 30",
                ],
                capture_output=True,
                timeout=60,
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
        print(f"[TTS] Subprocess audio player error: {exc}")


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

        # Slightly slower rate sounds more natural for an assistant
        engine.setProperty("rate",   160)
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
        print(f"[TTS] pyttsx3 error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# Text sanitisation
# ══════════════════════════════════════════════════════════════════════════════

def _sanitise(text: str) -> str:
    """
    Strip markdown artifacts and control characters that confuse TTS engines.
    Keeps the spoken output natural.
    """
    import re

    # Remove markdown bold/italic markers
    text = re.sub(r"\*{1,3}|_{1,3}", "", text)
    # Remove inline code ticks
    text = re.sub(r"`+", "", text)
    # Collapse multiple spaces / newlines into a single space
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    # Remove leftover bracket pairs (e.g. from [link text])
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    return text.strip()
