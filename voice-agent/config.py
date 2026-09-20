# ── Configuration ──────────────────────────────────────────────────────────────

import sys
from pathlib import Path

# Clovis is configured for its owner rather than inheriting a Windows account
# name, which may be abbreviated or different on another login.
USERNAME = "Shivansh Goyal"


def _get_shell_folder(name: str) -> str:
    """
    Read the real Windows shell folder path from the registry.
    This correctly handles cases where Desktop/Downloads/Documents
    have been relocated to a different drive (e.g. D:\\).
    Falls back to Path.home() / name if registry read fails.
    """
    if sys.platform == "win32":
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, name)
                return value
        except Exception:
            pass
    # Fallback for non-Windows or registry failure
    return str(Path.home() / name)


# Filesystem paths — read from Windows registry so relocated folders work correctly
BASE_DIR       = Path(__file__).parent
DESKTOP_PATH   = _get_shell_folder("Desktop")
DOWNLOADS_PATH = _get_shell_folder("{374DE290-123F-4565-9164-39C4925E467B}")  # Downloads GUID
DOCUMENTS_PATH = _get_shell_folder("Personal")  # "Personal" is the registry key for Documents

# Ollama / LLM settings
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:3b-instruct"

# Speech-to-text settings. ``base`` is fast enough for CPU use while providing
# substantially better accent recognition than the tiny model.
WHISPER_MODEL_SIZE = "base"
WHISPER_BEAM_SIZE = 8
WHISPER_INITIAL_PROMPT = (
    "Clovis is a Windows desktop voice assistant. "
    "Common commands: open Chrome, open Firefox, open Edge, open Notepad, open Calculator, "
    "open File Explorer, open Task Manager, open Settings, open Command Prompt, "
    "open PowerShell, open Terminal, open Control Panel, open Device Manager, "
    "open WhatsApp, open Telegram, open Discord, open Spotify, open Steam, "
    "open VS Code, open Notepad++, open Word, open Excel, open PowerPoint, open Outlook, "
    "open Paint, open VLC, open Steam, open Registry Editor, open Regedit, "
    "take screenshot, capture screen, grab screenshot, snap screen, "
    "lock screen, lock computer, lock PC, lock workstation, secure PC, "
    "volume up, volume down, increase volume, decrease volume, turn up, turn down, "
    "louder, quieter, mute, unmute, mute volume, silence, shut up, "
    "what time is it, what is the time, tell me the time, current time, "
    "what date is it, what is today's date, today's date, what day is it, "
    "create folder, create file, make folder, make directory, new folder, "
    "list files, list files in downloads, show files, show files in downloads, "
    "delete file, delete folder, remove file, delete test.txt, "
    "move file, move notes.txt to documents, "
    "download file, download from URL, "
    "open YouTube, open Google, open Gmail, search web, search for, "
    "open Gmail, compose email, send email, "
    "send WhatsApp, message on WhatsApp, WhatsApp message, "
    "open Telegram, open WhatsApp, "
    "set reminder, remind me to, remind me in, set timer, timer for, "
    "cancel reminder, cancel that reminder, delete reminder, "
    "snooze reminder, snooze for 5 minutes, "
    "what time is it, what's the time, tell me the time, "
    "what date is it, what is today's date, what day is it, "
    "volume up, volume down, louder, quieter, mute, unmute, "
    "lock screen, lock computer, lock PC, lock workstation, secure PC, "
    "take screenshot, capture screen, grab screenshot, snap screen, "
    "lock screen, lock computer, lock PC, lock workstation, secure PC, "
    "what time is it, what is the time, tell me the time, current time, "
    "what date is it, what is today's date, what day is it, "
    "volume up, volume down, louder, quieter, mute, unmute, "
    "lock screen, lock computer, lock PC, lock workstation, secure PC, "
    "take screenshot, capture screen, grab screenshot, snap screen, "
    "search for, search web, search YouTube, search Google, "
    "open incognito, private window, private mode, "
    "volume up, turn up, louder, increase volume, "
    "volume down, turn down, quieter, decrease volume, "
    "mute, unmute, mute volume, silence, shut up, "
    "lock screen, lock computer, lock PC, lock workstation, secure PC, "
    "take screenshot, capture screen, grab screenshot, snap screen, "
    "what time, what date, what day, "
    "remind me, set reminder, set timer, timer for, "
    "cancel reminder, cancel reminder, delete reminder, "
    "snooze, snooze for, "
    "open Chrome, open Firefox, open Edge, open Notepad, open Calculator, "
    "open File Explorer, open Task Manager, open Settings, "
    "open Command Prompt, open PowerShell, open Terminal, "
    "open Control Panel, open Device Manager, open Registry Editor, "
    "open Notepad++, open Word, open Excel, open PowerPoint, open Outlook, "
    "open Paint, open VLC, open Steam, open Registry Editor, "
    "open WhatsApp, open Telegram, open Discord, open Spotify, open Steam, "
    "open VS Code, open Visual Studio Code, "
    "search for, search web, search YouTube, search Google, "
    "open incognito, private window, private mode, "
    "wake up Clovis, hey Clovis, hello Clovis, hi Clovis, "
    "hey Clovis, hello Clovis, hi Clovis, "
    "good morning, good afternoon, good evening, good night, "
    "hello, hi, hey, wassup, howdy, greetings, "
    "thank you, thanks, cheers, appreciate it, "
    "goodbye, bye, see you, later, bye bye, catch you later, "
    "what is, calculate, compute, solve, evaluate, "
    "plus, minus, times, divided by, times, multiply, divide, "
    "remind me, set reminder, set timer, timer for, "
    "cancel reminder, cancel that reminder, delete reminder, "
    "snooze, snooze for, "
    "volume up, volume down, louder, quieter, mute, unmute, "
    "lock screen, lock computer, lock PC, lock workstation, secure PC, "
    "take screenshot, capture screen, grab screenshot, snap screen, "
    "what time, what date, what day, "
    "search for, search web, search YouTube, search Google, "
    "open incognito, private window, private mode, "
    "wake up Clovis, hey Clovis, hello Clovis, hi Clovis, "
    "good morning, good afternoon, good evening, good night, "
    "hello, hi, hey, wassup, howdy, greetings, "
    "thank you, thanks, cheers, appreciate it, "
    "goodbye, bye, see you, later, bye bye, catch you later, "
    "what is, calculate, compute, solve, evaluate, "
    "plus, minus, times, divided by, times, multiply, divide, "
    "remind me, set reminder, set timer, timer for, "
    "cancel reminder, cancel that reminder, delete reminder, "
    "snooze, snooze for, "
    "volume up, volume down, louder, quieter, mute, unmute, "
    "lock screen, lock computer, lock PC, lock workstation, secure PC, "
    "take screenshot, capture screen, grab screenshot, snap screen, "
    "what time, what date, what day, "
    "search for, search web, search YouTube, search Google, "
    "open incognito, private window, private mode, "
    "wake up Clovis, hey Clovis, hello Clovis, hi Clovis, "
    "good morning, good afternoon, good evening, good night, "
    "hello, hi, hey, wassup, howdy, greetings, "
    "thank you, thanks, cheers, appreciate it, "
    "goodbye, bye, see you, later, bye bye, catch you later, "
    "what is, calculate, compute, solve, evaluate, "
    "plus, minus, times, divided by, times, multiply, divide."
)

# Keep spoken answers brief and quick. Edge TTS accepts percentage strings.
TTS_RATE = "+20%"
TTS_FALLBACK_RATE = 210

# Wake word (lower-case; detection is case-insensitive)
WAKE_WORD = "wake up"
