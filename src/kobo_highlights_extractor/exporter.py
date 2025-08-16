"""
Core export logic for Kobo highlights.

Public API:
- export_highlights(db_path: str = "KoboReader.sqlite", out_csv: str = "highlights_enriched.csv",
                   suppress_filename_chapter_titles: bool = True) -> int
  Returns number of data rows written (excludes header).
"""

from __future__ import annotations

import csv
import logging
import os
import re
import sqlite3
from typing import Any, Dict, Tuple, Optional, TypedDict, Final, List
from urllib.parse import urlparse, unquote

__all__ = ["export_highlights"]

from .chapter_title import (
    determine_chapter_title,
    _clean_title,
    _p_anchor,
    _tail_after_bang_bang_no_fragment,
)

log = logging.getLogger(__name__)


# Module-level constants
COLOR_MAP: Final[dict[int, str]] = {0: "yellow", 1: "pink", 2: "blue", 3: "green"}

OUT_FIELDS: Final[tuple[str, ...]] = (
    "BookmarkID",
    "BookTitle",
    "Author",
    "ChapterTitle",
    "DateCreated",
    "DateModified",
    "Color",
    "Text",
    "Annotation",
    "Type",
)


class BookmarkRow(TypedDict, total=False):
    BookmarkID: str
    VolumeID: Optional[str]
    ContentID: Optional[str]
    DateCreated: Optional[str]
    DateModified: Optional[str]
    ChapterProgress: Optional[float]
    Color: Optional[str]
    Hidden: Optional[int]
    Text: Optional[str]
    Annotation: Optional[str]
    UUID: Optional[str]
    UserID: Optional[str]
    SyncTime: Optional[str]
    ContextString: Optional[str]
    Type: Optional[int]


class CsvRow(TypedDict, total=False):
    BookmarkID: str
    BookTitle: Optional[str]
    Author: Optional[str]
    ChapterTitle: Optional[str]
    VolumeID: Optional[str]
    ContentID: Optional[str]
    DateCreated: Optional[str]
    DateModified: Optional[str]
    ChapterProgress: Optional[float]
    Hidden: Optional[int]
    Text: Optional[str]
    Annotation: Optional[str]
    UUID: Optional[str]
    UserID: Optional[str]
    SyncTime: Optional[str]
    ContextString: Optional[str]
    Type: Optional[int]
    HtmlOpen: Optional[str]
    HtmlClose: Optional[str]


def _strip_after_bang_bang(content_id: Optional[str]) -> Optional[str]:
    if not content_id:
        return content_id
    idx = content_id.find("!!")
    return content_id[:idx] if idx != -1 else content_id


def _fragment_base(content_id: Optional[str]) -> Optional[str]:
    """Return the base of a ContentID up to the start of any hyphen after the fragment.

    Example:
      '/path/file.xhtml#p80-2' -> '/path/file.xhtml#p80'
      '/path/file.xhtml#p80'   -> '/path/file.xhtml#p80'
      '/path/file.xhtml'       -> None
    """
    if not content_id or "#" not in content_id:
        return None
    pre, frag = content_id.split("#", 1)
    frag_main = frag.split("-", 1)[0]
    return f"{pre}#{frag_main}"


def _pre_bang(content_id: Optional[str]) -> Optional[str]:
    """Return the path before any Kobo '!!' segment, keeping the path and optional fragment.

    Example:
      '/a/book.kepub.epub!!index_split_000.html#p40-2' -> '/a/book.kepub.epub'
      '/a/ch.xhtml#p3-1' -> '/a/ch.xhtml#p3' (no '!!', keep fragment base)
    """
    if not content_id:
        return None
    if "!!" in content_id:
        return content_id.split("!!", 1)[0]
    # If no '!!', try to normalize to fragment base
    return _fragment_base(content_id) or content_id


def _normalize_id(s: Optional[str]) -> Optional[str]:
    return unquote(s) if isinstance(s, str) else None


def _strip_fragment(content_id: Optional[str]) -> Optional[str]:
    """Strip any fragment (e.g., '#p123') from a ContentID-like string.

    Bookmark.ContentID often includes an anchor (e.g., '#p96'). The corresponding
    row in the 'content' table typically omits the fragment. Removing it greatly
    improves lookup success for chapter titles.
    """
    if not content_id:
        return content_id
    idx = content_id.find("#")
    return content_id[:idx] if idx != -1 else content_id


