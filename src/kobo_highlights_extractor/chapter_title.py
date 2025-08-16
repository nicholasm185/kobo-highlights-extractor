"""
Chapter title extraction helpers for Kobo highlights.

Public API:
- determine_chapter_title(...): compute a cleaned chapter title for a bookmark row

This module centralizes the heuristics for deriving a chapter title from the
available data (content rows, context strings, and ContentID forms).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, unquote

__all__ = [
    "determine_chapter_title",
    "_clean_title",
    "_is_generic_chapter_title",
    "_p_anchor",
    "_tail_after_bang_bang_no_fragment",
    "_fallback_title_from_content_id",
    "_title_from_context",
]


def _tail_after_bang_bang_no_fragment(content_id: Optional[str]) -> Optional[str]:
    """Return the tail path after '!!' (or first '!' if no '!!') with no fragment, unquoted.

    Examples:
      '/a/book!!OEBPS!xhtml/chap6.xhtml#p1-2' -> 'OEBPS!xhtml/chap6.xhtml'
      'uuid!OEBPS!xhtml/chap6.xhtml#p1-2'     -> 'OEBPS!xhtml/chap6.xhtml'
    """
    if not content_id:
        return None
    tail = None
    if "!!" in content_id:
        tail = content_id.split("!!", 1)[1]
    elif "!" in content_id:
        tail = content_id.split("!", 1)[1]
    if tail is None:
        return None
    tail = tail.split("#", 1)[0]
    return unquote(tail)


def _p_anchor(content_id: Optional[str]) -> Optional[str]:
    """Extract the 'pNNN' anchor id from a ContentID (fragment), if present.

    Examples:
      '/path#p167-2' -> 'p167'
      '/path#p40'    -> 'p40'
    """
    if not content_id or "#" not in content_id:
        return None
    frag = content_id.split("#", 1)[1]
    base = frag.split("-", 1)[0]
    return base if base.startswith("p") else None


def _fallback_title_from_content_id(content_id: Optional[str]) -> Optional[str]:
    """Derive a readable title from the content file name when no Title exists.

    Example: "/mnt/.../index_split_000.html" -> "index split 000"
    """
    if not content_id:
        return None
    try:
        path = unquote(urlparse(content_id).path)
        # Prefer the Kobo tail after '!!' or '!' (and without fragment), else use path
        tail = _tail_after_bang_bang_no_fragment(content_id) or path
        # Get the last component after either '!' or '/'
        base = re.split(r"[!/]+", tail)[-1] if tail else ""
        # Remove any fragment safety (shouldn't be present) and file extension
        base = base.split("#", 1)[0]
        base = re.sub(r"\.(x?html?)$", "", base, flags=re.IGNORECASE)
        # Normalize separators to spaces, collapse whitespace
        name = re.sub(r"[_\-]+", " ", base)
        name = re.sub(r"\s+", " ", name).strip()

        # 1) Strong label + number patterns covering common cases
        # chapter/ch/chap N
        m = re.fullmatch(r"(?i)(?:ch|chap|chapter)\s*0*(\d{1,5})", name)
        if m:
            return f"Chapter {int(m.group(1))}"
        # part N
        m = re.fullmatch(r"(?i)part\s*0*(\d{1,5})", name)
        if m:
            return f"Part {int(m.group(1))}"
        # preface N (or no number)
        m = re.fullmatch(r"(?i)preface(?:\s*0*(\d{1,5}))?", name)
        if m:
            num = m.group(1)
            return f"Preface {int(num)}" if num else "Preface"
        # prologue / epilogue (optional number)
        m = re.fullmatch(r"(?i)prolog(?:ue)?(?:\s*0*(\d{1,5}))?", name)
        if m:
            num = m.group(1)
            return f"Prologue {int(num)}" if num else "Prologue"
        m = re.fullmatch(r"(?i)epilog(?:ue)?(?:\s*0*(\d{1,5}))?", name)
        if m:
            num = m.group(1)
            return f"Epilogue {int(num)}" if num else "Epilogue"
        # appendix (letter/roman/number optional)
        m = re.fullmatch(r"(?i)appendix(?:\s+([A-Z]|[IVXLCDM]{1,8}|\d{1,3}))?", name)
        if m:
            suf = m.group(1)
            return f"Appendix {suf}" if suf else "Appendix"
        # introduction/foreword/afterword/conclusion (optional number)
        m = re.fullmatch(r"(?i)intro(?:duction)?(?:\s*0*(\d{1,5}))?", name)
        if m:
            num = m.group(1)
            return f"Introduction {int(num)}" if num else "Introduction"
        m = re.fullmatch(r"(?i)foreword(?:\s*0*(\d{1,5}))?", name)
        if m:
            num = m.group(1)
            return f"Foreword {int(num)}" if num else "Foreword"
        m = re.fullmatch(r"(?i)afterword(?:\s*0*(\d{1,5}))?", name)
        if m:
            num = m.group(1)
            return f"Afterword {int(num)}" if num else "Afterword"

        # 2) If basename includes labels with numbers after noise (e.g., '978... EPUB 8')
        m = re.search(r"(?i)\bchapter\s*0*(\d{1,5})\b", name)
        if m:
            return f"Chapter {int(m.group(1))}"
        m = re.search(r"(?i)\bpart\s*0*(\d{1,5})\b", name)
        if m:
            return f"Part {int(m.group(1))}"
        m = re.search(r"(?i)\bepub\s*0*(\d{1,5})\b", name)
        if m:
            return f"EPUB {int(m.group(1))}"

        # 3) As a last resort return the cleaned name
        return name or None
    except Exception:
        return None


def _title_from_context(context: Optional[str]) -> Optional[str]:
    """Try to extract a human-friendly chapter title from Bookmark.ContextString.

    Heuristics:
    - 'Chapter 4: ...' or 'Part II - ...'
    - Numbered headings like '7. How ...'
    - Common section names like 'Introduction', 'Preface', 'Epilogue', 'Appendix A'
    """
    if not context:
        return None
    ctx = context.strip()
    if not ctx:
        return None

    # Consider the first few non-empty lines; headings are often at the beginning.
    head = ctx[:400]
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]

    # 1) Chapter/Part with optional title
    for ln in lines[:3]:
        m = re.search(
            r"\b(Chapter|Part)\s+([0-9]{1,3}|[IVXLCDM]{1,8})(?:\s*[:\-–—]\s*([^\n]{1,80}))?",
            ln,
            re.I,
        )
        if m:
            kind = m.group(1).title()
            num = m.group(2)
            rest = (m.group(3) or "").strip()
            if rest:
                return f"{kind} {num}: {rest}"
            return f"{kind} {num}"

    # 2) Numbered headings like '7. How ...' or 'VII - Title'
    for ln in lines[:3]:
        m = re.match(
            r"^(?:([0-9]{1,3}|[IVXLCDM]{1,8})\s*[\.\-:–—]\s*)([^\n]{1,80})$",
            ln,
            re.I,
        )
        if m:
            num = m.group(1)
            rest = (m.group(2) or "").strip()
            # Prefer a generic heading label to avoid misreading list items
            if rest:
                return f"Section {num}: {rest}"

    # 3) Common section names as standalone titles
    common = [
        r"Introduction",
        r"Preface",
        r"Prologue",
        r"Epilogue",
        r"Foreword",
        r"Afterword",
        r"Conclusion",
        r"Acknowledg?ments",
        r"Appendix(?:\s+[A-Z]|\s+[IVXLCDM]{1,8}|\s+\d{1,3})?",
    ]
    for ln in lines[:3]:
        for pat in common:
            if re.fullmatch(pat, ln, re.I):
                return ln

    # 4) Fallback: search the entire context for Chapter/Part patterns
    m = re.search(
        r"\b(Chapter|Part)\s+([0-9]{1,3}|[IVXLCDM]{1,8})(?:\s*[:\-–—]\s*([^\n]{1,80}))?",
        ctx,
        re.I,
    )
    if m:
        kind = m.group(1).title()
        num = m.group(2)
        rest = (m.group(3) or "").strip()
        if rest:
            return f"{kind} {num}: {rest}"
        return f"{kind} {num}"
    return None


def _basename_no_ext(tail: Optional[str]) -> str:
    if not tail:
        return ""
    # tail may contain '!' as separators inside the epub container path
    parts = re.split(r"[!/]+", tail)
    base = parts[-1] if parts else tail
    base = re.sub(r"\.(x?html?)$", "", base, flags=re.IGNORECASE)
    return base


def _extract_numbers(s: str) -> List[int]:
    return [int(m) for m in re.findall(r"\d{1,6}", s)]


def _split_dirs(tail: Optional[str]) -> List[str]:
    if not tail:
        return []
    return [seg for seg in re.split(r"[!/]+", tail) if seg]


def _score_tail_similarity(cur_tail: Optional[str], cand_tail: Optional[str]) -> int:
    if not cand_tail:
        return 0
    score = 0
    cur_tail = cur_tail or ""
    if cand_tail == cur_tail:
        score += 100
    cur_base = _basename_no_ext(cur_tail)
    cand_base = _basename_no_ext(cand_tail)
    if cur_base and cand_base and cur_base == cand_base:
        score += 80
    # Numeric closeness
    cur_nums = _extract_numbers(cur_base)
    cand_nums = _extract_numbers(cand_base)
    if cur_nums and cand_nums:
        diff = abs(cur_nums[0] - cand_nums[0])
        score += max(0, 50 - min(diff, 50))
    # Directory depth commonality
    cur_dirs = _split_dirs(cur_tail)
    cand_dirs = _split_dirs(cand_tail)
    if cur_dirs and cand_dirs:
        # length of shared prefix
        common = 0
        for a, b in zip(cur_dirs, cand_dirs):
            if a == b:
                common += 1
            else:
                break
        score += min(common * 5, 20)
    return score


def _is_generic_chapter_title(val: Optional[str]) -> bool:
    if not val:
        return True
    stripped = val.strip()
    lowered = stripped.lower()
    # HTML-ish filenames (also covered elsewhere but keep centralized)
    if lowered.endswith((".xhtml", ".html", ".htm")):
        return True
    # ContentID artifacts or package paths
    if "!oebps!" in lowered or "!!" in stripped:
        return True
    # Common split names
    if "index_split" in lowered or "index split" in lowered:
        return True
    # Generic kepub split patterns like 'part0007 split 004' or 'split 004'
    if re.search(r"\bpart\d{1,5}\s*(?:_|\s)?split\s*\d{1,5}\b", lowered):
        return True
    if re.search(r"\bsplit[_ ]?\d{1,5}\b", lowered):
        return True
    # ISBN-like numeric prefixes followed by generic words (Chapter, EPUB, Page, Section, Part)
    if re.match(r"^\d{10,13}\s+(?:chapter|epub|page|section|part)\b", lowered, re.I):
        return True
    # Chapter plus zero-padded number without space (e.g., chapter006)
    if re.match(r"^chapter\d{2,}\b", lowered, re.I):
        return True
    # Abbreviated chapter markers like "ch02", "ch3"
    if re.match(r"^ch\d{1,3}\b", lowered, re.I):
        return True
    # Very short markers like "f 0047" / "p 0123"
    if re.match(r"^[a-zA-Z]\s?\d{3,4}$", stripped):
        return True
    return False


def _clean_title(
    val: Optional[str], suppress_filename_like: bool = True
) -> Optional[str]:
    if not val:
        return None
    v = val.strip()
    if not v:
        return None
    if suppress_filename_like and _is_generic_chapter_title(v):
        return None
    return v


def determine_chapter_title(
    r: Dict[str, Any],
    ch_row: Optional[Dict[str, Any]],
    *,
    cont_id: Optional[str],
    cont_id_no_frag: Optional[str],
    frag_base: Optional[str],
    pre_bang: Optional[str],
    content_by_frag_base: Dict[str, List[Dict[str, Any]]],
    content_by_pre_bang: Dict[str, List[Dict[str, Any]]],
    content_by_p_anchor: Dict[str, List[Dict[str, Any]]],
    content_by_tail: Dict[str, List[Dict[str, Any]]],
    suppress_filename_like: bool = True,
) -> Optional[str]:
    """Compute a cleaned chapter title for a bookmark row using several heuristics.

    This mirrors the logic previously embedded in exporter.export_highlights.
    """
    ch_title = _clean_title(
        ch_row.get("Title") if ch_row else None,
        suppress_filename_like=suppress_filename_like,
    )

    # Try extracting title from ContextString (often contains chapter headings)
    if not ch_title:
        _ctx_val = r.get("ContextString")
        _ctx_str: Optional[str] = _ctx_val if isinstance(_ctx_val, str) else None
        ctx_title = _title_from_context(_ctx_str)
        if ctx_title:
            ch_title = _clean_title(
                ctx_title,
                suppress_filename_like=suppress_filename_like,
            )

    # If missing or generic, try any rows that share the same fragment base
    if (not ch_title) and frag_base:
        cand_rows = content_by_frag_base.get(frag_base) or []
        cur_tail = _tail_after_bang_bang_no_fragment(cont_id)
        best_fb: Tuple[int, int, str] = (-1, -1, "")  # (score, length, title)
        for cr in cand_rows:
            t = _clean_title(
                cr.get("Title"), suppress_filename_like=suppress_filename_like
            )
            if not t or t.lower() == "table of contents":
                continue
            cand_tail = _tail_after_bang_bang_no_fragment(cr.get("ContentID"))
            score = _score_tail_similarity(cur_tail, cand_tail)
            tup = (score, len(t), t)
            if tup > best_fb:
                best_fb = tup
        if best_fb[2]:
            ch_title = best_fb[2]

    # If still missing, try exact tail (same file path) to avoid collapsing to one chapter
    if not ch_title:
        tail = _tail_after_bang_bang_no_fragment(cont_id)
        if tail:
            cand_rows = content_by_tail.get(tail) or []
            best_title = None
            best_len = -1
            for cr in cand_rows:
                t = _clean_title(
                    cr.get("Title"), suppress_filename_like=suppress_filename_like
                )
                if t and t.lower() != "table of contents":
                    L = len(t)
                    if L > best_len:
                        best_len = L
                        best_title = t
            if best_title:
                ch_title = best_title

    # If still missing, try rows that share the same 'pNNN' anchor across formats, scored
    if not ch_title:
        pa = _p_anchor(cont_id)
        if pa:
            cand_rows = content_by_p_anchor.get(pa) or []
            cur_tail = _tail_after_bang_bang_no_fragment(cont_id)
            best_pa: Tuple[int, int, str] = (-1, -1, "")  # (score, length, title)
            for cr in cand_rows:
                t = _clean_title(
                    cr.get("Title"), suppress_filename_like=suppress_filename_like
                )
                if not t or t.lower() == "table of contents":
                    continue
                cand_tail = _tail_after_bang_bang_no_fragment(cr.get("ContentID"))
                score = _score_tail_similarity(cur_tail, cand_tail)
                tup = (score, len(t), t)
                if tup > best_pa:
                    best_pa = tup
            if best_pa[2]:
                ch_title = best_pa[2]

    # If still missing, try sibling tails with '-N' suffix (common ToC mapping to chapter entry)
    if not ch_title:
        tail = _tail_after_bang_bang_no_fragment(cont_id)
        if tail:
            for n in (1, 2, 3, 4, 5):
                alt_tail = f"{tail}-{n}"
                cand_rows = content_by_tail.get(alt_tail) or []
                best_title = None
                best_key = (-1, -1, "")  # (depth, length, title)
                for cr in cand_rows:
                    t = _clean_title(
                        cr.get("Title"), suppress_filename_like=suppress_filename_like
                    )
                    if not t or t.lower() == "table of contents":
                        continue
                    depth_raw = cr.get("Depth")
                    try:
                        depth = int(depth_raw) if depth_raw is not None else 0
                    except Exception:
                        depth = 0
                    tup = (depth, len(t), t)
                    if tup > best_key:
                        best_key = tup
                        best_title = t
                if best_title:
                    ch_title = best_title
                    break

    # If still missing, try rows with same pre-bang (same book file), prefer non-generic
    if (not ch_title) and pre_bang:
        cand_rows = content_by_pre_bang.get(pre_bang) or []
        cur_tail = _tail_after_bang_bang_no_fragment(cont_id)
        best: Tuple[int, int, str] = (-1, -1, "")  # (score, length, title)
        for cr in cand_rows:
            t = _clean_title(
                cr.get("Title"), suppress_filename_like=suppress_filename_like
            )
            if not t or t.lower() == "table of contents":
                continue
            cand_tail = _tail_after_bang_bang_no_fragment(cr.get("ContentID"))
            score = _score_tail_similarity(cur_tail, cand_tail)
            tup = (score, len(t), t)
            if tup > best:
                best = tup
        if best[2]:
            ch_title = best[2]

    # Final fallback: derive something from content id
    if not ch_title:
        ch_title = _fallback_title_from_content_id(cont_id_no_frag or cont_id)
        ch_title = _clean_title(ch_title, suppress_filename_like=suppress_filename_like)

    return ch_title
