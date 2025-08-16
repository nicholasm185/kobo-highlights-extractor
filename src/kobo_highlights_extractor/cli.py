from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
import tempfile

from .exporter import export_highlights
from .md_exporter import export_markdown_from_csv


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kobo-highlights-extractor",
        description="Export Kobo highlights and notes to CSV with book metadata.",
    )
    p.add_argument(
        "--db",
        dest="db_path",
        default="KoboReader.sqlite",
        help="Path to KoboReader.sqlite (default: %(default)s)",
    )
    p.add_argument(
        "--out",
        dest="out_csv",
        default=None,
        help=(
            "Output CSV file. If omitted, a temporary CSV is used and deleted automatically."
        ),
    )
    p.add_argument(
        "--md-dir",
        dest="md_dir",
        default="notes",
        help=(
            "Directory to write Markdown notes grouped by book (default: %(default)s). "
            "Output structure: <md_dir>/<Author>/<Title>.md"
        ),
    )
    p.add_argument(
        "--keep-filename-chapter",
        dest="suppress_filename",
        action="store_false",
        help="Keep chapter titles that look like filenames (default is to suppress)",
    )
    p.add_argument(
        "--log-level",
        dest="log_level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Logging level (default: %(default)s)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s: %(message)s",
    )
    log = logging.getLogger(__name__)
    # Require an explicit, existing database path
    selected_db = Path(args.db_path).expanduser()
    if not selected_db.is_file():
        log.error(
            "Database file not found: %s. Specify a valid path with --db.", selected_db
        )
        return 2

    log.info("Using DB: %s", selected_db)
    provided_csv = args.out_csv is not None and str(args.out_csv).strip() != ""
    if provided_csv:
        out_path = Path(args.out_csv).resolve()
        count = export_highlights(
            db_path=str(selected_db),
            out_csv=str(out_path),
            suppress_filename_chapter_titles=args.suppress_filename,
        )
        log.info("Wrote %d rows to %s", count, out_path)
        md_base = Path(args.md_dir).expanduser() if args.md_dir else None
        if md_base:
            files = export_markdown_from_csv(str(out_path), str(md_base))
            log.info("Rendered %d Markdown files under %s", files, md_base.resolve())
    else:
        # Use a temporary CSV that will be removed automatically
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_csv = Path(tmpdir) / "highlights_enriched.csv"
            count = export_highlights(
                db_path=str(selected_db),
                out_csv=str(tmp_csv),
                suppress_filename_chapter_titles=args.suppress_filename,
            )
            # Default to Markdown output directory
            md_base = Path(args.md_dir).expanduser() if args.md_dir else None
            if md_base:
                files = export_markdown_from_csv(str(tmp_csv), str(md_base))
                log.info(
                    "Rendered %d Markdown files under %s", files, md_base.resolve()
                )
            else:
                log.info("Wrote %d rows (temporary CSV used)", count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
