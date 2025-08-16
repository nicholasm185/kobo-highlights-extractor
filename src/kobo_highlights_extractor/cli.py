from __future__ import annotations

import logging
from pathlib import Path
import tempfile

import typer

from .exporter import export_highlights
from .md_exporter import export_markdown_from_csv


def run(
    db_path: Path = typer.Option(
        "KoboReader.sqlite",
        "--db",
        prompt="Path to KoboReader.sqlite",
        help="Path to KoboReader.sqlite",
    ),
    out_csv: Path | None = typer.Option(
        Path("-"),
        "--out",
        prompt=(
            "Output CSV file (enter '-' to use a temporary CSV that is deleted automatically)."
        ),
        help=(
            "Output CSV file. Use '-' to write to a temporary CSV (default), which is cleaned up automatically."
        ),
        show_default=True,
    ),
    md_dir: Path | None = typer.Option(
        Path("notes"),
        "--md-dir",
        prompt="Directory to write Markdown notes grouped by book (default: notes). Output structure: <md_dir>/<Author>/<Title>.md",
        help=(
            "Directory to write Markdown notes grouped by book (default: notes). "
            "Output structure: <md_dir>/<Author>/<Title>.md"
        ),
    ),
    keep_filename_chapter: bool = typer.Option(
        False,
        "--keep-filename-chapter",
        help="Keep chapter titles that look like filenames (default is to suppress)",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Logging level (choices: CRITICAL, ERROR, WARNING, INFO, DEBUG)",
    ),
) -> None:
    # Validate log level
    valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
    level_upper = (log_level or "INFO").upper()
    if level_upper not in valid_levels:
        raise typer.BadParameter(
            f"Invalid log level '{log_level}'. Choose from: {', '.join(sorted(valid_levels))}."
        )
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, level_upper, logging.INFO),
        format="%(levelname)s: %(message)s",
    )
    log = logging.getLogger(__name__)

    selected_db = db_path.expanduser()
    if not selected_db.is_file():
        log.error(
            "Database file not found: %s. Specify a valid path with --db.", selected_db
        )
        raise typer.Exit(2)

    log.info("Using DB: %s", selected_db)
    suppress_filename = not keep_filename_chapter

    # Treat '-' as a sentinel meaning: use a temporary CSV (i.e., behave like None)
    if out_csv is not None and str(out_csv) == "-":
        out_csv = None

    provided_csv = out_csv is not None and str(out_csv).strip() != ""
    if provided_csv:
        # Type guard for static checkers
        assert out_csv is not None
        out_path = out_csv.resolve()
        count = export_highlights(
            db_path=str(selected_db),
            out_csv=str(out_path),
            suppress_filename_chapter_titles=suppress_filename,
        )
        log.info("Wrote %d rows to %s", count, out_path)
        md_base = Path(md_dir).expanduser() if md_dir else None
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
                suppress_filename_chapter_titles=suppress_filename,
            )
            # Default to Markdown output directory
            md_base = Path(md_dir).expanduser() if md_dir else None
            if md_base:
                files = export_markdown_from_csv(str(tmp_csv), str(md_base))
                log.info(
                    "Rendered %d Markdown files under %s", files, md_base.resolve()
                )
            else:
                log.info("Wrote %d rows (temporary CSV used)", count)


def main() -> int:
    try:
        typer.run(run)
        return 0
    except KeyboardInterrupt:
        # Gracefully handle Ctrl+C
        typer.echo("Aborted by user.", err=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
