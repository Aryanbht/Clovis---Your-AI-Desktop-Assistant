"""
tools/file_ops.py - File and folder operations using pathlib + os.
All functions return a plain string suitable for TTS output.
"""

from __future__ import annotations

import difflib
import os
import shutil
from pathlib import Path

from config import DESKTOP_PATH, DOCUMENTS_PATH, DOWNLOADS_PATH


# ── Path resolution ────────────────────────────────────────────────────────────
# The LLM sometimes generates wrong base paths (e.g. C:/Users/bhatn/Desktop
# instead of C:/Users/bhatn/OneDrive/Desktop). _resolve_path detects any path
# that mentions "desktop", "downloads", or "documents" as a component and
# rewrites it to the real path from config.py.

def _resolve_path(path: str) -> str:
    """
    Rewrite *path* so that known folder shortcuts always point to the real
    location read from the Windows registry (via config.py).

    Examples
    --------
    "C:/Users/bhatn/Desktop/foo"          -> "<DESKTOP_PATH>/foo"
    "C:/Users/anyone/Downloads/file.zip"  -> "<DOWNLOADS_PATH>/file.zip"
    "desktop"                             -> DESKTOP_PATH
    "downloads/file.zip"                  -> "<DOWNLOADS_PATH>/file.zip"
    """
    p       = Path(path)
    parts   = p.parts          # e.g. ('C:\\', 'Users', 'bhatn', 'Desktop', 'foo')
    lower   = [pt.lower() for pt in parts]

    _ROOTS = {
        "desktop":   Path(DESKTOP_PATH),
        "downloads": Path(DOWNLOADS_PATH),
        "documents": Path(DOCUMENTS_PATH),
    }

    for keyword, real_root in _ROOTS.items():
        if keyword in lower:
            idx  = lower.index(keyword)
            rest = Path(*parts[idx + 1:]) if idx + 1 < len(parts) else Path()
            return str(real_root / rest)

    return path   # no known folder found -- return unchanged


