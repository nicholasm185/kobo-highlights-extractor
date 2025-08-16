from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__all__ = ["export_markdown_from_csv"]


# HTML tag wrappers for each color used in Markdown output (inline styles for portability)
HTML_TAGS: dict[str, tuple[str, str]] = {
    "yellow": ('<mark style="background-color: yellow">', "</mark>"),
    "pink": ('<mark style="background-color: pink">', "</mark>"),
    "blue": ('<mark style="background-color: lightblue">', "</mark>"),
    "green": ('<mark style="background-color: lightgreen">', "</mark>"),
}


def _wrap_with_color(s: str, color: str) -> str:
    """Wrap string with HTML color tags if color is recognized.

    If color is empty or unrecognized, return the string unchanged.
    """
    c = (color or "").strip().lower()
    tags = HTML_TAGS.get(c)
    if not tags:
        return s
    open_tag, close_tag = tags
    return f"{open_tag}{s}{close_tag}"


@dataclass(frozen=True)
class Row:
    BookmarkID: str
    BookTitle: str
    Author: str
    ChapterTitle: str
    DateCreated: str
    DateModified: str
    Color: str
    Text: str
    Annotation: str
    Type: str


def _norm(s: Optional[str], fallback: str = "") -> str:
    if s is None:
        return fallback
    v = str(s).strip()
    return v if v else fallback


def _parse_dt(s: str) -> Tuple[int, str]:
    """Parse a timestamp-ish string for sorting.

    Returns a (sort_key, original) tuple where sort_key is an integer epoch seconds if
    parsing succeeds, else a large fallback to keep unknowns at the end while being
    stable.
    """
    s = s.strip()
    if not s:
        return (2**63 - 1, s)
    # Try a few common formats; keep robust and lenient
    fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            return (int(dt.timestamp()), s)
        except Exception:
            pass
    # Last resort: attempt fromisoformat (Python 3.12 handles many forms)
    try:
        dt = datetime.fromisoformat(s)
        return (int(dt.timestamp()), s)
    except Exception:
        return (2**63 - 1, s)


def _sanitize_filename(s: str) -> str:
    # Remove filesystem-unfriendly characters
    bad = '<>:"/\\|?*'  # noqa: W605
    out = "".join((c if c not in bad else "_") for c in s)
    out = out.strip().rstrip(".")
    return out or "untitled"


def _chapter_order_key(chapter: str, rows: List[Row]) -> Tuple[int, str]:
    # Order chapters by earliest DateCreated in that chapter; fallback to name
    if not rows:
        return (2**63 - 1, chapter)
    earliest = min(_parse_dt(r.DateCreated)[0] for r in rows)
    return (earliest, chapter)


def _render_book_md(title: str, author: str, rows: List[Row]) -> str:
    # Group by chapter
    by_chapter: Dict[str, List[Row]] = defaultdict(list)
    for r in rows:
        ch = r.ChapterTitle or "Untitled"
        by_chapter[ch].append(r)

    # Sort chapters by earliest highlight date
    chapter_items = sorted(
        by_chapter.items(), key=lambda kv: _chapter_order_key(kv[0], kv[1])
    )

    total = len(rows)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"by {author}")
    lines.append("")
    lines.append(f"Total highlights: {total}")
    lines.append(f"Generated: {generated}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for chapter, ch_rows in chapter_items:
        # Sort rows by DateCreated within chapter
        ch_rows_sorted = sorted(ch_rows, key=lambda r: _parse_dt(r.DateCreated)[0])
        lines.append(f"## {chapter}")
        lines.append("")
        for r in ch_rows_sorted:
            meta_bits: List[str] = []
            dc = _norm(r.DateCreated)
            if dc:
                meta_bits.append(dc)
            col = _norm(r.Color)
            if col:
                meta_bits.append(col)
            typ = _norm(r.Type)
            if typ:
                meta_bits.append(f"type {typ}")
            meta_line = " • ".join(meta_bits)

            lines.append(f"- {meta_line}" if meta_line else "-")
            # Highlight text as a blockquote if present
            txt = _norm(r.Text)
            if txt:
                lines.append("")
                for ln in txt.splitlines():
                    lines.append(f"> {_wrap_with_color(ln, col)}")
            # Annotation as a Note
            ann = _norm(r.Annotation)
            if ann:
                if not txt:
                    lines.append("")
                lines.append("")
                lines.append(f"  Note: {ann}")
            lines.append("")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_markdown_from_csv(csv_path: str, out_dir: str) -> int:
    """Create Markdown files in out_dir grouped as Author/Title.md.

    Returns the number of Markdown files written.
    """
    in_path = Path(csv_path)
    if not in_path.is_file():
        raise FileNotFoundError(f"CSV not found: {in_path}")
    base_out = Path(out_dir)
    base_out.mkdir(parents=True, exist_ok=True)

    # Group rows by (author, title)
    groups: Dict[Tuple[str, str], List[Row]] = defaultdict(list)

    with in_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for d in reader:
            row = Row(
                BookmarkID=_norm(d.get("BookmarkID")),
                BookTitle=_norm(d.get("BookTitle", "Unknown Title"), "Unknown Title"),
                Author=_norm(d.get("Author", "Unknown Author"), "Unknown Author"),
                ChapterTitle=_norm(d.get("ChapterTitle", "")),
                DateCreated=_norm(d.get("DateCreated", "")),
                DateModified=_norm(d.get("DateModified", "")),
                Color=_norm(d.get("Color", "")),
                Text=_norm(d.get("Text", "")),
                Annotation=_norm(d.get("Annotation", "")),
                Type=_norm(d.get("Type", "")),
            )
            groups[
                (row.Author or "Unknown Author", row.BookTitle or "Unknown Title")
            ].append(row)

    written = 0
    for (author, title), rows in groups.items():
        # Directory: out/Author; File: Title.md
        author_dir = base_out / _sanitize_filename(author or "Unknown Author")
        author_dir.mkdir(parents=True, exist_ok=True)
        file_path = author_dir / f"{_sanitize_filename(title or 'Unknown Title')}.md"
        content = _render_book_md(
            title or "Unknown Title", author or "Unknown Author", rows
        )
        file_path.write_text(content, encoding="utf-8")
        written += 1

    return written
