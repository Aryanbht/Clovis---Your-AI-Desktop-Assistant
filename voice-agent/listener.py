"""
listener.py – Microphone capture, VAD-based silence detection,
              Whisper transcription, and wake-word detection.

Windows-focused; uses sounddevice + faster-whisper + scipy.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Optional

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as wav_write
from faster_whisper import WhisperModel

from config import WHISPER_MODEL_SIZE


# ── Audio constants ────────────────────────────────────────────────────────────

SAMPLE_RATE     = 16_000   # Hz — Whisper expects 16 kHz mono
CHANNELS        = 1
DTYPE           = "int16"  # 16-bit PCM; matches scipy WAV output

CHUNK_DURATION  = 0.3      # seconds per recording chunk
CHUNK_SAMPLES   = int(SAMPLE_RATE * CHUNK_DURATION)

SILENCE_THRESH  = 500      # RMS below this → silence
SILENCE_TIMEOUT = 1.5      # seconds of continuous silence → stop recording
MAX_RECORD_SEC  = 15.0     # hard ceiling to prevent runaway recording

WAKE_CLIP_SEC   = 2.0      # duration of the short clip for wake-word detection


# ── Whisper model (loaded once, module-level) ──────────────────────────────────

def _load_model() -> WhisperModel:
    print(f"[Listener] Loading Whisper '{WHISPER_MODEL_SIZE}' model…")
    model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    print("[Listener] Whisper model ready.")
    return model


_model: Optional[WhisperModel] = None


def _get_model() -> WhisperModel:
    """Lazy-load the Whisper model on first use."""
    global _model
    if _model is None:
        _model = _load_model()
    return _model


# ══════════════════════════════════════════════════════════════════════════════
# Core helpers
# ══════════════════════════════════════════════════════════════════════════════

def _rms(chunk: np.ndarray) -> float:
    """Return the Root Mean Square amplitude of *chunk*."""
    return float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))


def _save_wav(audio: np.ndarray, path: str) -> None:
    """Write *audio* (int16, mono) to a WAV file at *path*."""
    wav_write(path, SAMPLE_RATE, audio)


def _transcribe_file(wav_path: str) -> str:
    """
    Transcribe a WAV file with faster-whisper.

    Returns the transcript as a lowercased, stripped string.
    Returns an empty string if no speech is detected.
    """
    model = _get_model()
    segments, info = model.transcribe(
        wav_path,
        language="en",
        beam_size=5,
        vad_filter=True,           # built-in VAD skips non-speech regions
        vad_parameters={
            "min_silence_duration_ms": 300,
        },
    )
    text = " ".join(seg.text for seg in segments).strip().lower()
    return text


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def listen() -> str:
    """
    Record from the default microphone until 1.5 s of silence is detected
    (or MAX_RECORD_SEC is reached), then transcribe and return the text.

    Returns
    -------
    str
        Lowercased, stripped transcript.  Empty string if nothing was heard
        or an error occurred.
    """
    print("[Listener] Listening… (speak now)")

    chunks: list[np.ndarray] = []
    silent_duration = 0.0
    total_duration  = 0.0

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
        ) as stream:
            while total_duration < MAX_RECORD_SEC:
                chunk, overflowed = stream.read(CHUNK_SAMPLES)

                if overflowed:
                    print("[Listener] Warning: input overflow detected.")

                chunk = chunk.flatten()
                chunks.append(chunk)
                total_duration += CHUNK_DURATION

                if _rms(chunk) < SILENCE_THRESH:
                    silent_duration += CHUNK_DURATION
                    if silent_duration >= SILENCE_TIMEOUT:
                        break
                else:
                    silent_duration = 0.0  # reset on speech detection

    except sd.PortAudioError as exc:
        print(f"[Listener] ❌ Microphone error: {exc}")
        print("[Listener]    → Check that a microphone is connected and not in use by another app.")
        return ""
    except Exception as exc:
        print(f"[Listener] ❌ Unexpected audio error: {exc}")
        return ""

    if not chunks:
        return ""

    audio = np.concatenate(chunks)

    # Bail out early if the whole recording was silence
    if _rms(audio) < SILENCE_THRESH:
        return ""

    # Write to a temp WAV, transcribe, then clean up
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="va_listen_")
    os.close(tmp_fd)
    try:
        _save_wav(audio, tmp_path)
        transcript = _transcribe_file(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if transcript:
        print(f"[Listener] Heard: '{transcript}'")
    return transcript


def listen_for_wake_word(wake_word: str) -> bool:
    """
    Record a short fixed-length clip (WAKE_CLIP_SEC seconds) and return
    ``True`` if *wake_word* appears anywhere in the transcript.

    Designed to be called in a tight loop so the assistant can idle cheaply
    while waiting for activation.

    Parameters
    ----------
    wake_word : str
        The trigger word/phrase to listen for (case-insensitive).

    Returns
    -------
    bool
        ``True`` if the wake word was detected, ``False`` otherwise.
    """
    n_samples = int(SAMPLE_RATE * WAKE_CLIP_SEC)

    try:
        audio = sd.rec(
            n_samples,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
        )
        sd.wait()
        audio = audio.flatten()

    except sd.PortAudioError as exc:
        print(f"[Listener] ❌ Microphone error during wake-word detection: {exc}")
        print("[Listener]    → Ensure a microphone is available and not blocked.")
        time.sleep(1.0)  # back-off before next attempt
        return False
    except Exception as exc:
        print(f"[Listener] ❌ Unexpected error during wake-word detection: {exc}")
        return False

    # Skip transcription if the clip is too quiet (saves CPU)
    if _rms(audio) < SILENCE_THRESH:
        return False

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="va_wake_")
    os.close(tmp_fd)
    try:
        _save_wav(audio, tmp_path)
        transcript = _transcribe_file(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    detected = wake_word.lower().strip() in transcript
    if detected:
        print(f"[Listener] 🎙️  Wake word '{wake_word}' detected!")
    return detected
