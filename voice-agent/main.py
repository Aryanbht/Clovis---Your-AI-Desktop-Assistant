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
import os
import sys
from pathlib import Path
import time

import brain
import config
import dispatcher
import listener
import router
import tts
import ui


# ==============================================================================
# Startup
# ==============================================================================

def _startup_checks(mode: str) -> None:
    """Print banner, check Ollama availability, and speak the boot message."""
    is_running = brain.is_ollama_running()
    ui.show_status_panel(config.OLLAMA_MODEL, config.WHISPER_MODEL_SIZE, config.WAKE_WORD, mode, is_running)
    ui.show_ollama_status(is_running)

    if mode == "text":
        ui.console.print("[dim cyan]Text mode -- type your commands below.[/dim cyan]\n")
        tts.speak("Clovis online. Text mode active.")
    elif mode == "hybrid":
        ui.console.print("[dim cyan]Hybrid mode -- press Enter to type or say nothing to use voice.[/dim cyan]\n")
        tts.speak("Clovis online. Hybrid mode active.")
        # Pre-load Whisper so it's ready when the user presses Enter
        listener.preload_model()
    else:
        ui.console.print(f"[dim cyan]Say '{config.WAKE_WORD.capitalize()}' to activate.[/dim cyan]\n")
        # Pre-load Whisper NOW so model-load messages appear before the mic bar
        listener.preload_model()
        tts.speak("Clovis online. Waiting for wake word.")



# ==============================================================================
# Input methods
# ==============================================================================

def _input_voice() -> str:
    """Record mic and return transcript (may be empty string)."""
    ui.show_listening()
    transcript = listener.listen()
    ui.stop_listening()
    return transcript


def _input_text(prompt: str = "You: ") -> str:
    """Prompt the user to type a command. Returns stripped string."""
    try:
        text = ui.console.input(f"[bright_cyan]{prompt}[/bright_cyan]").strip()
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
        typed = ui.console.input("[bright_cyan]You (type or press Enter to speak): [/bright_cyan]").strip()
    except EOFError:
        return ""

    if typed:
        return typed.lower()

    # User pressed Enter -> fall back to voice
    return _input_voice()


# ==============================================================================
# Core command handler  (shared by all modes)
# ==============================================================================

_last_command_time = time.time()

