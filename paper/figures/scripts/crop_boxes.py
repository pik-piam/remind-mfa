"""
Detect the content area of PDF figures, i.e. the bounding box of all non-white pixels,
and write it to a csv file, which LaTeX reads to crop the figures on inclusion
(see \\includecropped in paper/manuscript/manuscript.tex and paper/sm/supplementary_materials.tex).
The PDF files themselves are not modified.

Applied to all PDF figures: some are placed on a full page with white or transparent
surroundings, e.g. figures saved manually from the browser (figure 9) or exported from drawio
(figure 3), others have white margins. Figures are identified by their path relative to the
figures folder without suffix, e.g. pdf/figure_1 or drawio/simplified.

Requires Ghostscript (gs, gswin64c, or rungs from TeX Live) for rendering.
"""

import argparse
import csv
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

from _constants import FIGURE_DIR

CROP_BOX_FILE = FIGURE_DIR / "crop_boxes.csv"
COLUMNS = ["name", "llx", "lly", "urx", "ury"]


def _ghostscript() -> str:
    for exe in ("gs", "gswin64c", "gswin32c", "rungs"):
        path = shutil.which(exe)
        if path is not None:
            return path
    raise FileNotFoundError("Ghostscript not found (tried gs, gswin64c, gswin32c, rungs).")


def _render(pdf: Path, png: Path, dpi: int):
    """Render the first page; the crop box is used, as pdflatex does by default."""
    subprocess.run(
        [
            _ghostscript(),
            "-q",
            "-dSAFER",
            "-dNOPAUSE",
            "-dBATCH",
            "-dUseCropBox",
            "-dFirstPage=1",
            "-dLastPage=1",
            "-sDEVICE=png16m",
            f"-r{dpi}",
            f"-sOutputFile={png}",
            str(pdf),
        ],
        check=True,
    )


def content_box(pdf: Path, dpi: int = 144, threshold: int = 8, margin: float = 1.0) -> list[float]:
    """Bounding box of non-white content in bp (1/72 inch), relative to the lower left
    page corner, as expected by the viewport key of \\includegraphics."""
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "page.png"
        _render(pdf, png, dpi)
        image = Image.open(png).convert("RGB")
        image.load()

    white = Image.new("RGB", image.size, (255, 255, 255))
    deviation = ImageChops.difference(image, white).convert("L")
    content = deviation.point(lambda v: 255 if v > threshold else 0)
    bbox = content.getbbox()
    if bbox is None:
        raise ValueError(f"{pdf} has no non-white content.")

    left, top, right, bottom = bbox
    scale = 72 / dpi
    width, height = image.size[0] * scale, image.size[1] * scale
    # image rows count from the top, PDF coordinates from the bottom
    return [
        max(left * scale - margin, 0),
        max((image.size[1] - bottom) * scale - margin, 0),
        min(right * scale + margin, width),
        min((image.size[1] - top) * scale + margin, height),
    ]


def read_crop_boxes() -> dict[str, list[str]]:
    if not CROP_BOX_FILE.exists():
        return {}
    with open(CROP_BOX_FILE, newline="") as f:
        return {row["name"]: [row[c] for c in COLUMNS[1:]] for row in csv.DictReader(f)}


def main(patterns: list[str], dpi: int = 144, threshold: int = 8, margin: float = 1.0):
    pdfs = sorted({p for pattern in patterns for p in FIGURE_DIR.glob(pattern)})
    if not pdfs:
        raise FileNotFoundError(f"No PDFs matching {patterns} in {FIGURE_DIR}.")

    # keep entries of figures not processed in this run
    crop_boxes = read_crop_boxes()
    for pdf in pdfs:
        box = content_box(pdf, dpi=dpi, threshold=threshold, margin=margin)
        name = pdf.relative_to(FIGURE_DIR).with_suffix("").as_posix()
        crop_boxes[name] = [f"{v:.1f}" for v in box]
        print(f"{name}: {' '.join(crop_boxes[name])}")

    with open(CROP_BOX_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for name in sorted(crop_boxes):
            writer.writerow([name, *crop_boxes[name]])
    print(f"Written to {CROP_BOX_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "patterns",
        nargs="*",
        default=["pdf/*.pdf", "drawio/*.pdf"],
        help="file name patterns of PDFs, relative to the figures folder",
    )
    parser.add_argument("--dpi", type=int, default=144, help="rendering resolution")
    parser.add_argument(
        "--threshold",
        type=int,
        default=8,
        help="pixels deviating from white by more than this (0-255) count as content",
    )
    parser.add_argument("--margin", type=float, default=1.0, help="margin around content in bp")
    args = parser.parse_args()
    main(args.patterns, dpi=args.dpi, threshold=args.threshold, margin=args.margin)
