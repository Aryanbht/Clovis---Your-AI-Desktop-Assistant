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

# Suppress noisy HuggingFace / symlink warnings before importing HF libs
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np
import sounddevice as sd
from config import WHISPER_BEAM_SIZE, WHISPER_INITIAL_PROMPT, WHISPER_MODEL_SIZE


# ── Audio constants ────────────────────────────────────────────────────────────

SAMPLE_RATE     = 16_000   # Hz — Whisper expects 16 kHz mono
CHANNELS        = 1
DTYPE           = "int16"  # 16-bit PCM; matches scipy WAV output

CHUNK_DURATION  = 0.3      # seconds per recording chunk
CHUNK_SAMPLES   = int(SAMPLE_RATE * CHUNK_DURATION)

SILENCE_THRESH      = 120    # Low enough for quieter / accented speech; adapted to room noise below.
WAKE_SILENCE_THRESH = 80     # lower bar for wake-word clips (mic gain varies)
SILENCE_TIMEOUT     = 1.5   # seconds of continuous silence → stop recording
MAX_RECORD_SEC      = 15.0  # hard ceiling to prevent runaway recording

WAKE_CLIP_SEC   = 2.0      # duration of the short clip for wake-word detection


# ── Whisper model (loaded once, module-level) ──────────────────────────────────

def _load_model() -> "WhisperModel":
    from faster_whisper import WhisperModel
    model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return model


_model: Optional[WhisperModel] = None


def _get_model() -> WhisperModel:
    """Lazy-load the Whisper model on first use."""
    global _model
    if _model is None:
        _model = _load_model()
    return _model


def preload_model() -> None:
    """Explicitly load the Whisper model now (call at startup for clean output)."""
    _get_model()


# ══════════════════════════════════════════════════════════════════════════════
# Core helpers
# ══════════════════════════════════════════════════════════════════════════════

def _rms(chunk: np.ndarray) -> float:
    """Return the Root Mean Square amplitude of *chunk*."""
    return float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))


def _save_wav(audio: np.ndarray, path: str) -> None:
    """Write *audio* (int16, mono) to a WAV file at *path*."""
    from scipy.io.wavfile import write as wav_write
    wav_write(path, SAMPLE_RATE, audio)


def _denoise_and_normalise(audio: np.ndarray) -> np.ndarray:
    """Suppress low-frequency room noise and normalise a recorded utterance.

    This is deliberately lightweight: it runs once per utterance and adds no
    model dependency or startup cost. Whisper's own VAD handles residual noise.
    """
    if audio.size < 32:
        return audio

    samples = audio.astype(np.float32) / np.iinfo(np.int16).max
    try:
        from scipy.signal import butter, sosfiltfilt
        high_pass = butter(4, 80, btype="highpass", fs=SAMPLE_RATE, output="sos")
        samples = sosfiltfilt(high_pass, samples)
    except ValueError:
        pass

    peak = float(np.max(np.abs(samples)))
    if peak > 0.01:
        samples *= min(0.92 / peak, 4.0)
    return np.clip(samples * np.iinfo(np.int16).max, -32768, 32767).astype(np.int16)


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
        beam_size=WHISPER_BEAM_SIZE,
        best_of=5,
        temperature=0.0,
        condition_on_previous_text=False,
        initial_prompt=WHISPER_INITIAL_PROMPT,
        vad_filter=True,           # built-in VAD skips non-speech regions
        vad_parameters={
            "min_silence_duration_ms": 300,
        },
    )
    text = " ".join(seg.text for seg in segments).strip().lower()
    # Normalise whitespace and common transcription punctuation before routing.
    return " ".join(text.replace("’", "'").split())


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def listen() -> str:
    """
    Record from the default microphone and return a transcript.

    Two-phase recording:
      Phase 1 -- Waiting for speech to BEGIN (up to PRE_SPEECH_TIMEOUT seconds).
                 Silence countdown does NOT run yet; we are just waiting for the
                 user to start talking.
      Phase 2 -- Speech has started.  Now count silence; stop after
                 SILENCE_TIMEOUT seconds of continuous quiet.

    Returns
    -------
    str
        Lowercased, stripped transcript.  Empty string if nothing was heard
        or an error occurred.
    """
    PRE_SPEECH_TIMEOUT = 6.0   # seconds to wait for speech to START

    chunks: list[np.ndarray] = []
    silent_duration  = 0.0
    total_duration   = 0.0
    speech_started   = False   # True once the user has begun speaking
    noise_samples: list[float] = []

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
        ) as stream:
            while total_duration < MAX_RECORD_SEC:
                chunk, overflowed = stream.read(CHUNK_SAMPLES)

                if overflowed:
                    pass  # suppress overflow warning

                chunk = chunk.flatten()
                chunks.append(chunk)
                total_duration += CHUNK_DURATION

                rms = _rms(chunk)
                if not speech_started and len(noise_samples) < 3:
                    noise_samples.append(rms)
                room_noise = sum(noise_samples) / len(noise_samples) if noise_samples else 0.0
                dynamic_threshold = max(SILENCE_THRESH, min(350.0, room_noise * 2.2))
                chunk_loud = rms >= dynamic_threshold

                if not speech_started:
                    if chunk_loud:
                        # User has started speaking -- switch to phase 2
                        speech_started = True
                        silent_duration = 0.0
                    else:
                        # Still waiting for speech; bail if pre-speech window expires
                        if total_duration >= PRE_SPEECH_TIMEOUT:
                            return ""
                else:
                    # Phase 2: track silence after speech has begun
                    if not chunk_loud:
                        silent_duration += CHUNK_DURATION
                        if silent_duration >= SILENCE_TIMEOUT:
                            break   # enough silence -- done recording
                    else:
                        silent_duration = 0.0  # reset on renewed speech

    except sd.PortAudioError as exc:
        return ""
    except Exception as exc:
        return ""

    if not chunks or not speech_started:
        return ""

    audio = _denoise_and_normalise(np.concatenate(chunks))

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

    return transcript


def listen_for_wake_word(wake_word: str, cycle: int = 0) -> bool:
    """
    Record a short fixed-length clip (WAKE_CLIP_SEC seconds) and return
    ``True`` if *wake_word* appears anywhere in the transcript.

    Designed to be called in a tight loop so the assistant can idle cheaply
    while waiting for activation.

    Parameters
    ----------
    wake_word : str
        The trigger word/phrase to listen for (case-insensitive).
    cycle : int
        Loop counter passed by the caller; used to print a status line
        every few cycles so the user knows the assistant is listening.

    Returns
    -------
    bool
        ``True`` if the wake word was detected, ``False`` otherwise.
    """
    n_samples = int(SAMPLE_RATE * WAKE_CLIP_SEC)

    # Show a live indicator every 3 cycles (~6 seconds) so the user knows
    # the assistant is actively listening.
    # suppressed to prevent breaking rich Live layout

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
        time.sleep(1.0)  # back-off before next attempt
        return False
    except Exception as exc:
        return False

    rms = _rms(audio)

    # Skip transcription if the clip is too quiet
    if rms < WAKE_SILENCE_THRESH:
        return False

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="va_wake_")
    os.close(tmp_fd)
    try:
        _save_wav(_denoise_and_normalise(audio), tmp_path)
        transcript = _transcribe_file(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    detected = wake_word.lower().strip() in transcript
    return detected
