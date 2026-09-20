"""
chat.py – Conversational text interface for Clovis. Natural chat + task execution.

Run:
    python chat.py

Type naturally — chat, ask questions, give commands. Type 'exit' or 'quit' to stop.
"""

from __future__ import annotations

import sys

import brain
import dispatcher
import router
from config import OLLAMA_MODEL, USERNAME


BANNER = """
============================================================
   Clovis  —  Your Personal Assistant
   Chat naturally, give commands, ask questions.
   Type 'exit' to quit.
============================================================
"""




def process(transcript: str) -> tuple[str, str | None]:
    """
    Route transcript and return (conversational_response, task_response_or_none).
    task_response is the spoken response after task execution, or None if no task.
    """
    transcript = transcript.strip()
    if not transcript:
        return "", None

    fast_result = router.fast_route(transcript.lower())
    if fast_result is not None:
        response = fast_result.get("response", "")
        brain.add_to_history(transcript, response)
        return response, None

    if not brain.is_ollama_running():
        response = (
            "Ollama isn't running, so I can only handle basic commands like "
            "opening apps, checking time/date, or quick math. "
            "Start it with 'ollama serve' for full chat + task support."
        )
        brain.add_to_history(transcript, response)
        return response, None

    llm_result = brain.query(transcript)

    intent = llm_result.get("intent", "unknown")
    llm_response = llm_result.get("response", "")

    if intent in ("unknown", ""):
        return llm_response, None

    task_result = dispatcher.dispatch(llm_result, original_text=transcript)
    return llm_response, task_result


def main() -> None:
    print(BANNER)

    if brain.is_ollama_running():
        print("  [OK]  Ollama detected — full chat + task support active.")
    else:
        print("  [!!]   Ollama not running — basic commands only.")
        print("       Start with:  ollama serve")
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n[Clovis] Goodbye, {USERNAME}!")
            sys.exit(0)

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "bye", "goodbye"}:
            print(f"[Clovis] Goodbye, {USERNAME}!")
            sys.exit(0)

        conversational, task_response = process(user_input)

        if conversational:
            print(f"Clovis: {conversational}")
        if task_response:
            print(f"[Task done] {task_response}")
        print()


if __name__ == "__main__":
    main()
