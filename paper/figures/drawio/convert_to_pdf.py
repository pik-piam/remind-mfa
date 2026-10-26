"""Export all draw.io diagrams in this folder to PDFs cropped to the diagram size."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DRAWIO_CANDIDATES = [
    "draw.io",
    "drawio",
    r"C:\Program Files\draw.io\draw.io.exe",
]


def find_drawio() -> str:
    for candidate in DRAWIO_CANDIDATES:
        path = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if path:
            return path
    raise FileNotFoundError("No draw.io desktop installation found.")


def convert(drawio: str, source: Path) -> None:
    target = source.with_suffix(".pdf")
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
    for source in sorted(ROOT.glob("*.drawio")):
        convert(drawio, source)


if __name__ == "__main__":
    main()
