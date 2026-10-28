"""Export all draw.io diagrams in this folder to PDFs cropped to the diagram size.

The PDFs are written to the numbered folder and named after their figure number in the papers,
as given in FIGURE_FILES.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT.parent / "numbered"

DRAWIO_CANDIDATES = [
    "draw.io",
    "drawio",
    r"C:\Program Files\draw.io\draw.io.exe",
]

# draw.io file name without suffix -> name of the PDF (figure number in the papers)
FIGURE_FILES = {
    "simplified": "Fig1a",
    "all": "Fig3",
    "plastics": "FigS2",
    "steel": "FigS3",
    "cement": "FigS4",
}


def find_drawio() -> str:
    for candidate in DRAWIO_CANDIDATES:
        path = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if path:
            return path
    raise FileNotFoundError("No draw.io desktop installation found.")


def convert(drawio: str, source: Path) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    target = OUTPUT_DIR / f"{FIGURE_FILES[source.stem]}.pdf"
    subprocess.run(
        [drawio, "--export", "--format", "pdf", "--crop", "--output", str(target), str(source)],
        check=True,
        capture_output=True,
    )
    if not target.exists():
        raise RuntimeError(f"Export failed for {source}")
    print(f"{source.name} -> {target.name}")


def main() -> None:
    drawio = find_drawio()
    sources = sorted(ROOT.glob("*.drawio"))
    unmapped = [source.name for source in sources if source.stem not in FIGURE_FILES]
    if unmapped:
        raise KeyError(f"No figure name in FIGURE_FILES for {unmapped}")
    for source in sources:
        convert(drawio, source)


if __name__ == "__main__":
    main()
