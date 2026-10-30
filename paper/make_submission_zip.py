"""Pack the manuscript LaTeX sources for submission to Springer Nature into a flat zip file.

The zip contains manuscript.tex, the .bbl and .bib files, the class file, and the main text figure
PDFs and their crop boxes. Paths in manuscript.tex are rewritten to the flat zip structure. The
\\ref{SI-...} cross-references are replaced by the numbers from the .aux file of the supplementary
information, since the submission system does not resolve them via xr-hyper.
Build the paper first (task build), so that the .bbl and .aux files are up to date.

Usage:
        python make_submission_zip.py
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

PAPER_DIR = Path(__file__).parent
MANUSCRIPT_DIR = PAPER_DIR / "manuscript"
FIGURES_DIR = PAPER_DIR / "figures"
SI_AUX = PAPER_DIR / "si" / "supplementary_information.aux"
CROP_BOXES = FIGURES_DIR / "crop_boxes.csv"

COPIED_FILES = ["manuscript.bbl", "references.bib", "sn-jnl.cls"]

OUTPUT_FILE = PAPER_DIR / "springer_submission.zip"

# original string in manuscript.tex -> string for the flat zip structure
PATH_REPLACEMENTS = {
    "../figures/crop_boxes.csv": "crop_boxes.csv",
    "{../figures/#2.pdf}": "{#2.pdf}",
}

# xr-hyper setup lines, each with an optional preceding comment line, which are obsolete once the
# SI references are resolved
XR_PATTERNS = [
    r"(?m)^(%.*\n)?\\RequirePackage\{xr-hyper\}\n",
    r"(?m)^(%.*\n)?\\externaldocument\[SI-\]\{[^}]*\}\n",
]


def get_figure_names(tex: str) -> list[str]:
    """Names of all included figures, relative to the figures folder, e.g. numbered/Fig1a."""
    # the preamble only contains the macro definition
    body = tex.split(r"\begin{document}", 1)[1]
    return re.findall(r"\\includecropped(?:\[[^\]]*\])?\{([^}]+)\}", body)


def flatten_tex(tex: str, figure_names: list[str]) -> str:
    for original, replacement in PATH_REPLACEMENTS.items():
        if original not in tex:
            raise ValueError(f"'{original}' not found in manuscript.tex")
        tex = tex.replace(original, replacement)
    for name in figure_names:
        tex = tex.replace(f"{{{name}}}", f"{{{Path(name).name}}}")
    return tex


def get_si_labels() -> dict[str, str]:
    """Numbers of all labels in the supplementary information, e.g. sec:smoothing -> S1.1.3."""
    aux = SI_AUX.read_text(encoding="utf-8")
    return dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", aux))


def resolve_si_refs(tex: str) -> str:
    for pattern in XR_PATTERNS:
        tex, n_found = re.subn(pattern, "", tex)
        if n_found != 1:
            raise ValueError(f"'{pattern}' found {n_found} times in manuscript.tex")
    labels = get_si_labels()

    def replace(match: re.Match) -> str:
        label = match.group(1)
        if label not in labels:
            raise KeyError(f"SI label '{label}' not found in {SI_AUX.name}")
        return labels[label]

    return re.sub(r"\\ref\{SI-([^}]+)\}", replace, tex)


def get_crop_boxes_csv(figure_names: list[str]) -> str:
    """Crop boxes of the included figures, with names matching the flat zip structure."""
    with open(CROP_BOXES, newline="") as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader if row["name"] in figure_names]
        fieldnames = reader.fieldnames
    for row in rows:
        row["name"] = Path(row["name"]).name
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def warn_if_outdated(file: Path, source: Path):
    if file.stat().st_mtime < source.stat().st_mtime:
        print(f"Warning: {file.name} is older than {source.name}, consider rebuilding the paper.")


def main():
    tex_file = MANUSCRIPT_DIR / "manuscript.tex"
    tex = tex_file.read_text(encoding="utf-8")
    figure_names = get_figure_names(tex)
    warn_if_outdated(MANUSCRIPT_DIR / "manuscript.bbl", tex_file)
    warn_if_outdated(SI_AUX, PAPER_DIR / "si" / "supplementary_information.tex")

    with zipfile.ZipFile(OUTPUT_FILE, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manuscript.tex", resolve_si_refs(flatten_tex(tex, figure_names)))
        for file in COPIED_FILES:
            zf.write(MANUSCRIPT_DIR / file, file)
        zf.writestr("crop_boxes.csv", get_crop_boxes_csv(figure_names))
        for name in figure_names:
            zf.write(FIGURES_DIR / f"{name}.pdf", f"{Path(name).name}.pdf")

    print(f"Wrote {OUTPUT_FILE} with {len(figure_names)} figures.")


if __name__ == "__main__":
    main()
