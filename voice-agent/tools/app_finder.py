"""
tools/app_finder.py – Fully dynamic app discovery using PowerShell's Get-StartApps.

NO hardcoded app names. Scans every installed app on the system automatically:
  - Win32 applications (from Start Menu shortcuts)
  - Microsoft Store apps
  - Electron apps (Discord, Spotify, etc.)
  - Anything that shows up in the Windows Start Menu

How it works:
  1. Runs `Get-StartApps | ConvertTo-Json` once at startup (cached in memory).
  2. Builds an index: {display_name.lower() → AppID}.
  3. Fuzzy-matches user queries through a 5-stage pipeline.
  4. Launches the matched app using the AppID directly.

Launching:
  - Win32 exe path   → subprocess.Popen([exe_path])
  - Store AUMID      → explorer.exe shell:AppsFolder\\<aumid>
  - Other IDs        → Start-Process via PowerShell (universal fallback)
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from config import BASE_DIR


# ── Minimal abbreviation table ─────────────────────────────────────────────────
# ONLY genuine abbreviations / alternate spellings.
# NOT app-specific — the display name matching handles everything else.

_ABBREV: dict[str, str] = {
    # Common shorthands
    "wa":          "whatsapp",
    "vsc":         "visual studio code",
    "vs code":     "visual studio code",
    "vscode":      "visual studio code",
    "calc":        "calculator",
    "edge":        "microsoft edge",
    "ms edge":     "microsoft edge",
    "word":        "microsoft word",
    "excel":       "microsoft excel",
    "pp":          "powerpoint",
    "ppt":         "powerpoint",
    "ps":          "powershell",
    "cmd":         "command prompt",
    "explorer":    "file explorer",
}

# ── Windows Known-Folder GUIDs → real paths ───────────────────────────────────
# Get-StartApps encodes exe paths using these GUIDs.

_GUID_MAP: dict[str, str] = {
    "{6D809377-6AF0-444B-8957-A3773F02200E}": os.environ.get("PROGRAMFILES",
                                                              "C:\\Program Files"),
    "{7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E}": os.environ.get("PROGRAMFILES(X86)",
                                                               "C:\\Program Files (x86)"),
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}": os.path.join(
        os.environ.get("SystemRoot", "C:\\Windows"), "System32"),
    "{D65231B0-B2F1-4857-A4CE-A8E7C6EA7D27}": os.path.join(
        os.environ.get("SystemRoot", "C:\\Windows"), "System32"),
    "{F38BF404-1D43-42F2-9305-67DE0B28FC23}": os.environ.get("SystemDrive", "C:") + "\\",
    "{0139D44E-6AFE-49F2-8690-3DAFCAE6FFB2}": os.path.join(
        os.environ.get("APPDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs"),
}

# Skip entries whose name contains these words (help docs, uninstallers, etc.)
_SKIP_NAME_RE = re.compile(
    r"\b(uninstall|setup\.exe|readme|manual|user\s*guide|release\s*notes"
    r"|getting\s*started|tutorial|documentation|what'?s\s*new)\b",
    re.IGNORECASE,
)

# Skip web-only shortcuts
_SKIP_APPID_RE = re.compile(r"^https?://", re.IGNORECASE)

# Stop words for word-overlap matching
_STOP_WORDS = {"the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "by", "de"}


# ══════════════════════════════════════════════════════════════════════════════
# Index: display_name.lower() → AppID string
# ══════════════════════════════════════════════════════════════════════════════

_APP_INDEX: dict[str, str] = {}
_INDEX_BUILT = False

CACHE_FILE = BASE_DIR / "app_cache.json"

def load_cache() -> dict | None:
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(data["cached_at"])
        if (datetime.now() - cached_at).total_seconds() > 86400:
            return None
        return data["apps"]
    except Exception as exc:
        print(f"[AppFinder] Failed to load cache: {exc}")
        return None

def save_cache(app_dict: dict) -> None:
    try:
        data = {
            "cached_at": datetime.now().isoformat(),
            "apps": app_dict
        }
        CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[AppFinder] Failed to save cache: {exc}")


def _resolve_guid_path(app_id: str) -> str:
    """Replace Windows Known-Folder GUIDs in an AppID with real paths."""
    for guid, real_path in _GUID_MAP.items():
        if guid.upper() in app_id.upper():
            # Case-insensitive replace
            idx = app_id.upper().find(guid.upper())
            app_id = app_id[:idx] + real_path + app_id[idx + len(guid):]
    # Normalize separators
    return app_id.replace("\\\\", "\\")


def _build_index() -> None:
    """Query Get-StartApps + Epic Games + Steam + exe-search and populate _APP_INDEX."""
    global _INDEX_BUILT

    cached_apps = load_cache()
    if cached_apps is not None:
        _APP_INDEX.clear()
        _APP_INDEX.update(cached_apps)
        _INDEX_BUILT = True
        print(f"[APP INDEX] Loaded from cache ({len(_APP_INDEX)} apps)")
        return

    _APP_INDEX.clear()

    if sys.platform != "win32":
        _INDEX_BUILT = True
        return

    # ── 1. Get-StartApps (Win32 + Store + Electron) ────────────────────────────
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=25,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            if isinstance(data, dict):
                data = [data]
            for entry in data:
                name   = (entry.get("Name")  or "").strip()
                app_id = (entry.get("AppID") or "").strip()
                if not name or not app_id:
                    continue
                if _SKIP_NAME_RE.search(name):
                    continue
                if _SKIP_APPID_RE.match(app_id):
                    continue
                _APP_INDEX[name.lower()] = _resolve_guid_path(app_id)
    except Exception as exc:
        print(f"[AppFinder] Get-StartApps error: {exc}")

    # ── 2. Epic Games manifests ────────────────────────────────────────────────
    _scan_epic_games()

    # ── 3. Steam manifests (all library folders) ───────────────────────────────
    _scan_steam_games()

    # ── 4. Windows Registry (catches installers, FitGirl repacks, etc.) ────────
    _scan_registry()

    _INDEX_BUILT = True
    save_cache(_APP_INDEX)
    print(f"[APP INDEX] Rebuilt index ({len(_APP_INDEX)} apps)")


def _scan_epic_games() -> None:
    """Scan Epic Games manifests and add games to _APP_INDEX."""
    # Epic stores .item manifest files here
    manifests_dir = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) \
                    / "Epic/EpicGamesLauncher/Data/Manifests"
    if not manifests_dir.exists():
        return

    for item_file in manifests_dir.glob("*.item"):
        try:
            data = json.loads(item_file.read_text(encoding="utf-8"))
            name        = data.get("DisplayName", "").strip()
            launch_exe  = data.get("LaunchExecutable", "")
            install_dir = data.get("InstallLocation", "")
            catalog_id  = data.get("CatalogItemId", "")
            app_name    = data.get("AppName", "")    # used for Epic launch URI

            if not name:
                continue

            # Prefer direct exe path, fall back to Epic launcher URI
            exe_path = Path(install_dir) / launch_exe if install_dir and launch_exe else None
            if exe_path and exe_path.exists():
                _APP_INDEX[name.lower()] = str(exe_path)
            elif app_name:
                # Launch via Epic Games Launcher protocol
                _APP_INDEX[name.lower()] = f"com.epicgames.launcher://apps/{app_name}?action=launch&silent=true"
        except Exception:
            pass

    print(f"[AppFinder] + Epic Games scanned.")


def _scan_steam_games() -> None:
    """Scan Steam library folders and add all installed games to _APP_INDEX."""
    import re as _re

    # Find Steam root (check registry first, then common paths)
    steam_root = _find_steam_root()
    if not steam_root:
        return

    # Parse libraryfolders.vdf to find all library paths
    vdf_path = steam_root / "steamapps/libraryfolders.vdf"
    library_paths = [steam_root / "steamapps"]
    if vdf_path.exists():
        vdf_text = vdf_path.read_text(encoding="utf-8", errors="ignore")
        for m in _re.finditer(r'"path"\s+"([^"]+)"', vdf_text):
            extra = Path(m.group(1).replace("\\\\", "\\")) / "steamapps"
            if extra.exists() and extra not in library_paths:
                library_paths.append(extra)

    for lib in library_paths:
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                text    = acf.read_text(encoding="utf-8", errors="ignore")
                app_id  = _re.search(r'"appid"\s+"(\d+)"', text)
                name_m  = _re.search(r'"name"\s+"([^"]+)"', text)
                if not app_id or not name_m:
                    continue
                name = name_m.group(1).strip()
                # Skip redistributables and tools
                if _SKIP_NAME_RE.search(name) or "Redistributable" in name:
                    continue
                steam_uri = f"steam://rungameid/{app_id.group(1)}"
                _APP_INDEX.setdefault(name.lower(), steam_uri)
            except Exception:
                pass

    print(f"[AppFinder] + Steam games scanned.")


def _scan_registry() -> None:
    """
    Scan Windows Uninstall registry keys for installed applications.
    Catches FitGirl repacks, GOG games, and any program installed via a
    standard Windows installer — even if it has no Start Menu shortcut.
    """
    import winreg

    reg_keys = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    added = 0
    for hive, reg_path in reg_keys:
        try:
            with winreg.OpenKey(hive, reg_path) as key:
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        i += 1
                        with winreg.OpenKey(key, sub_name) as sub:
                            try:
                                # Skip system components and background tools
                                try:
                                    if winreg.QueryValueEx(sub, "SystemComponent")[0]:
                                        continue
                                except FileNotFoundError:
                                    pass

                                display_name = winreg.QueryValueEx(sub, "DisplayName")[0].strip()
                                if not display_name or _SKIP_NAME_RE.search(display_name):
                                    continue

                                key_lower = display_name.lower()
                                if key_lower in _APP_INDEX:
                                    continue   # already found via Get-StartApps

                                # Try to find exe via DisplayIcon, InstallLocation, UninstallString
                                exe = None

                                # DisplayIcon often = "path\to\app.exe,0"
                                try:
                                    icon = winreg.QueryValueEx(sub, "DisplayIcon")[0]
                                    icon_path = icon.split(",")[0].strip().strip('"')
                                    if icon_path.lower().endswith(".exe") and Path(icon_path).exists():
                                        exe = icon_path
                                except FileNotFoundError:
                                    pass

                                # InstallLocation: find the main exe in the folder
                                if not exe:
                                    try:
                                        loc = winreg.QueryValueEx(sub, "InstallLocation")[0].strip()
                                        if loc:
                                            loc_path = Path(loc)
                                            # Look for exe named after the app
                                            words = display_name.lower().split()
                                            for ex in loc_path.glob("*.exe"):
                                                ex_lower = ex.stem.lower()
                                                if any(w in ex_lower for w in words if len(w) >= 4):
                                                    exe = str(ex)
                                                    break
                                            if not exe:
                                                # Take first non-uninstaller exe
                                                for ex in loc_path.glob("*.exe"):
                                                    if not _SKIP_NAME_RE.search(ex.stem):
                                                        exe = str(ex)
                                                        break
                                    except FileNotFoundError:
                                        pass

                                if exe:
                                    _APP_INDEX[key_lower] = exe
                                    added += 1

                            except (FileNotFoundError, OSError):
                                pass
                    except OSError:
                        break
        except Exception:
            pass

    print(f"[AppFinder] + Registry: {added} additional apps found.")


def _find_steam_root() -> Path | None:
    """Find the Steam installation directory via registry or common paths."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
            path = winreg.QueryValueEx(key, "InstallPath")[0]
            p = Path(path)
            if p.exists():
                return p
    except Exception:
        pass
    for candidate in ["C:/Program Files (x86)/Steam", "C:/Program Files/Steam"]:
        p = Path(candidate)
        if p.exists():
            return p
    return None



