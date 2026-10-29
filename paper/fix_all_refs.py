"""Apply quick fixes to generated BibTeX files after docs export."""

from __future__ import annotations

from pathlib import Path

# (old, new) pairs of exact text replacements in the generated BibTeX file
REPLACEMENTS = [
    # Forward slash instead of backslash in the ODYSSEE title
    (
        "title        = {{ODYSSEE Database: Residential Technical /& Economic Data}},",
        "title        = {{ODYSSEE Database: Residential Technical \\& Economic Data}},",
    ),
    # Several ISBNs in one field, which biber rejects as invalid
    (
        "isbn = {978-92-64-97364-0 978-92-64-89881-3 978-92-64-83202-2 978-92-64-66764-8},",
        "isbn = {978-92-64-97364-0},",
    ),
    # Year range in the year field, which biber cannot sort; biblatex expects it in the date field
    (
        "year         = {2009--2024},",
        "date         = {2009/2024},",
    ),
    # Trailing commas after the author names, which biber removes with a warning
    (
        "author = {CatalinaYepesE,   and Anirudh Rao,   and Nicole Paul,   and Catarina Costa,   "
        "and alejocaldeGEM,   and Andres Abarca,  },",
        "author = {CatalinaYepesE and Anirudh Rao and Nicole Paul and Catarina Costa "
        "and alejocaldeGEM and Andres Abarca},",
    ),
]


def fix_bib_file(path: Path) -> None:
    """Apply all replacements in REPLACEMENTS to the BibTeX file."""
    text = path.read_text(encoding="utf-8")
    fixed = text
    for old, new in REPLACEMENTS:
        fixed = fixed.replace(old, new)
    if fixed != text:
        path.write_text(fixed, encoding="utf-8")


def main() -> None:
    """Apply all quick fixes to the generated docs BibTeX list."""
    root = Path(__file__).resolve().parent.parent
    fix_bib_file(root / "docs" / "all_refs.bib")


if __name__ == "__main__":
    main()