def _as_opt_float(v: Any) -> Optional[float]:
    """Best-effort convert a value into Optional[float].

    Accepts int/float directly, parses str (empty -> None), otherwise None.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None
    return None


def _as_opt_int(v: Any) -> Optional[int]:
    """Best-effort convert a value into Optional[int].

    Accepts int directly, truncates float, parses str digits, else None.
    """
    if v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        try:
            return int(v)
        except Exception:
            return None
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            try:
                return int(s)
            except Exception:
                return None
    return None


def _parse_from_volume_id(vol_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort parse of title and author from the VolumeID file path."""
    if not vol_id:
        return None, None
    try:
        path = unquote(urlparse(vol_id).path)
        filename = os.path.basename(path)
        author_dir = os.path.basename(os.path.dirname(path)) or None
        base = re.sub(r"\.(kepub\.)?epub$", "", filename, flags=re.IGNORECASE)
        # Common Kobo filename pattern: "<Title> - <Author>"
        if " - " in base:
            title_guess, author_guess = base.split(" - ", 1)
            title_guess = title_guess.strip() or None
            author_guess = author_guess.strip() or None
        else:
            title_guess, author_guess = (base or None), author_dir
        return title_guess, author_guess
    except Exception:
        return None, None


def export_highlights(
    db_path: str = "KoboReader.sqlite",
    out_csv: str = "highlights_enriched.csv",
    suppress_filename_chapter_titles: bool = True,
) -> int:
    # Open DB in immutable read-only mode to avoid creating sidecar WAL/SHM files.
    # Fall back to plain read-only if the runtime SQLite lacks immutable support.
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    except sqlite3.OperationalError:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Load minimal content metadata into memory for quick lookup
    content_by_id: Dict[str, Dict[str, Any]] = {}
    content_by_url: Dict[str, Dict[str, Any]] = {}
    content_by_frag_base: Dict[str, list[Dict[str, Any]]] = {}
    content_by_pre_bang: Dict[str, list[Dict[str, Any]]] = {}
    content_by_book: Dict[str, list[Dict[str, Any]]] = {}
    content_by_tail: Dict[str, list[Dict[str, Any]]] = {}
    content_by_p_anchor: Dict[str, list[Dict[str, Any]]] = {}
    content_by_id_norm: Dict[str, Dict[str, Any]] = {}
    content_by_url_norm: Dict[str, Dict[str, Any]] = {}

    try:
        for row in cur.execute(
            "SELECT ContentID, BookID, BookTitle, Title, Attribution, ContentURL FROM content"
        ):
            d: Dict[str, Any] = dict(row)
            content_by_id[d["ContentID"]] = d
            nid = _normalize_id(d.get("ContentID"))
            if nid:
                content_by_id_norm.setdefault(nid, d)
            url = d.get("ContentURL")
            if url:
                content_by_url[url] = d
                nurl = _normalize_id(url)
                if nurl:
                    content_by_url_norm.setdefault(nurl, d)
            fb = _fragment_base(d.get("ContentID"))
            if fb:
                content_by_frag_base.setdefault(fb, []).append(d)
            pb = _pre_bang(d.get("ContentID"))
            if pb:
                content_by_pre_bang.setdefault(pb, []).append(d)
            tail = _tail_after_bang_bang_no_fragment(d.get("ContentID"))
            if tail:
                content_by_tail.setdefault(tail, []).append(d)
            pa = _p_anchor(d.get("ContentID"))
            if pa:
                content_by_p_anchor.setdefault(pa, []).append(d)
            bid = d.get("BookID")
            if isinstance(bid, str):
                content_by_book.setdefault(bid, []).append(d)
    except sqlite3.DatabaseError:
        log.exception("Error reading content table")

    # Fetch highlights/notes
    rows_db = cur.execute(
        """
        SELECT BookmarkID, VolumeID, ContentID, DateCreated, DateModified,
               ChapterProgress, Color, Hidden, Text, Annotation, UUID, UserID,
               SyncTime, ContextString, Type
        FROM Bookmark
        WHERE ((Text IS NOT NULL AND TRIM(Text)!='')
           OR (Annotation IS NOT NULL AND TRIM(Annotation)!=''))
          AND (
            CASE
              WHEN Hidden IS NULL THEN 1
              WHEN typeof(Hidden)='integer' THEN CASE WHEN Hidden=0 THEN 1 ELSE 0 END
              WHEN typeof(Hidden)='real' THEN CASE WHEN Hidden=0.0 THEN 1 ELSE 0 END
              WHEN typeof(Hidden)='text' THEN CASE
                   WHEN lower(Hidden) IN ('false','0','no','n') THEN 1
                   WHEN trim(Hidden)='' THEN 1
                   ELSE 0
                 END
              ELSE 1
            END
          )=1
        ORDER BY DateCreated
        """
    ).fetchall()

    # Materialize typed bookmark rows for clarity
    rows: List[BookmarkRow] = []
    for rr in rows_db:
        drr = dict(rr)
        rows.append(
            BookmarkRow(
                BookmarkID=str(drr.get("BookmarkID")),
                VolumeID=drr.get("VolumeID"),
                ContentID=drr.get("ContentID"),
                DateCreated=drr.get("DateCreated"),
                DateModified=drr.get("DateModified"),
                ChapterProgress=_as_opt_float(drr.get("ChapterProgress")),
                Color=drr.get("Color"),
                Hidden=_as_opt_int(drr.get("Hidden")),
                Text=drr.get("Text"),
                Annotation=drr.get("Annotation"),
                UUID=drr.get("UUID"),
                UserID=drr.get("UserID"),
                SyncTime=drr.get("SyncTime"),
                ContextString=drr.get("ContextString"),
                Type=_as_opt_int(drr.get("Type")),
            )
        )

    # Using module-level OUT_FIELDS

    written = 0
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(OUT_FIELDS))
        w.writeheader()
        for r in rows:
            r = dict(r)
            vol_id_val = r.get("VolumeID")
            vol_id: Optional[str] = vol_id_val if isinstance(vol_id_val, str) else None
            cont_id_val = r.get("ContentID")
            cont_id: Optional[str] = (
                cont_id_val if isinstance(cont_id_val, str) else None
            )
            base_cont_id = _strip_after_bang_bang(cont_id)
            cont_id_no_frag = _strip_fragment(cont_id)
            frag_base = _fragment_base(cont_id)
            pre_bang = _pre_bang(cont_id)

            # Resolve chapter row: try exact/normalized ContentID, then without fragment,
            # then URL-based lookups as a last resort.
            ch_row: Dict[str, Any] | None = (
                content_by_id.get(cont_id) if cont_id else None
            )
            if not ch_row and cont_id:
                ch_row = content_by_id_norm.get(_normalize_id(cont_id) or "")
            if not ch_row and cont_id_no_frag:
                ch_row = content_by_id.get(cont_id_no_frag)
            if not ch_row and cont_id_no_frag:
                ch_row = content_by_id_norm.get(_normalize_id(cont_id_no_frag) or "")
            if not ch_row and cont_id:
                ch_row = content_by_url.get(cont_id)
            if not ch_row and cont_id_no_frag:
                ch_row = content_by_url.get(cont_id_no_frag)
            if not ch_row and cont_id:
                ch_row = content_by_url_norm.get(_normalize_id(cont_id) or "")
            if not ch_row and cont_id_no_frag:
                ch_row = content_by_url_norm.get(_normalize_id(cont_id_no_frag) or "")
            ch_title = determine_chapter_title(
                r,
                ch_row,
                cont_id=cont_id,
                cont_id_no_frag=cont_id_no_frag,
                frag_base=frag_base,
                pre_bang=pre_bang,
                content_by_frag_base=content_by_frag_base,
                content_by_pre_bang=content_by_pre_bang,
                content_by_p_anchor=content_by_p_anchor,
                content_by_tail=content_by_tail,
                suppress_filename_like=suppress_filename_chapter_titles,
            )

            # Candidate book rows in order of preference
            candidates = []
            if vol_id:
                candidates.append(content_by_id.get(vol_id))
                candidates.append(content_by_url.get(vol_id))
            if ch_row:
                book_id_val = ch_row.get("BookID")
                if isinstance(book_id_val, str):
                    candidates.append(content_by_id.get(book_id_val))
            if base_cont_id:
                candidates.append(content_by_id.get(base_cont_id))
                candidates.append(content_by_url.get(base_cont_id))

            book_row = next((c for c in candidates if c), None)

            book_title = None
            author = None
            if book_row:
                book_title = _clean_title(book_row.get("BookTitle")) or _clean_title(
                    book_row.get("Title")
                )
                author = (book_row.get("Attribution") or "").strip() or None

            # Fallback to parsing from VolumeID
            if not book_title or not author:
                t_guess, a_guess = _parse_from_volume_id(vol_id)
                if not book_title:
                    book_title = _clean_title(t_guess)
                if not author:
                    author = a_guess

            # Map color codes 0-3 to names
            color_val = r.get("Color")
            color_name = None
            if isinstance(color_val, (int, float)):
                try:
                    idx = int(color_val)
                except Exception:
                    idx = None
            elif isinstance(color_val, str) and color_val.strip().isdigit():
                idx = int(color_val.strip())
            else:
                idx = None
            if idx is not None:
                color_name = COLOR_MAP.get(idx)
            w.writerow(
                {
                    "BookmarkID": r.get("BookmarkID"),
                    "BookTitle": book_title or "",
                    "Author": author or "",
                    "ChapterTitle": ch_title or "",
                    "DateCreated": r.get("DateCreated"),
                    "DateModified": r.get("DateModified"),
                    "Color": color_name or "",
                    "Text": r.get("Text"),
                    "Annotation": r.get("Annotation"),
                    "Type": r.get("Type"),
                }
            )
            written += 1

    con.close()
    return written