def _ensure_index() -> None:
    if not _INDEX_BUILT:
        _build_index()


# ══════════════════════════════════════════════════════════════════════════════
# Fuzzy matching
# ══════════════════════════════════════════════════════════════════════════════

def _sig_words(text: str) -> set[str]:
    return {w for w in text.lower().split() if len(w) >= 3 and w not in _STOP_WORDS}


def _search(q: str) -> str | None:
    """
    5-stage matching pipeline against _APP_INDEX.
    Returns the matched display name (key) or None.
    """
    # 1. Exact
    if q in _APP_INDEX:
        return q

    # 2. Prefix — app name starts with query (minimum 3 chars)
    if len(q) >= 3:
        for name in _APP_INDEX:
            if name.startswith(q):
                return name

    # 3. Substring — query appears inside an app name (minimum 4 chars)
    if len(q) >= 4:
        for name in _APP_INDEX:
            if q in name:
                return name

    # 4. ALL significant words in query appear in the app name
    q_words = _sig_words(q)
    if q_words:
        matches = [n for n in _APP_INDEX if all(w in n for w in q_words)]
        if matches:
            return min(matches, key=len)   # prefer shorter / more specific

    # 5. difflib — conservative threshold (0.72) to avoid wrong app opens
    close = difflib.get_close_matches(q, list(_APP_INDEX.keys()), n=1, cutoff=0.72)
    if close:
        return close[0]

    return None


