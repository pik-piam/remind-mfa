"""Export of the generated files of the documentation site."""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from pydantic import PrivateAttr

from remind_mfa.common.assumptions_doc import assumptions_df
from remind_mfa.common.common_config import DocsExportCfg
from remind_mfa.common.common_definition import ExtrapolationDefinition, PlainDataPointDefinition
from remind_mfa.common.common_definition import scenario_parameters as common_scn_prm_def
from remind_mfa.common.common_mappings import CommonDisplayNames
from remind_mfa.common.helpers import DOCS_PATH, ModelNames, RemindMFABaseModel

if TYPE_CHECKING:
    from remind_mfa.common.common_model import CommonModel

SCENARIO_README_PATH = DOCS_PATH.parent / "config" / "scenarios" / "README.md"
"""Scenario README, whose generated sections list the scenario parameters."""

# A citation list such as "[@Andrews2019], [@Kaufmann2024]" may be split on commas.
# Free-text sources may contain commas themselves and are kept as one opaque token.
CITATION_LIST_PATTERN = re.compile(r"\[@[^\]]+\](\s*,\s*\[@[^\]]+\])*")

GENERATED_SECTION_MARKER = (
    "<!-- GENERATED SECTION {key}. DO NOT EDIT BY HAND: THE DOCS EXPORT OVERWRITES IT. -->"
)
GENERATED_SECTION_PATTERN = re.compile(
    r"^<!-- GENERATED SECTION ([A-Z_]+)\. DO NOT EDIT BY HAND: THE DOCS EXPORT OVERWRITES IT\. -->$",
    re.MULTILINE,
)


class DocumentationExporter(RemindMFABaseModel):
    """Writes the generated files of the documentation site from a model run.

    These are the definition tables, assumptions, config schema and scenario parameters of the
    model, the merged bibliography, and the generated sections of the scenario README.
    """

    cfg: DocsExportCfg
    display_names: CommonDisplayNames

    _model: "CommonModel | None" = PrivateAttr(default=None)

    def export(self, model: "CommonModel"):
        """Write all generated documentation files of the model.

        Args:
            model: Model run whose definition, config and parameters are documented.
        """
        if not self.cfg.do_export:
            return
        self._model = model
        self.definition_to_markdown()
        self.merge_bibtex_files()
        self.assumptions_to_markdown()
        self.cfg_to_markdown()
        self.scenario_parameters_to_markdown()

    @property
    def model_docs_path(self) -> Path:
        """Docs folder of the model."""
        return DOCS_PATH / self._model.name

    def definition_to_markdown(self):
        """Write one table per part of the future MFA definition (dimensions, flows, ...)."""
        dfs = self._model.definition_future.to_dfs()

        def dim_items_str(letter: str) -> str:
            dim = self._model.dims[letter]
            if dim.name == "Region":
                return "*see region definition*"
            if dim.dtype is int:
                return f"{dim.items[0]} to {dim.items[-1]}"
            return ", ".join(str(item) for item in dim.items)

        dfs["dimensions"]["items"] = dfs["dimensions"]["letter"].map(dim_items_str)

        drop_columns = {
            "dimensions": ["dtype"],
            "stocks": ["solver", "time_letter"],
            "flows": ["name_override"],
        }
        for name, cols in drop_columns.items():
            if name in dfs:
                for col in cols:
                    if col in dfs[name].columns:
                        dfs[name] = dfs[name].drop(columns=col, inplace=False)

        def convert_cell(cell: Any) -> str:
            if isinstance(cell, type):
                cell = cell.__name__
            elif isinstance(cell, tuple):
                cell = ", ".join(cell)
            elif cell is None:
                cell = ""
            return self._cell_str(cell)

        for name, df in dfs.items():
            df.columns = [self.display_names[col] for col in df.columns]
            columns_to_convert = list(df.columns)
            if name == "parameters":
                # sources are matched by internal parameter name, so before converting the names
                df = self._add_parameter_sources(params_df=df)
            df[columns_to_convert] = df[columns_to_convert].map(convert_cell)
            write_docs_file(
                self.model_docs_path / f"definitions/{name}.md", df.to_markdown(index=False)
            )

    def merge_bibtex_files(self):
        """Merge the bibliography of the input data with the custom references of the docs."""
        src1 = self._model.data_reader.parameters_path / "mrmfa_sources.bib"
        src2 = DOCS_PATH / "custom_refs.bib"
        out = DOCS_PATH / "all_refs.bib"
        merge_bib_files([src1, src2], out)

    def _add_parameter_sources(self, params_df: pd.DataFrame) -> pd.DataFrame:
        """Add a "Sources" column to the parameters table, matched by the "Name" column."""
        sources_df = pd.read_csv(self._model.data_reader.parameters_path / "mrmfa_sources.csv")
        return merge_parameters_sources(
            sources_df=sources_df, params_df=params_df, prefix=self._model.name[:2]
        )

    def assumptions_to_markdown(self):
        """Write the table of assumptions documented during the model run."""
        df = assumptions_df()
        write_docs_file(self.model_docs_path / "assumptions.md", df.to_markdown(index=False))

    def cfg_to_markdown(self):
        """Write the table of all config fields of the model."""
        schema_df = type(self._model.cfg).to_schema_df()
        schema_df.columns = [self.display_names[col] for col in schema_df.columns]
        schema_df = schema_df.map(
            lambda cell: "" if str(cell) == "PydanticUndefined" else self._cell_str(cell)
        )
        write_docs_file(
            self.model_docs_path / "config_schema.md", schema_df.to_markdown(index=False)
        )

    def scenario_parameters_to_markdown(self):
        """Write the lists of common and model-specific scenario parameter definitions to the docs
        folders, and update the corresponding generated sections of the scenario README.

        Names are kept internal (no display names), since they are used in the scenario CSVs.
        """
        sections = {
            "common": (DOCS_PATH / "common", {"Common": common_scn_prm_def}),
            self._model.name: (self.model_docs_path, self._model.scenario_parameter_doc_groups()),
        }
        texts = {}
        for key, (folder, groups) in sections.items():
            texts[key] = scenario_parameters_markdown(groups)
            folder.mkdir(exist_ok=True)
            write_docs_file(folder / "scenario_parameters.md", texts[key])
        order = ["common"] + [model.value for model in ModelNames]
        update_generated_sections(SCENARIO_README_PATH, sections=texts, order=order)

    def _cell_str(self, cell: Any) -> str:
        """String of a table cell, with internal names replaced by display names if configured."""
        if not self.cfg.apply_mappings:
            return str(cell)
        return self.display_names[str(cell)].replace("<br>", " ")