def _fuzzy_resolve_path(path: str) -> str:
    """
    Resolve *path* to an existing filesystem path using fuzzy matching.

    Algorithm (applied to each unresolved path component, deepest first):
      1. If the full path exists -> return as-is.
      2. Take the parent directory and the missing child name.
      3. Scan all entries (dirs + files) in the parent.
      4. Run a 4-stage match pipeline against the child name:
           Stage 1 - Case-insensitive exact match
           Stage 2 - All query words appear in candidate name
           Stage 3 - All candidate words appear in query
           Stage 4 - Significant word overlap (>= 50 %)
           Stage 5 - difflib ratio >= 0.55  (typos / abbreviations)
      5. Return the matched path, or the original path if nothing fits.

    Examples
    --------
    "D:/zero waste folder"  ->  "D:/Zero Waste"
    "D:/voice assistant"    ->  "D:/Voice Assistant"
    "D:/weeknd style"       ->  "D:/weekend style"  (typo)
    """
    p = Path(_resolve_path(path))  # apply known-folder rewrites first

    if p.exists():
        return str(p)

    # Walk up and find the first non-existent component
    # We only fuzzy-match the LAST non-existent segment; the parent must exist.
    parent = p.parent
    if not parent.exists():
        grandparent = parent.parent
        if grandparent.exists():
            # ── Stage 0: join the last two components into one name ──────────
            # The LLM sometimes splits a folder name with spaces into separate
            # path components, e.g. "Cakewalk Content" -> "Cakewalk/Content".
            # Try matching the joined name directly in the grandparent first.
            joined = f"{parent.name} {p.name}"  # e.g. "Cakewalk Content"
            try:
                gp_entries   = list(grandparent.iterdir())
                gp_names     = [e.name for e in gp_entries]
                gp_lower     = [n.lower() for n in gp_names]
                joined_lower = joined.lower()

                # Exact joined match
                if joined_lower in gp_lower:
                    idx = gp_lower.index(joined_lower)
                    matched = str(grandparent / gp_names[idx])
                    print(f"[FileOps] Fuzzy match (join): '{parent.name}/{p.name}' -> '{gp_names[idx]}'")
                    return matched

                # Fuzzy joined match
                close = difflib.get_close_matches(joined_lower, gp_lower, n=1, cutoff=0.60)
                if close:
                    idx = gp_lower.index(close[0])
                    matched = str(grandparent / gp_names[idx])
                    print(f"[FileOps] Fuzzy match (join~difflib): '{parent.name}/{p.name}' -> '{gp_names[idx]}'")
                    return matched
            except PermissionError:
                pass

            # ── Recursive parent resolution ───────────────────────────────────
            parent = Path(_fuzzy_resolve_path(str(parent)))
            if not parent.exists():
                return str(p)

        else:
            return str(p)

    target_name = p.name.lower().strip()

    try:
        candidates = list(parent.iterdir())
    except PermissionError:
        return str(p)

    if not candidates:
        return str(p)

    cand_names  = [c.name for c in candidates]
    cand_lower  = [c.name.lower() for c in candidates]

    def _words(s: str) -> set[str]:
        return {w for w in s.split() if len(w) >= 2}

    target_words = _words(target_name)

    # Stage 1 - exact case-insensitive
    for i, name in enumerate(cand_lower):
        if name == target_name:
            matched = str(parent / cand_names[i])
            print(f"[FileOps] Fuzzy match (exact-ci): '{p.name}' -> '{cand_names[i]}'")
            return matched

    # ── Score-based ranking across ALL candidates ──────────────────────────────
    # Previous first-match approach would return "Dekho zara" (2/3 word match)
    # before checking "Dekho Zara Video" (3/3 word match = perfect).
    # Now every candidate gets a composite score and the BEST one wins.
    #
    # Score components (all normalized 0.0-1.0, higher = better match):
    #   word_recall  : fraction of TARGET words found in candidate
    #   word_precision: fraction of CANDIDATE words found in target
    #   seq_sim      : difflib character-level sequence similarity
    #   len_penalty  : penalise large length differences
    #
    # Thresholds to accept a match:
    #   - word_recall >= 0.5  (at least half the query words are in the name)
    #   - OR  seq_sim  >= 0.65

    scored: list[tuple[float, int]] = []

    for i, name in enumerate(cand_lower):
        cand_words = _words(name)

        # Word recall = |target ∩ cand| / |target|
        if target_words:
            word_recall    = len(target_words & cand_words) / len(target_words)
            word_precision = (len(target_words & cand_words) / len(cand_words)
                              if cand_words else 0.0)
        else:
            word_recall = word_precision = 0.0

        # Character-level similarity
        seq_sim = difflib.SequenceMatcher(None, target_name, name).ratio()

        # Length penalty: discount if one string is much longer than the other
        len_ratio = (min(len(name), len(target_name)) /
                     max(len(name), len(target_name), 1))

        # Combined score (recall carries most weight)
        score = (word_recall * 0.50
                 + word_precision * 0.20
                 + seq_sim       * 0.20
                 + len_ratio     * 0.10)

        # Only consider candidates that clear a basic threshold
        if word_recall > 0.55 or seq_sim >= 0.72:
            scored.append((score, i))

    if scored:
        scored.sort(reverse=True)            # best score first
        best_score, best_i = scored[0]
        matched = str(parent / cand_names[best_i])
        print(f"[FileOps] Fuzzy match (score {best_score:.2f}): "
              f"'{p.name}' -> '{cand_names[best_i]}'")
        return matched

    return str(p)   # no match -- return original; _resolve_any will run system search


# ── System-wide folder search ──────────────────────────────────────────────────

_SKIP_SYSTEM_DIRS = {
    "windows", "system32", "syswow64", "system volume information",
    "$recycle.bin", "perflogs", "msocache", "$windows.~ws", "$windows.~bt",
    "recovery", "boot", "efi",
}


