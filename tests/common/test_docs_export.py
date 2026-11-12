from pathlib import Path

from remind_mfa.common.common_definition import (
    ExtrapolationDefinition,
    PlainDataPointDefinition,
    RemindMFAParameterDefinition,
)
from remind_mfa.common.docs_export import (
    GENERATED_SECTION_MARKER,
    scenario_parameters_markdown,
    update_generated_sections,
    write_docs_file,
)


def test_write_docs_file_strips_whitespace_and_trailing_newline(tmp_path: Path):
    path = tmp_path / "table.md"

    write_docs_file(path, "| a   | b |  \n|:----|--:|\t\n| x   | 1 |\n\n")

    assert path.read_bytes() == b"| a   | b |\n|:----|--:|\n| x   | 1 |\n"


def test_write_docs_file_adds_missing_final_newline(tmp_path: Path):
    path = tmp_path / "refs.bib"

    write_docs_file(path, "@article{key,\n  year = {2023}, \n}")

    assert path.read_bytes() == b"@article{key,\n  year = {2023},\n}\n"


def test_scenario_parameters_markdown_leaves_out_empty_items():
    definitions = [
        PlainDataPointDefinition(name="plain_prm", description="A scalar."),
        RemindMFAParameterDefinition(name="array_prm", dim_letters=("r", "u")),
        ExtrapolationDefinition(name="extrap_prm", dim_letters=("r",), blending_function="hermite"),
    ]

    text = scenario_parameters_markdown({"Steel": definitions})

    assert text == (
        "### Steel\n\n"
        "- **`plain_prm`**\\\n  *Type: plain*\\\n  A scalar.\n"
        "- **`array_prm`**\\\n  *Type: array; Dimensions: r, u*\n"
        "- **`extrap_prm`**\\\n  *Type: extrapolation (hermite); Dimensions: r*"
    )


def test_update_generated_sections_replaces_only_given_sections(tmp_path: Path):
    path = tmp_path / "README.md"
    path.write_text("# Manual part\n", encoding="utf-8")
    order = ["common", "steel", "cement"]

    update_generated_sections(path, {"cement": "old cement", "common": "old common"}, order)
    update_generated_sections(path, {"steel": "new steel", "common": "new common"}, order)
    update_generated_sections(path, {"steel": "new steel", "common": "new common"}, order)

    marker = GENERATED_SECTION_MARKER.format
    assert path.read_text(encoding="utf-8") == (
        f"# Manual part\n\n{marker(key='COMMON')}\n\nnew common\n\n"
        f"{marker(key='STEEL')}\n\nnew steel\n\n{marker(key='CEMENT')}\n\nold cement\n"
    )
