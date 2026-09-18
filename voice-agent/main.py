"""
main.py - Entry point for the Clovis voice assistant.

Run modes
---------
  Normal (wake-word loop):
      python main.py

  Skip wake word, listen with mic immediately:
      python main.py --no-wake-word

  Pure text input (no mic needed at all):
      python main.py --text

  Hybrid (prompted each turn -- choose voice or type):
      python main.py --hybrid

Flow (all modes share the same routing core)
----
  get_input()  ->  fast_route()  ->  speak/print response
                       |
                       +-(no match)->  brain.query()  ->  dispatch()  ->  speak/print
"""

from __future__ import annotations

import argparse
import sys
import time

import brain
import config
import dispatcher
import listener
import router
import tts


# ==============================================================================
# Startup
# ==============================================================================

def _startup_checks(mode: str) -> None:
    """Print banner, check Ollama availability, and speak the boot message."""
    print("=" * 55)
    print("  Clovis voice assistant")
    print(f"      Model  : {config.OLLAMA_MODEL}")
    print(f"      Whisper: {config.WHISPER_MODEL_SIZE}")
    print(f"      Wake   : '{config.WAKE_WORD}'")
    print(f"      Mode   : {mode}")
    print("=" * 55)

    if brain.is_ollama_running():
        print("[Main] Ollama is running -- LLM features available.")
    else:
        print(
            "[Main] Ollama not detected. "
            "LLM features will be unavailable.\n"
            "       Start it with: ollama serve"
        )

    print()

    if mode == "text":
        print("[Main] Text mode -- type your commands below.\n")
        tts.speak("Clovis online. Text mode active.")
    elif mode == "hybrid":
        print("[Main] Hybrid mode -- press Enter to type or say nothing to use voice.\n")
        tts.speak("Clovis online. Hybrid mode active.")
        # Pre-load Whisper so it's ready when the user presses Enter
        listener.preload_model()
    else:
        print(f"[Main] Say '{config.WAKE_WORD.capitalize()}' to activate.\n")
        # Pre-load Whisper NOW so model-load messages appear before the mic bar
        listener.preload_model()
        tts.speak("Clovis online. Waiting for wake word.")



# ==============================================================================
# Input methods
# ==============================================================================

def _input_voice() -> str:
    """Record mic and return transcript (may be empty string)."""
    return listener.listen()


def _input_text(prompt: str = "You: ") -> str:
    """Prompt the user to type a command. Returns stripped string."""
    try:
        text = input(prompt).strip()
        return text
    except EOFError:
        return ""


def _input_hybrid() -> str:
    """
    Ask the user whether to type or speak.
    Pressing Enter (empty input) -> use voice.
    Typing anything -> use that text directly.
    """
    try:
        typed = input("You (type or press Enter to speak): ").strip()
    except EOFError:
        return ""

    if typed:
        return typed.lower()

    # User pressed Enter -> fall back to voice
    print("[Main] Listening...")
    return _input_voice()


# ==============================================================================
# Core command handler  (shared by all modes)
# ==============================================================================

def _process(transcript: str) -> bool:
    """
    Route *transcript* through fast_route / LLM, execute tool, speak response.

    Returns
    -------
    bool
        False if a farewell action was detected (signal to exit the loop),
        True otherwise.
    """
    if not transcript:
        print("[Main] (empty input -- nothing to do)")
        return True

    print(f"[Main] You said: '{transcript}'")
    
    import random
    import threading

    # -- FAST PATH -------------------------------------------------------------
    fast_result = router.fast_route(transcript)

    if fast_result is not None:
        tts.speak(random.choice(["On it.", "Sure."]))
        
        response = fast_result.get("response", "")
        action   = fast_result.get("action")

        print(f"[FAST PATH] -> {action}")

        _respond(response)

        if action == "farewell":
            return False   # signal caller to stop looping

        return True

    # -- LLM PATH --------------------------------------------------------------
    tts.speak(random.choice(["Let me check.", "One moment."]))
    print("[LLM PATH] -> sending to Ollama...")

    llm_done = threading.Event()
    def _timeout_speaker():
        if not llm_done.wait(4.0):
            tts.speak("Still working on it...")
            
    t = threading.Thread(target=_timeout_speaker)
    t.daemon = True
    t.start()

    llm_result = brain.query(transcript)
    llm_done.set()

    if not llm_result:
        _respond("Sorry, I didn't get a response from the language model.")
        return True

    spoken_response = dispatcher.dispatch(llm_result, original_text=transcript)
    _respond(spoken_response)
    return True


def _respond(text: str) -> None:
    """Print and speak a response."""
    if not text:
        return
    print(f"[Clovis] {text}")
    tts.speak(text)


# ==============================================================================
# Run-mode loops
# ==============================================================================

def _wake_word_loop() -> None:
    """
    Outer loop : sleep until wake word is heard.
    Inner loop : stay active, processing commands one after another.
                 Go back to sleep after SLEEP_TIMEOUT seconds of no speech.
    """
    SLEEP_TIMEOUT = 5 * 60   # seconds of inactivity before going back to sleep

    cycle = 0

    while True:
        # ── SLEEP PHASE: wait for wake word ───────────────────────────────────
        print(f"\n[Main] Sleeping. Say '{config.WAKE_WORD}' to activate.\n")
        while True:
            detected = listener.listen_for_wake_word(config.WAKE_WORD, cycle=cycle)
            cycle += 1
            if detected:
                break

        # ── ACTIVE PHASE: keep listening until 5 min of inactivity ───────────
        print("\n[Main] Active! Listening for your command.")
        print(f"[Main] (I'll go back to sleep after {SLEEP_TIMEOUT // 60} min of silence.)\n")
        tts.speak("Yes?")

        last_activity = time.time()

        while True:
            transcript = _input_voice()

            if not transcript:
                elapsed  = time.time() - last_activity
                remaining = SLEEP_TIMEOUT - elapsed

                if elapsed >= SLEEP_TIMEOUT:
                    print("\n[Main] No activity for 5 minutes. Going to sleep...")
                    tts.speak("Going to sleep. Say " + config.WAKE_WORD + " to wake me up.")
                    break   # back to sleep phase

                mins = int(remaining // 60)
                secs = int(remaining % 60)
                print(f"[Main] Still listening... ({mins}m {secs}s until sleep)")
                continue

            # Got a real command -- reset the inactivity timer
            last_activity = time.time()
            keep_going = _process(transcript)

            if not keep_going:
                return   # farewell command -- exit completely

            # After responding, immediately listen for the next command
            print("[Main] Ready for next command (or stay quiet for 5 min to sleep).")



def _no_wake_word_loop() -> None:
    """Voice command -> process -> repeat (no wake word needed)."""
    tts.speak("Direct voice mode. Listening now.")
    while True:
        print("\n[Main] Listening for command...")
        transcript = _input_voice()
        keep_going = _process(transcript)
        if not keep_going:
            break


def _text_loop() -> None:
    """Text command -> process -> repeat."""
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


# ==============================================================================
# CLI argument parsing
# ==============================================================================

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


# ==============================================================================
# Main entry point
# ==============================================================================

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
        print("\n[Main] Shutting down...")
        tts.speak(f"Shutting down. Goodbye {config.USERNAME}.")
        sys.exit(0)

    except Exception as exc:
        print(f"[Main] Unexpected error: {exc}")
        tts.speak("An unexpected error occurred. Restarting.")
        main()


if __name__ == "__main__":
    main()