def _search_system_for_folder(folder_name: str) -> str | None:
    """
    Search the entire PC for a folder that fuzzy-matches *folder_name*.

    Strategy (fastest-first):
      1. Check user folders: Desktop, Downloads, Documents, home dir
      2. Check root of every available drive (C:\\, D:\\, ...)
      3. Check 1 level deep inside each drive root (skipping system dirs)

    Returns the matched absolute path string, or None if not found.

    Example
    -------
    _search_system_for_folder("cakewalk content")  ->  "C:\\Cakewalk Content"
    _search_system_for_folder("hollow knight")      ->  "D:\\Games\\Hollow Knight"
    """
    import string

    target_lower = folder_name.lower().strip()
    t_words      = {w for w in target_lower.split() if len(w) >= 2}

    def _score_candidate(name_lower: str) -> float:
        """Composite score: word recall (60%) + seq similarity (40%)."""
        c_words = {w for w in name_lower.split() if len(w) >= 2}
        recall  = len(t_words & c_words) / max(len(t_words), 1)
        sim     = difflib.SequenceMatcher(None, target_lower, name_lower).ratio()
        len_r   = (min(len(name_lower), len(target_lower)) /
                   max(len(name_lower), len(target_lower), 1))
        return recall * 0.60 + sim * 0.25 + len_r * 0.15

    def _candidates_in(directory: Path) -> list[tuple[float, str]]:
        """Score every subfolder in *directory* and return (score, path) pairs."""
        results: list[tuple[float, str]] = []
        try:
            for entry in directory.iterdir():
                if not entry.is_dir():
                    continue
                nl    = entry.name.lower()
                score = _score_candidate(nl)
                # Must clear minimum: recall>0.55 OR very similar char sequence
                c_words = {w for w in nl.split() if len(w) >= 2}
                recall  = len(t_words & c_words) / max(len(t_words), 1)
                sim     = difflib.SequenceMatcher(None, target_lower, nl).ratio()
                if recall > 0.55 or sim >= 0.80:
                    results.append((score, str(entry)))
        except (PermissionError, OSError):
            pass
        return results

    # ── Collect all candidates from all locations ──────────────────────────────
    all_hits: list[tuple[float, str]] = []

    priority = [
        Path(DESKTOP_PATH),
        Path(DOWNLOADS_PATH),
        Path(DOCUMENTS_PATH),
        Path(DESKTOP_PATH).parent,
        Path(DESKTOP_PATH).parent.parent,
    ]
    drives = [Path(f"{d}:\\") for d in string.ascii_uppercase
              if Path(f"{d}:\\").exists()]

    for root in priority:
        if root.exists():
            all_hits.extend(_candidates_in(root))

    for drive in drives:
        all_hits.extend(_candidates_in(drive))
        try:
            for sub in drive.iterdir():
                if (sub.is_dir()
                        and sub.name.lower() not in _SKIP_SYSTEM_DIRS
                        and not sub.name.startswith("$")):
                    all_hits.extend(_candidates_in(sub))
        except (PermissionError, OSError):
            continue

    if not all_hits:
        return None

    # Return the best-scoring candidate
    all_hits.sort(reverse=True)
    best_score, best_path = all_hits[0]
    print(f"[FileOps] System search best match "
          f"(score {best_score:.2f}): '{folder_name}' -> '{best_path}'")
    return best_path


def _resolve_any(path: str) -> str:
    """
    Full 3-stage path resolution:
      1. _fuzzy_resolve_path   – fuzzy match in the specified parent dir
      2. Completeness check    – if the match is missing key query words,
                                 also run system search and take the better result
      3. _search_system_for_folder – search entire PC if still not found
    """
    resolved = _fuzzy_resolve_path(path)

    # ── Check if the local fuzzy match is COMPLETE ─────────────────────────────
    # "Dekho zara" matches "Dekho zara Video" but MISSES the word "video".
    # In that case, run the system search too and prefer the complete match.
    def _sig_words(s: str) -> set:
        return {w.lower() for w in s.split() if len(w) >= 2}

    orig_name    = Path(_resolve_path(path)).name   # e.g. "Dekho zara Video"
    target_words = _sig_words(orig_name)

    if Path(resolved).exists():
        matched_words = _sig_words(Path(resolved).name)
        missing       = target_words - matched_words

        if not missing:
            # Perfect match — all target words present, trust it
            return resolved

        # Incomplete match — some words are missing (e.g. "video")
        # Run system search to see if a better folder exists elsewhere
        print(f"[FileOps] Incomplete match (missing: {missing}), running system search...")

    # ── Build search candidates ────────────────────────────────────────────────
    parts = [p for p in Path(_resolve_path(path)).parts
             if len(p) > 3 and p not in ("\\", "/")]
    candidates = []
    if parts:
        candidates.append(parts[-1])                       # e.g. "Dekho zara Video"
    if len(parts) >= 2:
        candidates.append(f"{parts[-2]} {parts[-1]}")     # e.g. "Desktop Dekho zara Video"

    # Also try joining the last component's words differently
    if parts:
        candidates.append(orig_name)

    seen = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        found = _search_system_for_folder(name)
        if found:
            found_words = _sig_words(Path(found).name)
            # Prefer system result only if it covers MORE target words
            if not target_words or target_words.issubset(found_words):
                print(f"[FileOps] System search preferred: '{found}'")
                return found
            # Still better than original if the local match was incomplete
            if Path(resolved).exists():
                local_words = _sig_words(Path(resolved).name)
                if len(found_words & target_words) > len(local_words & target_words):
                    print(f"[FileOps] System search preferred (more words): '{found}'")
                    return found

    # Fall back to local fuzzy match if it exists, else original
    if Path(resolved).exists():
        return resolved
    return resolved   # caller will surface the error


