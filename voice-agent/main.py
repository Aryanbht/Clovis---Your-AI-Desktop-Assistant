"""
main.py - Entry point for the Clovis voice assistant.

Run modes
─────────
  Normal (wake-word loop):
      python main.py

  Skip wake word, listen with mic immediately:
      python main.py --no-wake-word

  Pure text input (no mic needed at all):
      python main.py --text

  Hybrid (prompted each turn — choose voice or type):
      python main.py --hybrid

Flow (all modes share the same routing core)
────
  get_input()  →  fast_route()  →  speak/print response
                      │
                      └─(no match)─►  brain.query()  →  dispatch()  →  speak/print
"""

from __future__ import annotations

import argparse
import sys

import brain
import config
import dispatcher
import listener
import router
import tts


# ══════════════════════════════════════════════════════════════════════════════
# Startup
# ══════════════════════════════════════════════════════════════════════════════

def _startup_checks(mode: str) -> None:
    """Print banner, check Ollama availability, and speak the boot message."""
    print("=" * 55)
    print("  🤖  Clovis voice assistant")
    print(f"      Model  : {config.OLLAMA_MODEL}")
    print(f"      Whisper: {config.WHISPER_MODEL_SIZE}")
    print(f"      Wake   : '{config.WAKE_WORD}'")
    print(f"      Mode   : {mode}")
    print("=" * 55)

    if brain.is_ollama_running():
        print("[Main] ✅  Ollama is running — LLM features available.")
    else:
        print(
            "[Main] ⚠️   Ollama not detected. "
            "LLM features will be unavailable.\n"
            "       Start it with: ollama serve"
        )

    print()

    if mode == "text":
        print("[Main] 📝  Text mode — type your commands below.\n")
        tts.speak("Clovis online. Text mode active.")
    elif mode == "hybrid":
        print("[Main] 🔀  Hybrid mode — press Enter to type or say nothing to use voice.\n")
        tts.speak("Clovis online. Hybrid mode active.")
    else:
        print(f"[Main] Say '{config.WAKE_WORD.capitalize()}' to activate.\n")
        tts.speak("Clovis online. Waiting for wake word.")


# ══════════════════════════════════════════════════════════════════════════════
# Input methods
# ══════════════════════════════════════════════════════════════════════════════

def _input_voice() -> str:
    """Record mic and return transcript (may be empty string)."""
    return listener.listen()


def _input_text(prompt: str = "You: ") -> str:
    """Prompt the user to type a command. Returns stripped lowercase string."""
    try:
        text = input(prompt).strip()
        return text
    except EOFError:
        return ""


def _input_hybrid() -> str:
    """
    Ask the user whether to type or speak.
    Pressing Enter (empty input) → use voice.
    Typing anything → use that text directly.
    """
    try:
        typed = input("You (type or press Enter to speak): ").strip()
    except EOFError:
        return ""

    if typed:
        return typed.lower()

    # User pressed Enter → fall back to voice
    print("[Main] 🎙️  Listening…")
    return _input_voice()


# ══════════════════════════════════════════════════════════════════════════════
# Core command handler  (shared by all modes)
# ══════════════════════════════════════════════════════════════════════════════

def _process(transcript: str) -> bool:
    """
    Route *transcript* through fast_route / LLM, execute tool, speak response.

    Returns
    -------
    bool
        ``False`` if a farewell action was detected (signal to exit the loop),
        ``True`` otherwise.
    """
    if not transcript:
        print("[Main] (empty input — nothing to do)")
        return True

    print(f"[Main] 📝 You said: '{transcript}'")

    # ── FAST PATH ──────────────────────────────────────────────────────────────
    fast_result = router.fast_route(transcript)

    if fast_result is not None:
        response = fast_result.get("response", "")
        action   = fast_result.get("action")

        print(f"[Main] ⚡ Fast path  →  action='{action}'")

        _respond(response)

        if action == "farewell":
            return False   # signal caller to stop looping

        return True

    # ── LLM PATH ───────────────────────────────────────────────────────────────
    print("[Main] 🧠 Querying LLM…")

    llm_result = brain.query(transcript)

    if not llm_result:
        _respond("Sorry, I didn't get a response from the language model.")
        return True

    spoken_response = dispatcher.dispatch(llm_result)
    _respond(spoken_response)
    return True


def _respond(text: str) -> None:
    """Print and speak a response."""
    if not text:
        return
    print(f"[Clovis] {text}")
    tts.speak(text)


# ══════════════════════════════════════════════════════════════════════════════
# Run-mode loops
# ══════════════════════════════════════════════════════════════════════════════

def _wake_word_loop() -> None:
    """Wait for wake word → voice command → process → repeat."""
    while True:
        detected = listener.listen_for_wake_word(config.WAKE_WORD)
        if detected:
            print(f"[Main] 🎙️  Wake word detected.")
            tts.speak("Yes?")
            transcript = _input_voice()
            keep_going = _process(transcript)
            if not keep_going:
                break


def _no_wake_word_loop() -> None:
    """Voice command → process → repeat (no wake word needed)."""
    tts.speak("Direct voice mode. Listening now.")
    while True:
        print("\n[Main] 🎙️  Listening for command…")
        transcript = _input_voice()
        keep_going = _process(transcript)
        if not keep_going:
            break


def _text_loop() -> None:
    """Text command → process → repeat."""
    print("[Main] Type your command and press Enter. Type 'bye' to exit.\n")
    while True:
        transcript = _input_text("You: ")
        if not transcript:
            continue
        keep_going = _process(transcript)
        if not keep_going:
            break


def _hybrid_loop() -> None:
    """Each turn: type a command OR press Enter to speak."""
    print("[Main] Press Enter to speak, or type a command directly.\n")
    while True:
        transcript = _input_hybrid()
        if not transcript:
            continue
        keep_going = _process(transcript)
        if not keep_going:
            break


# ══════════════════════════════════════════════════════════════════════════════
# CLI argument parsing
# ══════════════════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="clovis",
        description="Clovis voice assistant",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--no-wake-word",
        action="store_true",
        dest="no_wake_word",
        help="Skip wake-word detection; listen with mic immediately each turn.",
    )
    group.add_argument(
        "--text",
        action="store_true",
        dest="text_mode",
        help="Type commands instead of speaking (no microphone required).",
    )
    group.add_argument(
        "--hybrid",
        action="store_true",
        dest="hybrid_mode",
        help="Each turn: type a command OR press Enter to use the microphone.",
    )

    return parser.parse_args()


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    args = _parse_args()

    # Determine friendly mode name for the banner
    if args.text_mode:
        mode = "text"
    elif args.hybrid_mode:
        mode = "hybrid"
    elif args.no_wake_word:
        mode = "voice (no wake word)"
    else:
        mode = "voice (wake word)"

    _startup_checks(mode)

    try:
        if args.text_mode:
            _text_loop()
        elif args.hybrid_mode:
            _hybrid_loop()
        elif args.no_wake_word:
            _no_wake_word_loop()
        else:
            _wake_word_loop()

    except KeyboardInterrupt:
        print("\n[Main] Shutting down…")
        tts.speak("Shutting down. Goodbye Aryan.")
        sys.exit(0)

    except Exception as exc:
        print(f"[Main] ❌ Unexpected error: {exc}")
        tts.speak("An unexpected error occurred. Restarting.")
        main()


if __name__ == "__main__":
    main()
