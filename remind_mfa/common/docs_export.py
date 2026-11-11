from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import pandas as pd
from pydantic import PrivateAttr

from remind_mfa.common.assumptions_doc import assumptions_df
from remind_mfa.common.common_config import DocsExportCfg
from remind_mfa.common.common_definition import scenario_parameters as common_scn_prm_def
from remind_mfa.common.common_mappings import CommonDisplayNames
from remind_mfa.common.docs_export_helpers import (
    merge_bib_files,
    merge_parameters_sources,
    scenario_parameters_markdown,
    update_generated_sections,
    write_docs_file,
)
from remind_mfa.common.helpers import DOCS_PATH, ModelNames, RemindMFABaseModel

if TYPE_CHECKING:
    from remind_mfa.common.common_model import CommonModel

SCENARIO_README_PATH = DOCS_PATH.parent / "config" / "scenarios" / "README.md"
"""Scenario README, whose generated sections list the scenario parameters."""


class DocumentationExporter(RemindMFABaseModel):
    """Writes the generated files of the documentation site from a model run.

    These are the definition tables, assumptions, config schema and scenario parameters of the
    model, the merged bibliography, and the generated sections of the scenario README.
    """

    cfg: DocsExportCfg
    display_names: CommonDisplayNames

    _model: Optional["CommonModel"] = PrivateAttr(default=None)

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