def _process(transcript: str) -> bool:
    """
    Route *transcript* through fast_route / LLM, execute tool, speak response.

    Returns
    -------
    bool
        False if a farewell action was detected (signal to exit the loop),
        True otherwise.
    """
    global _last_command_time
    
    current_time = time.time()
    if current_time - _last_command_time > 300:  # 5 minutes
        ui.console.print("[dim yellow]5 minutes of inactivity. Clearing session memory.[/dim yellow]")
        brain.clear_memory()
    _last_command_time = current_time

    if not transcript:
        return True

    ui.console.print(f"[dim cyan]You said:[/dim cyan] [white]'{transcript}'[/white]")
    
    import random
    import threading

    # -- FAST PATH -------------------------------------------------------------
    fast_result = router.fast_route(transcript)

    if fast_result is not None:
        tts.speak(random.choice(["On it.", "Sure."]))
        
        response = fast_result.get("response", "")
        action   = fast_result.get("action")

        ui.log_intent("FAST", str(action), {"input": transcript})

        _respond(response)

        if action == "farewell":
            return False   # signal caller to stop looping

        return True

    # -- LLM PATH --------------------------------------------------------------
    tts.speak(random.choice(["Let me check.", "One moment."]))

    llm_done = threading.Event()
    def _timeout_speaker():
        if not llm_done.wait(4.0):
            tts.speak("Still working on it...")
            
    t = threading.Thread(target=_timeout_speaker)
    t.daemon = True
    t.start()

    ui.show_thinking()
    llm_result = brain.query(transcript)
    ui.stop_thinking()
    
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
    ui.show_response(text)
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
        ui.console.print(f"\n[dim cyan]Sleeping. Say '{config.WAKE_WORD}' to activate.[/dim cyan]\n")
        while True:
            detected = listener.listen_for_wake_word(config.WAKE_WORD, cycle=cycle)
            cycle += 1
            if detected:
                break

        # ── ACTIVE PHASE: keep listening until 5 min of inactivity ───────────
        ui.console.print("\n[bright_green]Active! Listening for your command.[/bright_green]")
        ui.console.print(f"[dim](I'll go back to sleep after {SLEEP_TIMEOUT // 60} min of silence.)[/dim]\n")
        tts.speak("Yes?")

        last_activity = time.time()

        while True:
            transcript = _input_voice()

            if not transcript:
                elapsed  = time.time() - last_activity
                remaining = SLEEP_TIMEOUT - elapsed

                if elapsed >= SLEEP_TIMEOUT:
                    ui.console.print("\n[dim yellow]No activity for 5 minutes. Going to sleep...[/dim yellow]")
                    tts.speak("Going to sleep. Say " + config.WAKE_WORD + " to wake me up.")
                    break   # back to sleep phase

                mins = int(remaining // 60)
                secs = int(remaining % 60)
                ui.console.print(f"[dim]Still listening... ({mins}m {secs}s until sleep)[/dim]", end="\r")
                continue

            # Got a real command -- reset the inactivity timer
            last_activity = time.time()
            keep_going = _process(transcript)

            if not keep_going:
                return   # farewell command -- exit completely

            # After responding, immediately listen for the next command
            ui.console.print("\n[dim cyan]Ready for next command (or stay quiet for 5 min to sleep).[/dim cyan]")



def _no_wake_word_loop() -> None:
    """Voice command -> process -> repeat (no wake word needed)."""
    tts.speak("Direct voice mode. Listening now.")
    while True:
        ui.console.print("\n[dim cyan]Listening for command...[/dim cyan]")
        transcript = _input_voice()
        keep_going = _process(transcript)
        if not keep_going:
            break


def _text_loop() -> None:
    """Text command -> process -> repeat."""
    ui.console.print("[dim cyan]Type your command and press Enter. Type 'bye' to exit.[/dim cyan]\n")
    while True:
        transcript = _input_text("You: ")
        if not transcript:
            continue
        keep_going = _process(transcript)
        if not keep_going:
            break


def _hybrid_loop() -> None:
    """Each turn: type a command OR press Enter to speak."""
    ui.console.print("[dim cyan]Press Enter to speak, or type a command directly.[/dim cyan]\n")
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
    
    lock_file = Path(config.BASE_DIR) / "clovis.lock"
    with open(lock_file, "w") as f:
        f.write(str(os.getpid()))

    # Show menu if no arguments were provided at all
    if not any([args.text_mode, args.hybrid_mode, args.no_wake_word]) and len(sys.argv) == 1:
        ui.show_banner()
        choice = ui.show_menu()
        if choice == "1":
            args.text_mode = True
        elif choice == "2":
            pass # default wake word mode
        elif choice == "3":
            args.no_wake_word = True
        elif choice == "4":
            args.hybrid_mode = True
        else:
            ui.show_farewell()
            sys.exit(0)

    if args.text_mode:
        mode = "text"
    elif args.hybrid_mode:
        mode = "hybrid"
    elif args.no_wake_word:
        mode = "voice (no wake word)"
    else:
        mode = "voice (wake word)"

    # If args were passed, banner was not shown yet
    if len(sys.argv) > 1:
        ui.show_banner()

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
        ui.console.print("\n[dim yellow]Shutting down...[/dim yellow]")
        tts.speak(f"Shutting down. Goodbye {config.USERNAME}.")
        ui.show_farewell()
        if lock_file.exists():
            lock_file.unlink()
        sys.exit(0)

    except Exception as exc:
        ui.show_error(f"Unexpected error: {exc}")
        tts.speak("An unexpected error occurred. Restarting.")
        if lock_file.exists():
            lock_file.unlink()
        main()


if __name__ == "__main__":
    main()
