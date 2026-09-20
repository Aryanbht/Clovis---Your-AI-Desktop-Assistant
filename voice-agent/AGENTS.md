# AGENTS.md — Clovis Voice Assistant

## Project Overview
Clovis is a Windows desktop voice assistant. It uses Ollama (local LLM), Faster-Whisper (STT),
Edge-TTS/pyttsx3 (TTS), and Rich for a terminal UI. Runs entirely offline for core features.

## Run Commands
```bash
# Text mode (no microphone needed, LLM available if Ollama is running)
python main.py --text

# Voice mode with wake word ("wake up")
python main.py

# Voice mode without wake word (listens immediately)
python main.py --no-wake-word

# Hybrid mode (type or press Enter to speak)
python main.py --hybrid

# Chat module (alters text interface)
python chat.py

# Setup validator (checks env, packages, mic, Ollama, config)
python setup_check.py

# JSON extraction unit tests
python test_extract.py
```

## Virtual Environment
The project uses a `.venv` in `voice-agent/`. Activate with:
```bash
.venv\Scripts\activate
```

## Key Architecture
- `main.py` — entry point, mode loops, background LLM worker
- `router.py` — fast-path regex routing (sub-5ms for common commands)
- `brain.py` — LLM communication, JSON extraction, conversation history
- `dispatcher.py` — maps LLM intents to tool functions in `tools/`
- `listener.py` — microphone capture, VAD, Whisper STT
- `tts.py` — speech synthesis (edge-tts primary, pyttsx3 fallback)
- `ui.py` — Rich terminal UI components
- `config.py` — global settings, Windows shell folder paths

## Development Notes
- `setup_check.py` now reconfigures stdout to UTF-8 on import, so it works
  even without `PYTHONIOENCODING=utf-8` being set externally.
- Fast-path intents (router.py) bypass the LLM entirely for common commands.
- LLM responses must use intents from the system_prompt.txt INTENTS list.
- Debug/dev scripts have been removed from the repo; keep new scratch files
  in a separate location or in a `debug/` subdirectory that is gitignored.