# ══════════════════════════════════════════════════════════════════════════════
# Launcher
# ══════════════════════════════════════════════════════════════════════════════

def _launch(display_name: str, app_id: str) -> str:
    """
    Launch an app by its AppID (resolved).
    Handles:
      - Win32 exe paths
      - Store AUMIDs (contain !)
      - Steam URIs  (steam://rungameid/...)
      - Epic URIs   (com.epicgames.launcher://...)
      - Electron / generic protocol IDs
    """
    try:
        # ── Steam / Epic / protocol URI ────────────────────────────────────────
        if app_id.startswith(("steam://", "com.epicgames.launcher://",
                               "http://", "https://")):
            os.startfile(app_id)   # Windows protocol handler
            return f"Opening {display_name.title()}."

        # ── Win32 executable path ──────────────────────────────────────────────
        if app_id.lower().endswith(".exe") or (os.sep in app_id and ".exe" in app_id.lower()):
            exe = Path(app_id)
            if exe.exists():
                # os.startfile uses ShellExecute — handles UAC elevation prompts
                os.startfile(str(exe))
                return f"Opening {display_name.title()}."
            # Unresolved path — hand off to shell
            os.startfile(app_id)
            return f"Opening {display_name.title()}."

        # ── Store AUMID / Generic AppID (universal fallback) ──────────────────
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"], shell=False)
        return f"Opening {display_name.title()}."

    except Exception as exc:
        return f"Found '{display_name}' but couldn't launch it: {exc}"



# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def find_and_launch(query: str) -> str:
    """
    Find the best matching app for *query* on this system and launch it.
    Returns a human-readable string suitable for TTS.
    """
    _ensure_index()

    import string
    q = query.strip().lower().strip(string.punctuation)
    q = _ABBREV.get(q, q)       # apply abbreviation only if it's an exact alias

    match_name = _search(q)

    if match_name is None:
        # Rebuild index once (catches newly installed apps) and retry
        global _INDEX_BUILT
        _INDEX_BUILT = False
        _ensure_index()
        match_name = _search(q)

    if match_name is None:
        return f"I couldn't find any app matching '{query}' on this system."

    app_id = _APP_INDEX[match_name]
    print(f"[AppFinder] '{query}' -> '{match_name}'")
    print(f"[AppFinder]            AppID: {app_id[:80]}")
    return _launch(match_name, app_id)


# Alias for backward compatibility with system_ops.py
def launch(query: str) -> str:
    return find_and_launch(query)


def list_all_apps() -> str:
    """Return all indexed apps — useful for debugging."""
    _ensure_index()
    if not _APP_INDEX:
        return "No apps indexed."
    return "\n".join(
        f"{name:40}  {app_id[:60]}"
        for name, app_id in sorted(_APP_INDEX.items())
    )


def refresh_app_index() -> str:
    """Force a background rescan of all apps and overwrite the cache."""
    global _INDEX_BUILT
    _INDEX_BUILT = False
    
    if CACHE_FILE.exists():
        try:
            CACHE_FILE.unlink()
        except OSError:
            pass
            
    threading.Thread(target=_build_index, daemon=True).start()
    return "Rescanning all installed apps. This will take a few seconds."