def write_docs_file(path: Path, text: str):
    """Write a generated docs file in a standardized form (compatible with pre-commit)."""
    content = "\n".join(line.rstrip() for line in text.split("\n")).rstrip("\n")
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(content + "\n" if content else "")


def merge_bib_files(src_paths: list[Path], out_path: Path) -> tuple[int, int, int]:
    """Merge bib files from src_paths into out_path, keeping only the first entry of each key.

    Returns a tuple: (total_entries_read, duplicates_skipped, total_written)
    """
    seen_keys: dict[str, str] = {}
    all_entries: list[str] = []
    total_read = 0
    duplicates = 0

    for path in src_paths:
        try:
            text = open(path, encoding="utf-8").read()
        except FileNotFoundError:
            # If a source file is missing, just continue (keeps behaviour simple)
            continue
        entries = _split_entries(text)
        for entry in entries:
            total_read += 1
            key = _extract_key(entry)

            # If key present and already seen, skip
            if key and key in seen_keys:
                duplicates += 1
                continue

            # Accept this entry
            all_entries.append(entry)
            if key:
                seen_keys[key] = entry

    # Write merged file with entries separated by a blank line
    write_docs_file(out_path, "\n\n".join(all_entries))

    written = len(all_entries)
    return total_read, duplicates, written


def _split_entries(text: str) -> list[str]:
    """Split raw bibtex file content into individual entry strings.

    This finds occurrences of '@' starting an entry and slices between them.
    """
    # Find all start indices of entries (an '@' followed by word chars)
    starts = [m.start() for m in re.finditer(r"@\w+\s*\(", text)]
    # Also allow entries that use brace style: @article{key,
    starts += [m.start() for m in re.finditer(r"@\w+\s*\{", text)]
    starts = sorted(set(starts))
    if not starts:
        return []
    entries = []
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        entries.append(text[s:end].strip())
    return entries


