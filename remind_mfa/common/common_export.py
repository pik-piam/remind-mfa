import logging
import os
import pickle
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, List, Literal, ClassVar

import flodym as fd
import numpy as np
from pydantic import PrivateAttr
import pandas as pd

from remind_mfa.common.docs_export_helpers import merge_parameters_sources
from remind_mfa.common.docs_export_helpers import merge_bib_files
from remind_mfa.common.docs_export_helpers import write_docs_file
from remind_mfa.common.docs_export_helpers import scenario_parameters_markdown
from remind_mfa.common.docs_export_helpers import update_generated_sections

from remind_mfa.common.assumptions_doc import assumptions_df, assumptions_str
from remind_mfa.common.common_config import CommonCfg, ExportCfg
from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.common.common_definition import scenario_parameters as common_scn_prm_def
from remind_mfa.common.common_mappings import CommonDisplayNames
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.common.helpers import (
    DOCS_PATH,
    ModelNames,
    RemindMFABaseModel,
    series_export_path,
    export_dir_prefix,
)

SCENARIO_README_PATH = DOCS_PATH.parent / "config" / "scenarios" / "README.md"
"""Scenario README, whose generated sections list the scenario parameters."""

if TYPE_CHECKING:
    import pyam

    from remind_mfa.common.common_model import CommonModel


class IamcVariable(RemindMFABaseModel):
    """Declarative specification of a single IAMC output variable."""

    variable_name: str
    """IAMC variable path, e.g. "Production|Iron and Steel|Steel"."""
    calculation_function: Callable[[CommonMFASystem], fd.FlodymArray]
    """Given the future MFA system, returns the array to report, reduced to (t, r) or (t, r, <per-dim>)."""
    unit: str
    """Base unit of the array, e.g. "t/yr" or "t"."""
    split_dims: Optional[List[str] | Literal["all"]] = None
    """Dimension names or letters to split into child variables (e.g. "Good"). None = single variable. "all" = all non-(h, t, r) dimensions."""
    aggregate_parent: bool = True
    """When this variable is split (``split_dims`` set), whether its children are summed back
    into ``variable_name``. Set False for a second, orthogonal split of a variable whose parent
    total is already produced by another split, to avoid double-counting the parent. Exactly one
    split per parent may keep this True; a second aggregating split of the same parent raises at
    export time."""
    region_weight: Optional[str] = None
    """Variable to weight by when aggregating to "World" (e.g. "Population" for per-capita
    variables). None = plain sum across regions."""


class RemindInputVariable(RemindMFABaseModel):
    """Declarative specification of a single variable that will serve as input to REMIND."""

    name: str
    """Name to use in the REMIND input layer."""
    calculation_function: Callable[[CommonMFASystem], fd.FlodymArray]
    """Given the future MFA system, returns the array to report, reduced to (t, r) or (t, r, <per-dim>)."""
    unit: Optional[str] = None
    """Base unit of the calculated data, e.g. "t/yr" or "t"."""


