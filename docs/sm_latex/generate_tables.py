from __future__ import annotations

import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = ROOT.parent
OUTPUT_ROOT = ROOT / "generated"
BIB_SOURCE = SOURCE_ROOT / "mrmfa_sources.bib"
BIB_TARGET = ROOT / "mrmfa_sources.bib"

SECTIONS = ["plastics", "steel", "cement"]
SUBSECTIONS = ["dimensions", "processes", "flows", "stocks", "trades", "parameters"]

COLUMN_WIDTHS: dict[str, list[float]] = {
    "dimensions": [0.25, 0.09],
    "processes": [0.25],
    "flows": [0.15, 0.25, 0.25],
    "stocks": [0.15, 0.16, 0.15, 0.23, 0.20],
    "trades": [0.15, 0.20],
    "parameters": [0.11, 0.17, 0.25, 0.42],
}


def escape_latex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    escaped = []
    for char in text:
        escaped.append(replacements.get(char, char))
    return "".join(escaped)


def sanitize_bib_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    replacements = {
        "–": "--",
        "—": "---",
        "−": "-",
        "“": "``",
        "”": "''",
        "‘": "'",
        "’": "'",
        "…": "...",
        " ": " ",
        "­": "",
        "": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def citation_placeholder(match: re.Match[str]) -> str:
    raw = match.group(1)
    ids = [part.strip().lstrip("@").strip() for part in re.split(r"[;,]", raw) if part.strip()]
    token = f"CITE{citation_placeholder.counter}"
    citation_placeholder.counter += 1
    citation_placeholder.mapping[token] = ids
    return f"@@{token}@@"


citation_placeholder.counter = 0  # type: ignore[attr-defined]
citation_placeholder.mapping = {}  # type: ignore[attr-defined]


def format_cell(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    text = re.sub(r"\[@([^\]]+)\]", citation_placeholder, text)
    text = escape_latex(text)
    for token, ids in citation_placeholder.mapping.items():
        cite_text = r"\cite{" + ",".join(ids) + r"}"
        text = text.replace(f"@@{token}@@", cite_text)
    return text


def parse_markdown_table(path: Path) -> tuple[list[str], list[list[str]]]:
    lines = [
        line.rstrip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    rows = [line for line in lines if line.lstrip().startswith("|")]
    if len(rows) < 2:
        raise ValueError(f"No markdown table found in {path}")

    def split_row(row: str) -> list[str]:
        parts = [part.strip() for part in row.strip().strip("|").split("|")]
        return parts

    header = split_row(rows[0])
    body_rows = [split_row(row) for row in rows[2:]]
    return header, body_rows


def column_spec(subsection: str, column_count: int) -> str:
    widths = COLUMN_WIDTHS.get(subsection, [])
    if len(widths) != column_count:
        short = max(0.10, 0.92 / max(column_count, 1))
        widths = [short] * column_count
    return "".join(
        rf">{{\raggedright\arraybackslash}}p{{{width:.2f}\linewidth}}" for width in widths
    )


def render_table(
    subsection: str,
    caption: str,
    label: str,
    header: list[str],
    rows: list[list[str]],
) -> str:
    citation_placeholder.counter = 0  # type: ignore[attr-defined]
    citation_placeholder.mapping = {}  # type: ignore[attr-defined]

    headers = [format_cell(cell) for cell in header]
    body = [[format_cell(cell) for cell in row] for row in rows]
    spec = column_spec(subsection, len(headers))
    lines = [
        rf"\begin{{longtable}}{{{spec}}}",
        rf"\caption{{{caption}}}\label{{{label}}}\\",
        r"\toprule",
        " & ".join(headers) + r" \\",
        r"\midrule",
        r"\endfirsthead",
        rf"\caption{{{caption} (continued)}}\\",
        r"\toprule",
        " & ".join(headers) + r" \\",
        r"\midrule",
        r"\endhead",
        r"\midrule",
        rf"\multicolumn{{{len(headers)}}}{{r}}{{Continued on next page}} \\",
        r"\endfoot",
        r"\bottomrule",
        r"\endlastfoot",
    ]
    for row in body:
        lines.append(" & ".join(row) + r" \\")
    lines.append(r"\end{longtable}")
    return "\n".join(lines) + "\n"


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    BIB_TARGET.write_text(
        sanitize_bib_text(BIB_SOURCE.read_text(encoding="utf-8")), encoding="utf-8"
    )
    for section in SECTIONS:
        for subsection in SUBSECTIONS:
            source = SOURCE_ROOT / section / "definitions" / f"{subsection}.md"
            header, rows = parse_markdown_table(source)
            tex = render_table(
                subsection=subsection,
                caption=f"{section.capitalize()} {subsection.capitalize()}",
                label=f"tab:{section}-{subsection}",
                header=header,
                rows=rows,
            )
            (OUTPUT_ROOT / f"{section}_{subsection}.tex").write_text(tex, encoding="utf-8")


if __name__ == "__main__":
    main()