def _extract_key(entry: str) -> str | None:
    """Extract the BibTeX key from an entry, or None if not found."""
    m = re.match(r"@\w+\s*[\{\(]\s*([^,\s]+)", entry, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def merge_parameters_sources(
    sources_df: pd.DataFrame, params_df: pd.DataFrame, prefix: str
) -> pd.DataFrame:
    """Merge parameter files with source information and generate markdown documentation."""

    # Filter sources for this module (module-specific + common)
    module_sources = sources_df[sources_df["Filename"].str.startswith(f"{prefix}_")].copy()

    # Extract parameter name from filename (prefix_param.cs4r -> param)
    module_sources["Name"] = (
        module_sources["Filename"]
        .str.replace(f"{prefix}_", "", regex=True)
        .str.replace(".cs4r", "")
    )

    # Merge with parameters based on Name, rename Bibtex -> Sources
    merged_df = params_df.merge(
        module_sources[["Name", "Bibtex"]].rename(columns={"Bibtex": "Sources"}),
        on="Name",
        how="left",
    )

    # Replace NaN with empty string for cleaner display
    merged_df["Sources"] = merged_df["Sources"].fillna("")

    # Apply custom mapping: append CUSTOM_SOURCES to the sources from the csv file
    CUSTOM_SOURCES = {
        "carbon_content_polymers": "Carbon contents of different polymers are calculated from their chemical structure. For broader categories (Other thermoplastics, other thermosets), rough assumptions and weighted averages were used.",
        "mechanical_recycling_yield": "[@Uekert23]",
        "chemical_recycling_yield": "[@Yadav23]",
        "reclmech_loss_uncontrolled_rate": "[@brown_potential_2023]",
        "lifetime_rel_std": "Expert guess",
        "waste_size_min": "[@Kaufmann2024]",
        "waste_size_max": "[@Kaufmann2024]",
        "cao_emission_factor": "Stoichiometry",
        "floorspace": "[@edgeb26]",
        "unoccupied_residential_stock_share": "[@Zheng2025]",
    }
    if CUSTOM_SOURCES:
        mapped = merged_df["Name"].map(CUSTOM_SOURCES)
        # mask: a non-empty custom mapping exists
        has_custom = mapped.notna() & (mapped.astype(str).str.strip() != "")
        merged_df.loc[has_custom, "Sources"] = [
            _combine_sources(existing, custom)
            for existing, custom in zip(merged_df.loc[has_custom, "Sources"], mapped[has_custom])
        ]

    return merged_df


def _split_sources(value):
    """Split a source string into tokens, keeping free text intact."""
    value = str(value).strip()
    if not value:
        return []
    if not CITATION_LIST_PATTERN.fullmatch(value):
        return [value]
    return re.findall(r"\[@[^\]]+\]", value)


def _combine_sources(existing, custom):
    """Append custom source tokens to the existing ones, skipping duplicates."""
    tokens = _split_sources(existing)
    for token in _split_sources(custom):
        if token not in tokens:
            tokens.append(token)
    return ", ".join(tokens)


def scenario_parameters_markdown(groups: dict[str, list]) -> str:
    """Markdown list of scenario parameter definitions for the docs, one subsection per group.

    Args:
        groups: Subsection title (e.g. "Cement (bottom-up module)") mapped to the list of
            scenario parameter definitions of that model or module.
    """
    blocks = []
    for title, definitions in groups.items():
        items = "\n".join(_scenario_parameter_item(definition) for definition in definitions)
        blocks.append(f"### {title}\n\n{items}")
    return "\n\n".join(blocks)


def _scenario_parameter_item(definition) -> str:
    """List item with name, metadata and description on separate lines.

    Uses backslash line breaks, since the pre-commit hooks remove trailing double spaces.
    """
    # ExtrapolationDefinition subclasses RemindMFAParameterDefinition, so check it first
    if isinstance(definition, ExtrapolationDefinition):
        prm_type = f"extrapolation ({definition.blending_function})"
    elif isinstance(definition, PlainDataPointDefinition):
        prm_type = "plain"
    else:
        prm_type = "array"
    metadata = [f"Type: {prm_type}"]
    dim_letters = getattr(definition, "dim_letters", ())
    if dim_letters:
        metadata.append(f"Dimensions: {', '.join(dim_letters)}")
    lines = [f"**`{definition.name}`**", f"*{'; '.join(metadata)}*"]
    if definition.description:
        lines.append(definition.description)
    return "- " + "\\\n  ".join(lines)


def update_generated_sections(path: Path, sections: dict[str, str], order: list[str]):
    """Replace generated sections at the end of a markdown file, keeping all other sections.

    Generated sections follow the hand-written part of the file. Each starts with a marker
    line and ends at the next marker or the end of the file. Sections are sorted by `order`.

    Args:
        path: Markdown file to update.
        sections: Section key (e.g. "common", "steel") mapped to the new section text.
        order: All valid section keys, in the order of the sections in the file.
    """
    parts = GENERATED_SECTION_PATTERN.split(path.read_text(encoding="utf-8"))
    manual_part = parts[0].rstrip()
    existing = {key.lower(): text.strip() for key, text in zip(parts[1::2], parts[2::2])}
    all_sections = existing | sections
    unknown = set(all_sections) - set(order)
    if unknown:
        raise ValueError(f"Unknown generated sections {sorted(unknown)} in {path}.")
    blocks = [manual_part] + [
        f"{GENERATED_SECTION_MARKER.format(key=key.upper())}\n\n{all_sections[key]}"
        for key in order
        if key in all_sections
    ]
    write_docs_file(path, "\n\n".join(blocks))
