"""
chat.py – Simple text-only interface for Clovis. No mic, no TTS required.

Run:
    python chat.py

Type a command and press Enter. Type 'exit' or 'quit' to stop.
"""

from __future__ import annotations

import sys

import brain
import dispatcher
import router


BANNER = """
╔══════════════════════════════════════════╗
║   🤖  Clovis  —  Text Chat Mode       ║
║   Type a command and press Enter.        ║
║   Type  exit  to quit.                   ║
╚══════════════════════════════════════════╝
"""


def process(transcript: str) -> str:
    """Route transcript and return the response string."""
    transcript = transcript.strip().lower()

    if not transcript:
        return ""

    # ── Fast path ──────────────────────────────────────────────────────────────
    fast_result = router.fast_route(transcript)
    if fast_result is not None:
        return fast_result.get("response", "")

    # ── LLM path ───────────────────────────────────────────────────────────────
    if not brain.is_ollama_running():
        return (
            "Ollama is not running, so I can't answer complex queries. "
            "Start it with:  ollama serve\n"
            "For basic commands (open app, time, date, maths) I work fine offline."
        )

    llm_result = brain.query(transcript)
    return dispatcher.dispatch(llm_result, original_text=transcript)


def main() -> None:
    print(BANNER)

    # Quick Ollama status line — non-blocking, just informational
    if brain.is_ollama_running():
        print("  ✅  Ollama detected — full LLM support active.")
    else:
        print("  ⚠️   Ollama not running — fast-path commands only.")
        print("       Start Ollama with:  ollama serve")
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Clovis] Goodbye, Aryan!")
            sys.exit(0)

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "bye", "goodbye"}:
            print("[Clovis] Goodbye, Aryan!")
            sys.exit(0)

        response = process(user_input)

        if response:
            print(f"[Clovis] {response}\n")
        else:
            print("[Clovis] (no response)\n")


if __name__ == "__main__":
    main()
