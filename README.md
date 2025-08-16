Kobo Highlights Extractor
 
 Export your Kobo reader highlights and notes to Markdown and CSV.
 
 # Overview
 This tool reads a Kobo `KoboReader.sqlite` database and produces:
 - Markdown files grouped by book, saved under `notes/<Author>/<Title>.md` by default.
 - Optionally, a CSV file with enriched metadata (only saved if you request it with `--out`).
 
 Markdown output uses inline HTML color highlighting via `<mark style="background-color: ...">…</mark>` for broad compatibility. Notes (annotations) are not color-highlighted.
 
 # Requirements
 - Python 3.12+
 - A local copy of your Kobo `KoboReader.sqlite` database
 
 # Installation
Run directly from the repo (no install):
 
 ```bash
 uv run -m kobo_highlights_extractor --db /path/to/KoboReader.sqlite
 ```
 
 Or install and use the CLI entrypoint:
 
 ```bash
 pip install .
 kobo-highlights-extractor --db /path/to/KoboReader.sqlite
 ```
 
## Install from Releases (prebuilt executables)
Download an executable from GitHub Releases for your OS/arch.

- Linux/macOS (tar.gz):
  ```bash
  # Example: kobo-highlights-extractor-v1.0.0-Linux-X64.tar.gz
  tar -xzf kobo-highlights-extractor-<version>-<OS>-<ARCH>.tar.gz
  chmod +x kobo-highlights-extractor  # may not be necessary
  ./kobo-highlights-extractor --help
  ```
  - macOS Gatekeeper may block unsigned binaries. You can allow it via:
    ```bash
    xattr -dr com.apple.quarantine kobo-highlights-extractor
    ```

- Windows (zip):
  1. Unzip the archive
  2. Run `kobo-highlights-extractor.exe`

Notes:
- Linux binaries are built on Ubuntu 20.04 to maximize glibc compatibility.
- Each artifact contains a single binary; place it on your PATH if you like (e.g., `/usr/local/bin`).

## Build locally
Requires `uv` (or a Python 3.12 environment) and PyInstaller will be added transiently.

```bash
make build-exe
./dist/kobo-highlights-extractor --help
```

# Usage
Default (Markdown to `notes/`, temporary CSV auto-deleted):
 
 ```bash
 uv run -m kobo_highlights_extractor --db /path/to/KoboReader.sqlite
 ```
 
 Options (see `src/kobo_highlights_extractor/cli.py`):
 
 - `--db PATH`
   Path to `KoboReader.sqlite`. Default: `KoboReader.sqlite` in current directory (must exist).
 
 - `--md-dir DIR`
   Directory for Markdown output. Default: `notes`. Structure: `notes/<Author>/<Title>.md`.
 
 - `--out PATH`
  CSV output path. Default is `-`, which uses a temporary CSV that is deleted automatically after Markdown generation.
  When running interactively, pressing Enter will keep the default `-`.
 
 - `--keep-filename-chapter`
   Keep chapter titles that look like filenames (suppressed by default).
 
 - `--log-level {CRITICAL,ERROR,WARNING,INFO,DEBUG}`
   Logging verbosity. Default: `INFO`.
 
 Examples:
 
 ```bash
 # Run interactively
 uv run -m kobo_highlights_extractor

 # Default: Markdown to notes/, temp CSV
 uv run -m kobo_highlights_extractor --db ~/KoboReader.sqlite
 
 # Persist CSV too
 uv run -m kobo_highlights_extractor --db ~/KoboReader.sqlite --out highlights.csv
 
 # Custom Markdown directory
 uv run -m kobo_highlights_extractor --db ~/KoboReader.sqlite --md-dir my_notes
 
 # Keep filename-like chapter titles
 uv run -m kobo_highlights_extractor --db ~/KoboReader.sqlite --keep-filename-chapter
 
 # More verbose logs
 uv run -m kobo_highlights_extractor --db ~/KoboReader.sqlite --log-level DEBUG
 ```
 
 # Output details
 Markdown:
 - Grouped by book (Author/Title)
 - Headings per chapter
 - Each highlight appears as a blockquote line (`>`)
 - Highlight text wrapped in `<mark style="background-color: ...">…</mark>`
 - Notes rendered as `Note: ...` (not highlighted)
 
 CSV columns (see `src/kobo_highlights_extractor/exporter.py`):
 - `BookmarkID`
 - `BookTitle`
 - `Author`
 - `ChapterTitle`
 - `DateCreated`
 - `DateModified`
 - `Color` (yellow, pink, blue, green; may be empty)
 - `Text`
 - `Annotation`
 - `Type`
 
 Color mapping from Kobo:
 - 0 → yellow
 - 1 → pink
 - 2 → blue
 - 3 → green
 
 In Markdown, inline colors use common names: `yellow`, `pink`, `lightblue`, `lightgreen`.
 
 # Troubleshooting
 - __Database file not found__
   Ensure `--db` points to an existing `KoboReader.sqlite` (e.g., `--db ~/Downloads/KoboReader.sqlite`).
 
 - __No highlights exported__
   Empty highlights/notes are ignored; entries marked hidden are filtered.
 
 - __HTML not rendered__
   Some Markdown viewers sanitize HTML. Inline `<mark>` may be stripped. Try another viewer.
 
 # Development
 - Format & lint: `make check`
 - Auto-format: `make fmt`
 - Lint with fixes: `make lint-fix`
 - Type check (Pyrefly): `make typecheck`
 
 Entrypoints:
 - Module: `python -m kobo_highlights_extractor`
 - CLI (installed): `kobo-highlights-extractor`
 
 Key modules:
 - CLI: `src/kobo_highlights_extractor/cli.py`
 - CSV export: `src/kobo_highlights_extractor/exporter.py`
 - Markdown export: `src/kobo_highlights_extractor/md_exporter.py`