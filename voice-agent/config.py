# ── Configuration ──────────────────────────────────────────────────────────────

import sys
from pathlib import Path

USERNAME = "Aryan"


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
DESKTOP_PATH   = _get_shell_folder("Desktop")
DOWNLOADS_PATH = _get_shell_folder("{374DE290-123F-4565-9164-39C4925E467B}")  # Downloads GUID
DOCUMENTS_PATH = _get_shell_folder("Personal")  # "Personal" is the registry key for Documents

# Ollama / LLM settings
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:3b-instruct"

# Speech-to-text settings
WHISPER_MODEL_SIZE = "base"

# Wake word (lower-case; detection is case-insensitive)
WAKE_WORD = "nova"
