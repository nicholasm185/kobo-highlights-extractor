from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

__all__ = [
    "find_kobo_sqlite_paths",
    "choose_best_kobo_sqlite",
]


def _candidate_roots() -> List[Path]:
    roots: List[Path] = []
    user = os.environ.get("USER") or os.environ.get("USERNAME") or ""

    if sys.platform.startswith("linux"):
        # Common Linux mount locations (GNOME/KDE/others)
        roots.extend(
            [
                Path("/run/media") / user,
                Path("/media") / user,
                Path("/media"),
                Path("/mnt"),
            ]
        )
    elif sys.platform == "darwin":  # macOS
        roots.append(Path("/Volumes"))
    elif os.name == "nt":  # Windows
        # Try typical removable drive letters (skip C)
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            roots.append(Path(f"{letter}:/"))
    else:
        # Fallback generic guesses
        roots.extend([Path("/mnt"), Path("/media"), Path("/Volumes")])

    # Only keep existing roots
    return [p for p in roots if p.exists()]


def _possible_mounts(root: Path) -> Iterable[Path]:
    # The device may be mounted directly at the root (e.g., D:/ on Windows),
    # or as a subdirectory under the root (e.g., /run/media/$USER/KOBOeReader)
    yield root
    try:
        for child in root.iterdir():
            if child.is_dir():
                yield child
    except Exception:
        # Ignore permission errors or transient FS errors
        pass


def find_kobo_sqlite_paths() -> List[Path]:
    """Search common mount points for a connected Kobo eReader database file.

    Returns a list of candidate paths to ".kobo/KoboReader.sqlite".
    """
    matches: List[Path] = []
    for base in _candidate_roots():
        for mount in _possible_mounts(base):
            # Typical layout on device: <mount>/.kobo/KoboReader.sqlite
            candidate = mount / ".kobo" / "KoboReader.sqlite"
            try:
                if candidate.is_file():
                    matches.append(candidate)
            except Exception:
                # Ignore unreadable paths
                continue
    return matches


def choose_best_kobo_sqlite(paths: List[Path]) -> Optional[Path]:
    """Choose the most likely Kobo database among candidates.

    Heuristics:
    - Prefer a path with a parent directory name containing 'kobo'
    - Otherwise, pick the most recently modified database
    """
    if not paths:
        return None

    def score(p: Path) -> tuple[int, float]:
        parents_str = "/".join(part.lower() for part in p.parts)
        kobo_hint = 1 if "kobo" in parents_str else 0
        try:
            mtime = p.stat().st_mtime
        except Exception:
            mtime = 0.0
        # Higher is better
        return (kobo_hint, mtime)

    return sorted(paths, key=score, reverse=True)[0]
