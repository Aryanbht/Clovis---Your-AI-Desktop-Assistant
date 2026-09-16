"""
chat.py – Conversational text interface for Clovis. Natural chat + task execution.

Run:
    python chat.py

Type naturally — chat, ask questions, give commands. Type 'exit' or 'quit' to stop.
"""

from __future__ import annotations

import json
import re
import sys

import brain
import dispatcher
import router
from config import OLLAMA_MODEL, OLLAMA_URL


BANNER = """
============================================================
   Clovis  —  Your Personal Assistant
   Chat naturally, give commands, ask questions.
   Type 'exit' to quit.
============================================================
"""


# Store conversation history for context
conversation_history: list[dict[str, str]] = []


def _build_context_prompt(transcript: str) -> str:
    """Build prompt with conversation history for the LLM."""
    system_prompt = brain._load_system_prompt()

    # Add recent conversation context (last 6 exchanges = 12 messages)
    context_lines = []
    for msg in conversation_history[-12:]:
        role = "User" if msg["role"] == "user" else "Clovis"
        context_lines.append(f"{role}: {msg['content']}")

    context = "\n".join(context_lines) if context_lines else "(no prior conversation)"

    return f"{system_prompt}\n\nConversation so far:\n{context}\n\nUser: {transcript}"


def _extract_json_and_text(raw_response: str) -> tuple[str, dict | None]:
    """
    Split LLM response into conversational text and optional JSON.
    Returns (conversational_text, json_dict_or_none).
    """
    # Look for JSON object in the response
    json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
    if not json_match:
        return raw_response.strip(), None

    json_str = json_match.group(0)
    conversational = raw_response[:json_match.start()].strip()

    try:
        parsed = json.loads(json_str)
        # Validate it has the expected structure - require intent and params at minimum
        if "intent" in parsed and "params" in parsed:
            # If response is missing, use a default based on intent
            if "response" not in parsed:
                parsed["response"] = f"Done: {parsed['intent']} completed."
            return conversational, parsed
    except json.JSONDecodeError:
        pass

    return raw_response.strip(), None


def process(transcript: str) -> tuple[str, str | None]:
    """
    Route transcript and return (conversational_response, task_response_or_none).
    task_response is the spoken response after task execution, or None if no task.
    """
    transcript = transcript.strip()
    if not transcript:
        return "", None

    # Add user message to history
    conversation_history.append({"role": "user", "content": transcript})

    # ── Fast path ──────────────────────────────────────────────────────────────
    fast_result = router.fast_route(transcript.lower())
    if fast_result is not None:
        response = fast_result.get("response", "")
        conversation_history.append({"role": "assistant", "content": response})
        return response, None

    # ── LLM path ───────────────────────────────────────────────────────────────
    if not brain.is_ollama_running():
        response = (
            "Ollama isn't running, so I can only handle basic commands like "
            "opening apps, checking time/date, or quick math. "
            "Start it with 'ollama serve' for full chat + task support."
        )
        conversation_history.append({"role": "assistant", "content": response})
        return response, None

    # Build prompt with conversation context
    full_prompt = _build_context_prompt(transcript)

    # Query LLM with context using brain module
    llm_result = brain.query_with_context(full_prompt)
    raw_output = llm_result.get("response", "")

    # Split conversational text from JSON task
    conversational, task_json = _extract_json_and_text(raw_output)

    if task_json:
        # Execute the task
        task_result = dispatcher.dispatch(task_json, original_text=transcript)
        # Add both parts to history
        full_response = f"{conversational}\n{task_result}".strip()
        conversation_history.append({"role": "assistant", "content": full_response})
        return conversational, task_result
    else:
        # Pure conversation OR task that failed to produce JSON
        # Check if this looks like a task request that failed
        task_keywords = ["create", "delete", "open", "send", "message", "list", "move", "download", "search", "folder", "file", "screenshot", "whatsapp", "email", "chrome", "browser"]
        is_likely_task = any(kw in transcript.lower() for kw in task_keywords)
        
        if is_likely_task:
            # This was likely a task request but LLM didn't produce JSON
            # Don't add the failed response to history; return a helpful message
            fallback = "I didn't catch that as a clear command. Could you rephrase? For example: 'create a folder called X on desktop' or 'message John on WhatsApp hello'"
            return fallback, None
        else:
            # Pure conversation
            conversation_history.append({"role": "assistant", "content": conversational})
            return conversational, None


def main() -> None:
    print(BANNER)

    # Quick Ollama status line
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
            print("\n[Clovis] Goodbye, Aryan!")
            sys.exit(0)

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "bye", "goodbye"}:
            print("[Clovis] Goodbye, Aryan!")
            sys.exit(0)

        conversational, task_response = process(user_input)

        if conversational:
            print(f"Clovis: {conversational}")
        if task_response:
            print(f"[Task done] {task_response}")
        print()


if __name__ == "__main__":
    main()
    