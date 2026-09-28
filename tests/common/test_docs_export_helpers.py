from pathlib import Path

from remind_mfa.common.docs_export_helpers import write_docs_file


def test_write_docs_file_strips_whitespace_and_trailing_newline(tmp_path: Path):
    path = tmp_path / "table.md"

    write_docs_file(path, "| a   | b |  \n|:----|--:|\t\n| x   | 1 |\n\n")

    assert path.read_bytes() == b"| a   | b |\n|:----|--:|\n| x   | 1 |\n"


def test_write_docs_file_adds_missing_final_newline(tmp_path: Path):
    path = tmp_path / "refs.bib"

    write_docs_file(path, "@article{key,\n  year = {2023}, \n}")

    assert path.read_bytes() == b"@article{key,\n  year = {2023},\n}\n"

