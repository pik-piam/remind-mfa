"""Apply quick fixes to generated BibTeX files after docs export."""

from __future__ import annotations

from pathlib import Path


def fix_odyssee_title(path: Path) -> None:
    """Replace the forward slash in the ODYSSEE title with a backslash."""
    text = path.read_text(encoding="utf-8")
    old = "title        = {{ODYSSEE Database: Residential Technical /& Economic Data}},"
    new = "title        = {{ODYSSEE Database: Residential Technical \\& Economic Data}},"
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    """Apply all quick fixes to the generated docs BibTeX list."""
    root = Path(__file__).resolve().parent.parent
    fix_odyssee_title(root / "docs" / "all_refs.bib")


if __name__ == "__main__":
    main()