class CommonDataExporter(RemindMFABaseModel):
    cfg: ExportCfg
    display_names: CommonDisplayNames

    # Datasets producing a single file: placed directly in the run folder, no subfolder.
    FLAT_DATASETS: ClassVar[set[str]] = {"pickle", "iamc_reporting", "iamc_raw", "assumptions"}

    _IAMC_RAW_PARAMETERS: ClassVar[dict[str, str]] = {
        "lifetime_mean": "yr",
        "lifetime_std": "yr",
        "population": "cap",
        "gdppc": "$/cap/yr",
    }

    _model: Optional["CommonModel"] = PrivateAttr(default=None)
    _run_path: Optional[str] = PrivateAttr(default=None)

    def export(self, model: "CommonModel"):
        # Always set the model as the visualizer needs it to determine the run folder
        # even when data export is disabled.
        self._model = model
        if not self.cfg.do_export:
            return
        self.export_common()
        self.export_custom()

    def export_common(self):
        mfa = self._model.future_mfa
        if self.cfg.pickle.do_export:
            self._clear_recomputable_caches()
            pickle.dump(self._model, open(self.export_path("pickle", "model.pickle"), "wb"))
        if self.cfg.csv.do_export:
            import flodym.export as fde  # deferred: pulls in plotly and matplotlib

            dir_out = self.export_path("csv", "flows")
            fde.export_mfa_flows_to_csv(mfa=mfa, export_directory=dir_out)
            fde.export_mfa_stocks_to_csv(mfa=mfa, export_directory=dir_out)
        if self.cfg.mrindustry.do_export:
            self.write_mrindustry()
        if self.cfg.assumptions.do_export:
            file_out = self.export_path("assumptions", "assumptions.txt")
            with open(file_out, "w") as f:
                f.write(assumptions_str())
        if self.cfg.docs.do_export:
            self.definition_to_markdown(self._model.definition_future)
            self.merge_bibtex_files()
            self.assumptions_to_markdown()
            self.cfg_to_markdown(cfg=self._model.cfg)
            self.scenario_parameters_to_markdown()
        if self.cfg.iamc_reporting.do_export:
            self.write_iamc_reporting()
        if self.cfg.iamc_raw.do_export:
            self.write_iamc_raw()

    def export_custom(self):
        pass

    @property
    def iamc_raw_parameters(self) -> dict[str, str]:
        """Parameters to include in the raw IAMC export, mapped to their units."""
        return CommonDataExporter._IAMC_RAW_PARAMETERS | self._IAMC_RAW_PARAMETERS

    def _clear_recomputable_caches(self):
        """Drop lifetime-model sf/pdf caches from the historical and future MFA stocks before pickling
        to save memory.

        These arrays (shape ``(n_t, n_t, ...)``) are read only through the ``sf``/``pdf``
        properties, which lazily recompute when the backing attribute is ``None`` -- so clearing
        them here is transparent: the next access (including any later ``stock.compute()``)
        rebuilds them from the stored lifetime parameters.
        """
        for mfa in (self._model.historical_mfa, self._model.future_mfa):
            for stock in mfa.stocks.values():
                lifetime_model: fd.LifetimeModel | None = getattr(stock, "lifetime_model", None)
                if lifetime_model is not None:
                    lifetime_model.reset_cached_arrays()

    @property
    def model_name(self) -> str:
        """Model identifier for the IAMC "model" column, including the REMIND-MFA version."""
        try:
            return f"REMIND-MFA {version('remind-mfa')}"
        except PackageNotFoundError:
            return "REMIND-MFA"

    def common_iamc_variables(self) -> list[IamcVariable]:
        """IAMC variables exported for every material.

        ``Population`` is exported both as an output variable and used as the weight for
        aggregating per-capita variables to the "World" region.
        """
        return [
            IamcVariable(
                variable_name="Population",
                calculation_function=lambda mfa: mfa.parameters["population"].sum_to(("t", "r")),
                unit="cap",
            ),
            IamcVariable(
                variable_name="GDP|PPP",
                calculation_function=lambda mfa: (
                    mfa.parameters["gdppc"] * mfa.parameters["population"] / 1e9
                ).sum_to(("t", "r")),
                unit="billion USD_2005/yr",
            ),
        ]

    def iamc_variables(self) -> list[IamcVariable]:
        """Material-specific IAMC variable specifications. Override in subclasses.
        When adding IAMC variables, follow the nomenclature of the CIRCOMOD or the
        PRISMA project (templates can be found in the Cloud under data/iamc_nomenclature),
        if possible. Document the source (i.e. which template you took each variable from)."""
        return []

    def iamc_aggregates(self) -> list[str]:
        """Extra parent variables to aggregate, beyond the automatic per-split parents.

        Variables declared with a ``per`` dimension are summed back to their parent
        automatically. Use this only for parents whose children are separate specs rather
        than a ``per`` split (e.g. summing "…|Primary" and "…|Secondary" into their parent).
        Override in subclasses.
        """
        return []

    def write_iamc_reporting(self):
        """Export the selected variables from ``iamc_variables()`` in IAMC nomenclature."""
        iamc_vars = self.iamc_variables()
        if not iamc_vars:
            return
        iamc_vars = self.common_iamc_variables() + iamc_vars

        time_items = self.cfg.iamc_reporting.time_items
        self._warn_if_iamc_includes_historical(time_items, "IAMC reporting export")

        constants = self.iamc_constants(self._model)
        mfa = self._model.future_mfa

        iamc_dataframe, split_parent_components, region_weights = self._build_all_iamc_df(
            mfa, iamc_vars, constants, time_items
        )

        self._aggregate_iamc_variables(iamc_dataframe, split_parent_components)
        self._aggregate_iamc_regions(iamc_dataframe, region_weights)
        self._convert_iamc_units(iamc_dataframe)

        iamc_dataframe.to_excel(self.export_path("iamc_reporting", "iamc_reporting.xlsx"))

    def iamc_constants(self, model: "CommonModel") -> dict:
        """IAMC constants to include in every exported variable."""
        return {"model": self.model_name, "scenario": model.cfg.model_switches.scenario}

    def write_iamc_raw(self):
        """Export all flows, stocks, trades and selected parameters in IAMC format,
        with variable names derived from the internal names. One file per configured detail level.
        """
        time_items = self.cfg.iamc_raw.time_items
        self._warn_if_iamc_includes_historical(time_items, "Raw IAMC export")
        for detail in self.cfg.iamc_raw.detail:
            self._write_iamc_raw_file(detail, time_items)

    def _write_iamc_raw_file(self, detail: Literal["aggregated", "complete"], time_items: list):
        import pyam  # deferred: slow to import

        mfa = self._model.future_mfa
        vname_base = self._model.cfg.model.value
        constants = self.iamc_constants(self._model)

        df_list = []
        self._iamc_raw_flows(mfa, vname_base, detail, time_items, df_list)
        self._iamc_raw_stocks(mfa, vname_base, detail, time_items, df_list)
        self._iamc_raw_trades(mfa, vname_base, detail, time_items, df_list)

        df_out = pd.concat(df_list)
        pyam_df = pyam.IamDataFrame(df_out, **constants)
        self._aggregate_iamc_regions(pyam_df, region_weights={})

        if detail == "complete":
            df_list = []
            self._iamc_raw_parameters(mfa, vname_base, time_items, df_list)
            df_out = pd.concat(df_list)
            pyam_df_prms = pyam.IamDataFrame(df_out, **constants)
            pyam_df = pyam_df.append(pyam_df_prms)

        self._convert_iamc_units(pyam_df)
        pyam_df.to_csv(self.export_path("iamc_raw", f"iamc_raw_{detail}.csv"))

    def _iamc_raw_flows(self, mfa: fd.MFASystem, vname_base, detail, time_items, df_list):
        for flow in mfa.flows.values():
            df = self._iamc_raw_df(f"{vname_base}|flows|{flow.name}", flow, detail, time_items)
            df["unit"] = "t/yr"
            df_list.append(df)

    def _iamc_raw_stocks(self, mfa, vname_base, detail, time_items, df_list):
        config = [
            ("inflow", lambda stock: stock.inflow, "t/yr"),
            ("outflow", lambda stock: stock.outflow, "t/yr"),
            ("stock", lambda stock: stock.stock, "t"),
        ]
        for stock in mfa.stocks.values():
            for name, array_func, unit in config:
                df = self._iamc_raw_df(
                    vname_base=f"{vname_base}|stocks|{stock.name}|{name}",
                    array=array_func(stock),
                    detail=detail,
                    time_items=time_items,
                )
                df["unit"] = unit
                df_list.append(df)

    def _iamc_raw_trades(self, mfa, vname_base, detail, time_items, df_list):
        config = [
            ("export", lambda trade: trade.exports),
            ("import", lambda trade: trade.imports),
        ]
        for name, trade in mfa.trade_set.markets.items():
            for direction, array_func in config:
                df = self._iamc_raw_df(
                    vname_base=f"{vname_base}|trades|{name}|{direction}",
                    array=array_func(trade),
                    detail=detail,
                    time_items=time_items,
                )
                df["unit"] = "t/yr"
                df_list.append(df)

    def _iamc_raw_parameters(self, mfa: fd.MFASystem, vname_base, time_items, df_list):
        for name, unit in self.iamc_raw_parameters.items():
            param = mfa.parameters[name]
            if not isinstance(param, fd.FlodymArray):
                logging.warning(
                    f"Raw IAMC export: Skipping non-FlodymArray parameter {param.name} of type {type(param)}"
                )
                continue
            if "h" in param.dims:
                logging.warning(
                    f"Raw IAMC export: Skipping parameter {param.name} with historical dim"
                )
                continue
            dims = mfa.dims["t", "r"].union_with(mfa.parameters[name].dims)
            param = param.cast_to(dims)
            df = self._fd_array_to_df_for_iamc(
                f"{vname_base}|parameters|{name}", param, time_items, split_dims="all"
            )
            df["unit"] = unit
            df_list.append(df)

    def _warn_if_iamc_includes_historical(self, time_items: list, export_name: str):
        """Warn if the configured IAMC export range covers historical years.

        Historical years derive partly from proprietary input data (e.g. WorldSteel), so
        including them in a shared output risks leaking that data. The last historical year is
        taken per-material from the model's historical time dimension.
        """
        last_historical_year = self._model.dims["h"].items[-1]
        historical = [y for y in time_items if y <= last_historical_year]
        if historical:
            logging.warning(
                f"{export_name} range includes historical years ({historical[0]}-{last_historical_year}), "
                "which may derive from proprietary input data (e.g. WorldSteel). "
                "Verify you are permitted to share these years before distributing the output."
            )

    def _build_all_iamc_df(
        self,
        mfa: "CommonMFASystem",
        iamc_vars: list[IamcVariable],
        constants: dict,
        time_items: list,
    ) -> tuple[pyam.IamDataFrame, dict[str, list[str]], dict[str, str]]:
        """Build one IamDataFrame per iamc variable and concatenate them.

        Also collects two side-tables consumed by the later aggregation steps:

        - ``split_parent_components`` maps each ``split_dims`` parent variable to the exact child
        variables produced by its split, so the parent is summed from those children
        only. Relying on pyam's default (all direct children of the parent path) would
        wrongly pull in sibling variables under the same path, e.g. "…|Plastics|Per Capita".
        - ``region_weights`` lists variables aggregated to "World" as a weighted mean
        instead of a plain sum (e.g. per-capita variables weighted by Population),
        mapping variable -> weight variable.
        """
        import pyam  # deferred: slow to import

        iamc_dataframes = []
        split_parent_components: dict[str, list[str]] = {}
        region_weights: dict[str, str] = {}
        for iamc_var in iamc_vars:
            iamc_df, variables = self._iamc_var_to_iamc_df(mfa, iamc_var, constants, time_items)
            iamc_dataframes.append(iamc_df)
            if iamc_var.split_dims is not None and iamc_var.aggregate_parent:
                if iamc_var.variable_name in split_parent_components:
                    raise ValueError(
                        f"'{iamc_var.variable_name}' is aggregated from more than one split "
                        f"(latest via split_dims='{iamc_var.split_dims}'). Each split sums to the "
                        f"full parent total, so aggregating from two would double-count it. Set "
                        f"aggregate_parent=False on all but one orthogonal split of this variable."
                    )
                split_parent_components[iamc_var.variable_name] = variables
            if iamc_var.region_weight is not None:
                region_weights.update({v: iamc_var.region_weight for v in variables})
        return pyam.concat(iamc_dataframes), split_parent_components, region_weights

    def _aggregate_iamc_variables(
        self, iamc_dataframe: pyam.IamDataFrame, split_parent_components: dict[str, list[str]]
    ):
        """Sum child variables into their parents (variable-axis aggregation).

        Parents come from two sources:
        - ``split_dims`` variables were split into children on export, so each is summed back
          to its parent from exactly the children it produced.
        - ``iamc_aggregates`` adds further parents whose children are separate iamc variables
          (e.g. summing sibling "…|Primary" and "…|Secondary" variables).
        """
        for parent, components in split_parent_components.items():
            iamc_dataframe.aggregate(variable=parent, components=components, append=True)
        for parent in self.iamc_aggregates():
            if parent in split_parent_components:
                continue
            iamc_dataframe.aggregate(variable=parent, append=True)

    def _aggregate_iamc_regions(
        self, iamc_dataframe: pyam.IamDataFrame, region_weights: dict[str, str]
    ):
        """Aggregate regional values to "World".

        Most variables are summed across regions. Per-capita (and other weighted)
        variables are aggregated as a weighted mean instead, so e.g. World per-capita
        demand is World total demand / World population rather than the sum of the
        regional per-capita values.
        """
        plain_vars = [v for v in iamc_dataframe.variable if v not in region_weights]
        iamc_dataframe.aggregate_region(variable=plain_vars, region="World", append=True)
        for variable, weight in region_weights.items():
            iamc_dataframe.aggregate_region(
                variable=variable, region="World", weight=weight, append=True
            )

    def _convert_iamc_units(self, iamc_dataframe: pyam.IamDataFrame):
        """Convert the model's base units to the reporting units used in IAMC output."""

        # all units:
        # {'-', 't', 't/sqm', 'm', 'cap', 'sqm', 'yr', '$/cap/yr', 't/yr', '1/yr'}

        conversions = [
            {"current": "t/yr", "to": "Mt/yr"},
            {"current": "t", "to": "Mt"},
            {"current": "t/cap/yr", "to": "kg/cap/yr", "factor": 1000},
            {"current": "sqm", "to": "Gsqm", "factor": 1e-9},
            {"current": "t/sqm", "to": "Mt/Gsqm", "factor": 1e3},
        ]

        for conv in conversions:
            iamc_dataframe.convert_unit(**conv, inplace=True)

    def _iamc_var_to_iamc_df(
        self, mfa: CommonMFASystem, iamc_var: IamcVariable, constants: dict, time_items: list
    ) -> tuple[pyam.IamDataFrame, list[str]]:
        """Build the IamDataFrame for a iamc variable and return it with the variable names it produced."""
        import pyam  # deferred: slow to import

        df = self._fd_array_to_df_for_iamc(
            vname_base=iamc_var.variable_name,
            array=iamc_var.calculation_function(mfa),
            time_items=time_items,
            split_dims=iamc_var.split_dims,
        )
        variables = list(dict.fromkeys(df["variable"]))
        return pyam.IamDataFrame(df, unit=iamc_var.unit, **constants), variables

    def _iamc_raw_df(
        self,
        vname_base: str,
        array: fd.FlodymArray,
        detail: Literal["aggregated", "complete"],
        time_items: list,
    ) -> pd.DataFrame:
        """Aggregated variable, plus all split components if ``detail`` is "complete"."""
        df_agg = self._fd_array_to_df_for_iamc(vname_base, array, time_items, split_dims=None)
        if detail == "aggregated" or array.dims.letters == ("t", "r"):
            return df_agg
        df_complete = self._fd_array_to_df_for_iamc(vname_base, array, time_items, split_dims="all")
        return pd.concat([df_agg, df_complete], ignore_index=True)

    def _fd_array_to_df_for_iamc(
        self,
        vname_base: str,
        array: fd.FlodymArray,
        time_items: list,
        split_dims: Optional[list[str] | Literal["all"]] = None,
    ) -> pd.DataFrame:

        require_dims_err_msg = (
            f"Array {array.name} must include 't' or 'h' and 'r' dimensions for IAMC export"
        )
        if "r" not in array.dims:
            raise ValueError(require_dims_err_msg)
        if ("t" in array.dims) + ("h" in array.dims) != 1:
            raise ValueError(require_dims_err_msg)
        base_dims = ("t", "r") if "t" in array.dims else ("h", "r")

        if split_dims is None:
            split_dims = []
        elif split_dims == "all":
            split_dims = [dim.name for dim in array.dims if dim.letter not in ("h", "t", "r")]

        array = array.sum_to(base_dims + tuple(split_dims))

        df = self.to_iamc_df(array, time_items)
        df = self._merge_index_columns(df, array.dims, vname_base)
        return df

    def _merge_index_columns(
        self, df: "pd.DataFrame", dims: fd.DimensionSet, base_name: str
    ) -> "pd.DataFrame":
        names = [dim.name for dim in dims if dim.letter not in ("h", "t", "r")]
        df["variable"] = base_name
        for name in names:
            df["variable"] += "|" + df[name].astype(str)
            df = df.drop(columns=name)
        return df

    def get_mrindustry_variables(self) -> list[RemindInputVariable]:
        """Return the variables to export as REMIND input. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_mrindustry_variables method")

    def write_mrindustry(self):
        """Write material flows needed as inputs to REMIND."""
        export_dir = Path(self.export_path("mrindustry"))
        if export_dir.exists() and export_dir.is_dir():
            shutil.rmtree(export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)

        for variable in self.get_mrindustry_variables():
            array = variable.calculation_function(self._model.future_mfa)
            self._check_mrindustry_values(variable.name, array)
            df = array.to_df().rename(columns={"value": variable.name})
            df.to_csv(self.export_path("mrindustry", f"{variable.name}.csv"))

    @staticmethod
    def _check_mrindustry_values(name: str, array: fd.FlodymArray, n_items_shown: int = 5):
        """Check that a REMIND input variable is free of NaN and negative values.

        Args:
            name (str): Name of the variable, used in the error message.
            array (fd.FlodymArray): Values of the variable.
            n_items_shown (int): Number of offending dimension items listed in the error message.

        Raises:
            ValueError: If the variable contains NaN or negative values.
        """
        for problem, condition in (
            ("NaN", np.isnan),
            ("negative", lambda values: values < 0),
        ):
            items = array.items_where(condition)
            if len(items):
                shown = ", ".join(
                    f"({', '.join(str(value) for value in item)})" for item in items[:n_items_shown]
                )
                raise ValueError(
                    f"mrindustry variable '{name}' has {len(items)} {problem} values, "
                    f"e.g. at ({', '.join(array.dims.names)}) = {shown}."
                )

    def definition_to_markdown(self, definition: RemindMFADefinition):

        if not self.cfg.docs.do_export:
            return

        dfs = definition.to_dfs()

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
            return self._docs_cell_str(cell)

        for name, df in dfs.items():
            df.columns = [self.display_names[col] for col in df.columns]
            columns_to_convert = list(df.columns)
            if name == "parameters":
                # sources are matched by internal parameter name, so before converting the names
                df = self.merge_parameters_sources(params_df=df)
            df[columns_to_convert] = df[columns_to_convert].map(convert_cell)
            write_docs_file(
                self.model_docs_path / f"definitions/{name}.md", df.to_markdown(index=False)
            )

    def merge_bibtex_files(self):
        """Compatibility wrapper used previously; merges two default files."""
        src1 = self._model.data_reader.parameters_path / "mrmfa_sources.bib"
        src2 = DOCS_PATH / "custom_refs.bib"
        out = DOCS_PATH / "all_refs.bib"
        merge_bib_files([src1, src2], out)

    def merge_parameters_sources(self, params_df: pd.DataFrame) -> pd.DataFrame:
        """Add a "Sources" column to the parameters table, matched by the "Name" column."""
        sources_df = pd.read_csv(self._model.data_reader.parameters_path / "mrmfa_sources.csv")
        return merge_parameters_sources(
            sources_df=sources_df, params_df=params_df, prefix=self._model.name[:2]
        )

    def assumptions_to_markdown(self):

        if not self.cfg.docs.do_export:
            return

        df = assumptions_df()
        write_docs_file(self.model_docs_path / "assumptions.md", df.to_markdown(index=False))

    def cfg_to_markdown(self, cfg: "CommonCfg"):

        if not self.cfg.docs.do_export:
            return

        schema_df = type(cfg).to_schema_df()
        schema_df.columns = [self.display_names[col] for col in schema_df.columns]
        schema_df = schema_df.map(
            lambda cell: "" if str(cell) == "PydanticUndefined" else self._docs_cell_str(cell)
        )
        write_docs_file(
            self.model_docs_path / "config_schema.md", schema_df.to_markdown(index=False)
        )

    def scenario_parameters_to_markdown(self):
        """Write the lists of common and model-specific scenario parameter definitions to the docs
        folders, and update the corresponding generated sections of the scenario README.

        Names are kept internal (no display names), since they are used in the scenario CSVs.
        """

        if not self.cfg.docs.do_export:
            return

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

    def _docs_cell_str(self, cell: Any) -> str:
        """String of a docs table cell, with internal names replaced by display names if configured."""
        if not self.cfg.docs.apply_mappings:
            return str(cell)
        return self.display_names[str(cell)].replace("<br>", " ")

    def to_iamc_df(self, array: fd.FlodymArray, time_items: list):
        time_out = fd.Dimension(name="Time Out", letter="O", items=time_items)
        time_letter = "t" if "t" in array.dims else "h"
        df = array[{time_letter: time_out}].to_df(dim_to_columns="Time Out", index=False)
        df = df.rename(columns={"Region": "region"})
        return df

    def run_path(self) -> str:
        """Per-model-run export folder, created once and shared by exporter and visualizer."""
        if self._run_path is None:
            if self.cfg.bundle_export:
                self.cfg.path = series_export_path(self.cfg.path, self.cfg.prefix)
            name = (
                f"{export_dir_prefix(self._model.cfg.export.prefix)}_{self._model.name}_"
                f"{self._model.cfg.model_switches.scenario}_{self._model.cfg.input.region_mapping}"
            )
            self._run_path = os.path.join(self.cfg.path, name)
            Path(self._run_path).mkdir(parents=True, exist_ok=True)
        return self._run_path

    def export_path(self, dataset: str, filename: str | None = None) -> str:
        if not hasattr(self.cfg, dataset):
            raise ValueError(f"Dataset {dataset} not found in config")

        if dataset in self.FLAT_DATASETS:
            base_dir = self.run_path()
        else:
            base_dir = os.path.join(self.run_path(), dataset)

        if not os.path.isdir(base_dir):
            Path(base_dir).mkdir(parents=True, exist_ok=True)

        if filename is None:
            return base_dir
        return os.path.join(base_dir, filename)

    @property
    def model_docs_path(self) -> str:
        """Per-model-run export folder for docs, created once and shared by exporter and visualizer."""
        return DOCS_PATH / self._model.name
