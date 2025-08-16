from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .exporter import export_highlights


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
        default="highlights_enriched.csv",
        help="Output CSV file (default: %(default)s)",
    )
    p.add_argument(
        "--keep-filename-chapter",
        dest="suppress_filename",
        action="store_false",
        help="Keep chapter titles that look like filenames (default is to suppress)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)
    count = export_highlights(
        db_path=args.db_path,
        out_csv=args.out_csv,
        suppress_filename_chapter_titles=args.suppress_filename,
    )
    out_path = Path(args.out_csv).resolve()
    print(f"Wrote {count} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
