"""
Prepare the PDF figures included by the manuscript and the SI.

1. The generated PDF figures are copied to the numbered folder under their figure number in the
   papers, e.g. Fig1b.pdf or FigS1.pdf, as given in FIGURE_FILES. The draw.io figures are exported
   to the numbered folder directly (see figures/drawio/convert_to_pdf.py).
2. The content area of all numbered figures, i.e. the bounding box of all non-white pixels, is
   written to a csv file, which LaTeX reads to crop the figures on inclusion (see
   \\includecropped in paper/manuscript/manuscript.tex and paper/si/supplementary_information.tex).
   Cropping is applied to all figures: some are placed on a full page with white or transparent
   surroundings, e.g. figures saved manually from the browser (figure 6) or exported from drawio
   (figure 1b), others have white margins. The PDF files themselves are not modified.

FIGURE_FILES has to be updated when figures are added, removed or reordered in the tex files.

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

NUMBERED_DIR = FIGURE_DIR / "numbered"
CROP_BOX_FILE = FIGURE_DIR / "crop_boxes.csv"
COLUMNS = ["name", "llx", "lly", "urx", "ury"]

# Name of the numbered PDF (figure number in the papers) -> generated PDF relative to the figures
# folder, without suffix. Figures from the main paper which are repeated in the SI have two entries.
FIGURE_FILES = {
    # manuscript (figures 1a and 3 are draw.io figures)
    "Fig1b": "pdf/figure_1b_model_steps",
    "Fig2": "pdf/figure_2_steel_JPN_s3",
    "Fig4a": "pdf/figure_4a",
    "Fig4b": "pdf/figure_4b",
    "Fig5": "pdf/figure_5_agg5",
    "Fig6": "pdf/figure_6_carbon",
    "Fig7": "pdf/figure_7_steel_agg5",
    "Fig8": "pdf/figure_8_cement_agg5",
    # SI: equations
    "FigS1": "pdf/figure_S1",
    # SI: additional figures (figures S2 to S4 in the definitions are draw.io figures)
    "FigS5": "pdf/figure_5_h12",
    "FigS6": "pdf/figure_5_agg5",
    "FigS7": "pdf/figure_5_h12_countries",
    "FigS8": "pdf/figure_5_agg5_countries",
    "FigS9": "pdf/figure_6_plastics",
    "FigS10": "pdf/figure_6_steel",
    "FigS11": "pdf/figure_6_cement",
    "FigS12": "pdf/figure_7_plastics_h12",
    "FigS13": "pdf/figure_7_steel_h12",
    "FigS14": "pdf/figure_7_cement_h12",
    "FigS15": "pdf/figure_7_plastics_agg5",
    "FigS16": "pdf/figure_7_steel_agg5",
    "FigS17": "pdf/figure_7_cement_agg5",
    "FigS18": "pdf/figure_8_plastics_h12",
    "FigS19": "pdf/figure_8_steel_h12",
    "FigS20": "pdf/figure_8_cement_h12",
    "FigS21": "pdf/figure_8_plastics_agg5",
    "FigS22": "pdf/figure_8_steel_agg5",
    "FigS23": "pdf/figure_8_cement_agg5",
    "FigS24": "pdf/gdppc_h12",
    "FigS25": "pdf/gdppc_agg5",
    "FigS26": "pdf/pop_h12",
    "FigS27": "pdf/pop_agg5",
    "FigS28": "pdf/production_plastics_h12_vs_iso249",
    "FigS29": "pdf/production_steel_h12_vs_iso249",
    "FigS30": "pdf/production_cement_h12_vs_iso249",
    "FigS31": "pdf/pcstocks_plastics_h12_vs_iso249",
    "FigS32": "pdf/pcstocks_steel_h12_vs_iso249",
    "FigS33": "pdf/pcstocks_cement_h12_vs_iso249",
}


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


def copy_numbered_figures():
    NUMBERED_DIR.mkdir(exist_ok=True)
    for name, source in FIGURE_FILES.items():
        pdf = FIGURE_DIR / f"{source}.pdf"
        if not pdf.exists():
            raise FileNotFoundError(f"Missing source figure for {name}: {pdf}")
        shutil.copy2(pdf, NUMBERED_DIR / f"{name}.pdf")
        print(f"{source} -> numbered/{name}")


def write_crop_boxes(dpi: int = 144, threshold: int = 8, margin: float = 1.0):
    pdfs = sorted(NUMBERED_DIR.glob("*.pdf"))
    crop_boxes = {}
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


def main(dpi: int = 144, threshold: int = 8, margin: float = 1.0):
    copy_numbered_figures()
    write_crop_boxes(dpi=dpi, threshold=threshold, margin=margin)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dpi", type=int, default=144, help="rendering resolution")
    parser.add_argument(
        "--threshold",
        type=int,
        default=8,
        help="pixels deviating from white by more than this (0-255) count as content",
    )
    parser.add_argument("--margin", type=float, default=1.0, help="margin around content in bp")
    args = parser.parse_args()
    main(dpi=args.dpi, threshold=args.threshold, margin=args.margin)
