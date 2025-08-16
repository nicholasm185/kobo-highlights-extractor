from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .exporter import export_highlights
from .detect import find_kobo_sqlite_paths, choose_best_kobo_sqlite


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
    p.add_argument(
        "--detect-db",
        dest="detect_db",
        action="store_true",
        help=(
            "Scan common mount points (USB) to locate .kobo/KoboReader.sqlite. "
            "Also used automatically if --db path is not found."
        ),
    )
    p.add_argument(
        "-i",
        "--interactive",
        dest="interactive",
        action="store_true",
        help=(
            "Interactive mode: choose among detected databases or enter a path manually"
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)
    # Resolve DB path: use provided path if it exists; otherwise (or if --detect-db),
    # attempt to find the database under common USB mount points.
    selected_db = Path(args.db_path)
    need_detect = args.detect_db or not selected_db.is_file()
    if need_detect:
        candidates = find_kobo_sqlite_paths()
        if args.interactive:
            # Interactive selection or manual entry
            while True:
                if not candidates:
                    print(
                        "No Kobo databases detected on mounted drives.",
                        file=sys.stderr,
                    )
                    manual = input(
                        "Enter path to KoboReader.sqlite (or 'q' to quit): "
                    ).strip()
                    if manual.lower() in {"q", "quit", "exit"}:
                        return 2
                    mp = Path(manual).expanduser()
                    if mp.is_file():
                        selected_db = mp
                        break
                    print(
                        "Path not found or not a file. Please try again.",
                        file=sys.stderr,
                    )
                    continue
                # Show detected candidates
                print("Detected Kobo databases:")
                for i, pth in enumerate(candidates, 1):
                    print(f"  {i}) {pth}")
                choice = input(
                    "Select [1-{}], 'm' to enter path manually, or 'q' to quit: ".format(
                        len(candidates)
                    )
                ).strip()
                if choice.lower() in {"q", "quit", "exit"}:
                    return 2
                if choice.lower() in {"m", "manual"}:
                    manual = input("Enter path to KoboReader.sqlite: ").strip()
                    mp = Path(manual).expanduser()
                    if mp.is_file():
                        selected_db = mp
                        break
                    print(
                        "Path not found or not a file. Please try again.",
                        file=sys.stderr,
                    )
                    continue
                try:
                    idx = int(choice)
                except ValueError:
                    print("Invalid selection.", file=sys.stderr)
                    continue
                if not (1 <= idx <= len(candidates)):
                    print("Selection out of range.", file=sys.stderr)
                    continue
                selected_db = candidates[idx - 1]
                break
        else:
            if not candidates:
                print(
                    "Could not locate .kobo/KoboReader.sqlite on mounted drives. "
                    "Specify --db PATH explicitly.",
                    file=sys.stderr,
                )
                return 2
            if len(candidates) == 1:
                selected_db = candidates[0]
            else:
                best = choose_best_kobo_sqlite(candidates)
                selected_db = best or candidates[0]
                # Inform about multiple matches
                print("Found multiple Kobo databases:", file=sys.stderr)
                for p in candidates:
                    print(f"  - {p}", file=sys.stderr)
                print(f"Choosing: {selected_db}", file=sys.stderr)

    print(f"Using DB: {selected_db}")
    count = export_highlights(
        db_path=str(selected_db),
        out_csv=args.out_csv,
        suppress_filename_chapter_titles=args.suppress_filename,
    )
    out_path = Path(args.out_csv).resolve()
    print(f"Wrote {count} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