def create_folder(path: str) -> str:
    """
    Create a folder (and any missing parents) at *path*.
    Uses fuzzy matching if the parent path name is slightly off.
    Returns a success or failure message string.
    """
    try:
        target = Path(_resolve_any(path))
        target.mkdir(parents=True, exist_ok=True)
        return f"Folder created: {target}"
    except PermissionError:
        return f"Permission denied: cannot create folder at '{path}'."
    except Exception as exc:
        return f"Failed to create folder '{path}': {exc}"


def create_file(path: str, content: str = "") -> str:
    """
    Create a file at *path* with optional *content*.
    Parent directories are created automatically.

    Returns a success or failure message string.
    """
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"File created: {target}"
    except PermissionError:
        return f"Permission denied: cannot write to '{path}'."
    except Exception as exc:
        return f"Failed to create file '{path}': {exc}"


def list_files(path: str) -> str:
    """
    List the contents of *path*, with fuzzy folder name matching.
    If the exact path doesn't exist, finds the closest matching folder name.
    Returns a formatted string of entry names or an error message.
    """
    try:
        resolved = _resolve_any(path)
        target   = Path(resolved)

        if not target.exists():
            return f"'{path}' does not exist."
        if not target.is_dir():
            return f"'{path}' is a file, not a folder."

        entries = sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))

        if not entries:
            return f"'{path}' is empty."

        lines: list[str] = []
        folders = [e for e in entries if e.is_dir()]
        files   = [e for e in entries if e.is_file()]

        # Header
        lines.append(f"📂 Contents of  {target}  ({len(folders)} folder(s), {len(files)} file(s))")
        lines.append("─" * 52)

        for folder in folders:
            lines.append(f"  [DIR]  {folder.name}")
        for file in files:
            size = file.stat().st_size
            lines.append(f"  [FILE] {file.name}  ({_human_size(size)})")

        # Short summary at the end for TTS (voice mode reads this last line)
        lines.append(f"\nFound {len(folders)} folder(s) and {len(files)} file(s) in '{target.name}'.")
        return "\n".join(lines)

    except PermissionError:
        return f"Permission denied: cannot read '{path}'."
    except Exception as exc:
        return f"Failed to list '{path}': {exc}"


def delete_file(path: str) -> str:
    """
    Delete a file or folder at *path*, with fuzzy name matching.
    Returns a success or failure message string.
    """
    try:
        target = Path(_resolve_any(path))

        if not target.exists():
            return f"'{path}' does not exist."

        if target.is_dir():
            shutil.rmtree(target)
            return f"Folder deleted: {target}"
        else:
            target.unlink()
            return f"File deleted: {target}"

    except PermissionError:
        return f"Permission denied: cannot delete '{path}'."
    except Exception as exc:
        return f"Failed to delete '{path}': {exc}"


def move_file(src: str, dest: str) -> str:
    """
    Move or rename file/folder at *src* to *dest*, with fuzzy name matching.
    Returns a success or failure message string.
    """
    try:
        source      = Path(_resolve_any(src))
        destination = Path(_resolve_any(dest))

        if not source.exists():
            return f"Source '{src}' does not exist."

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return f"Moved '{source.name}' -> '{destination}'."

    except PermissionError:
        return f"Permission denied: cannot move '{src}'."
    except Exception as exc:
        return f"Failed to move '{src}' to '{dest}': {exc}"


# ── Internal helper ────────────────────────────────────────────────────────────

def _human_size(n_bytes: int) -> str:
    """Convert a byte count to a human-readable string (e.g. '1.4 MB')."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} PB"
