# 🤖 Clovis - Your AI Desktop Assistant

A locally-running AI assistant for Windows, powered by **Ollama** (LLM) and **Faster-Whisper** (STT). Understands natural language commands to control your PC, manage files, open any app, and more — completely offline.

---

## ✨ Features

| Category | What Clovis can do |
|---|---|
| 🗣️ **Voice / Text** | Wake-word detection ("Clovis"), speech-to-text, or type commands directly |
| 📁 **File System** | Create, delete, list, and move files and folders |
| 🚀 **App Launcher** | Open **any** installed app — Start Menu, Store, Steam, Epic, cracked installs, anything |
| 🌐 **Browser** | Open URLs and search the web |
| 📸 **Screenshot** | Take and save a screenshot to your Desktop |
| 🔒 **Lock Screen** | Lock your PC instantly |
| 🔊 **Volume** | Volume up / down / mute |
| ➕ **Quick Math** | Instant arithmetic without the LLM |
| 🕐 **Time & Date** | Tell the current time and date |
| 💬 **WhatsApp** | Send messages via WhatsApp (with phone number + text) |
| 📧 **Gmail** | Open Gmail or compose an email |
| ⬇️ **Downloader** | Download files to your Downloads folder |
| 🤖 **LLM Fallback** | Anything not handled by fast-path goes to `qwen2.5-coder:3b` via Ollama |

---

## 🏗️ Architecture

```
User Input (voice / text)
        │
        ▼
   router.py  ──── Fast Path ────► system_ops / file_ops / etc.
        │                               (instant, no LLM needed)
        │ (no match)
        ▼
   brain.py ──── Ollama LLM ────► dispatcher.py ──► tool functions
   (qwen2.5-coder:3b)                     │
                                          ▼
                                     tts.py (speak result)
```

### File Map

```
voice-agent/
├── main.py          # Voice loop — wake word → listen → route → speak
├── chat.py          # Text loop — type commands in the terminal
├── router.py        # Fast-path pattern matching (regex, no LLM)
├── brain.py         # LLM interface — sends prompt to Ollama, parses JSON
├── dispatcher.py    # Intent → function mapper (routes LLM output to tools)
├── listener.py      # Microphone input + Whisper STT
├── tts.py           # Text-to-speech (edge-tts / pyttsx3)
├── config.py        # Global settings (model, wake word, paths)
├── agent.log        # All dispatched intents logged with timestamps
├── requirements.txt
├── prompts/
│   └── system_prompt.txt   # System prompt for the LLM
└── tools/
    ├── app_finder.py   # Smart app discovery (Get-StartApps + Epic + Steam + Registry)
    ├── system_ops.py   # Screenshot, lock screen, open app
    ├── file_ops.py     # Create/delete/list/move files and folders
    ├── browser.py      # Open URLs, web search
    ├── downloader.py   # Download files
    ├── messenger.py    # WhatsApp messaging
    └── gmail.py        # Gmail integration
```

---

## ⚡ Smart App Launcher

The app launcher (`tools/app_finder.py`) scans **4 sources** at startup:

1. **Windows Start Menu** — all traditional Win32 + Electron apps (VS Code, Chrome, Discord, etc.)
2. **Microsoft Store** — WhatsApp, Calculator, Notepad, Paint, Teams, etc.
3. **Epic Games manifests** — any game installed via the Epic Games Launcher
4. **Steam `.acf` manifests** — all Steam games across all library folders
5. **Windows Registry** — FitGirl repacks, GOG games, standalone installers — anything with an Uninstall entry

> **No hardcoded app list.** It discovers every app on your PC dynamically. Just restart `chat.py` after installing a new app.

**Fuzzy matching** handles typos and alternate names:

| You say | Opens |
|---|---|
| `open whatsapp` | WhatsApp (Store) |
| `open vs code` | Visual Studio Code |
| `open hollow knight` | Hollow Knight (from Games folder) |
| `open cakewalk sonar` | Cakewalk Sonar (Program Files) |
| `open chrome` | Google Chrome |

---

## 🚀 Getting Started

### Prerequisites

- **Windows 10 / 11**
- **Python 3.10+**
- **[Ollama](https://ollama.com)** installed and running

### 1. Install Ollama model

```bash
ollama pull qwen2.5-coder:3b
```

### 2. Install Python dependencies

```bash
cd voice-agent
pip install -r requirements.txt
```

### 3. Run in text mode (recommended to start)

```bash
python chat.py
```

### 4. Run in voice mode

```bash
python main.py
```

> Say **"Clovis"** to activate, then speak your command.

---

## ⚙️ Configuration

Edit [`config.py`](config.py) to customize:

```python
USERNAME          = "Aryan"              # Your name
WAKE_WORD         = "clovis"           # Wake word (case-insensitive)
OLLAMA_MODEL      = "qwen2.5-coder:3b"  # LLM model
WHISPER_MODEL_SIZE = "base"             # STT model (tiny / base / small)
```

Paths (Desktop, Downloads, Documents) are read from the **Windows Registry** automatically — even if you've relocated them to a different drive via OneDrive or Settings.

---

## 💬 Example Commands

```
open whatsapp
open vs code
open hollow knight
take a screenshot
create a folder called Projects on the desktop
list files in downloads
what time is it
what is 45 times 12
lock the screen
volume up
search for best Python tutorials on YouTube
download https://example.com/file.zip
```

---

## 📋 Requirements

| Package | Purpose |
|---|---|
| `faster-whisper` | Speech-to-text (offline, runs locally) |
| `sounddevice` | Microphone input |
| `scipy` | Audio processing |
| `requests` | HTTP calls to Ollama API |
| `pyttsx3` | Offline TTS fallback |
| `edge-tts` | High-quality online TTS (Microsoft Edge voices) |
| `pyautogui` | Screenshots + volume key presses |
| `ollama` | Ollama Python client |

---

## 📝 Logging

Every dispatched intent is logged to [`agent.log`](agent.log) with a timestamp:

```
[2026-09-14 16:10:23] intent=open_app | params={'app_name': 'Hollow Knight'} | result=Opening Hollow Knight.
[2026-09-14 16:11:05] intent=take_screenshot | params={} | result=Screenshot saved to 'D:\OneDrive\Desktop\screenshot_20260914_161105.png'.
```

---

## 🛠️ How the Fast Path Works

`router.py` handles common intents **instantly** via regex — no LLM call needed:

| Pattern | Intent | Example |
|---|---|---|
| `open / launch / start <app>` | `open_app` | "open chrome" |
| `what time is it` | `tell_time` | "what's the time?" |
| `what's the date` | `tell_date` | "today's date?" |
| `<number> + - * / <number>` | `quick_math` | "what is 12 times 7" |
| `volume up / down / mute` | `volume_*` | "turn up the volume" |
| `hey / hello / hi` | `greet` | "hey clovis" |

Everything else is sent to the LLM.

---

## 🤝 Contributing / Extending

To add a new tool:
1. Add a function to an existing file in `tools/` (or create a new one)
2. Register the intent in `dispatcher.py`
3. Add a regex pattern in `router.py` if it's a fast-path intent
4. Add an example to the system prompt in `prompts/system_prompt.txt`
