import logging
import os
import pickle
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, List, Literal, ClassVar
import pandas as pd
from pydantic import PrivateAttr

import flodym as fd
import flodym.export as fde
from pydantic import PrivateAttr

_root_logger = logging.getLogger()
_prev_level = _root_logger.level
_root_logger.setLevel(logging.WARNING)
import pyam  # noqa: E402

_root_logger.setLevel(_prev_level)
del _root_logger, _prev_level

from remind_mfa.common.assumptions_doc import assumptions_df, assumptions_str
from remind_mfa.common.common_config import CommonCfg, ExportCfg
from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.common.common_mappings import CommonDisplayNames
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.common.helpers import RemindMFABaseModel, series_export_path, export_dir_prefix

if TYPE_CHECKING:
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
    """When this variable is split (``split_name`` set), whether its children are summed back
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
    FLAT_DATASETS: ClassVar[set[str]] = {"pickle", "iamc", "assumptions"}

    _model: Optional["CommonModel"] = PrivateAttr(default=None)
    _run_path: Optional[str] = PrivateAttr(default=None)
    _riamc_only_agg: Optional[bool] = PrivateAttr(default=False)
    """If True, only export the aggregated variables, not the split components.
    Set by the write_riamc() method to avoid passing the flag through multiple layers of function calls.
    """

    def export(self, model: "CommonModel"):
        if not self.cfg.do_export:
            return
        self._model = model
        self.export_common()
        self.export_custom()

    def export_common(self):
        mfa = self._model.future_mfa
        if self.cfg.pickle.do_export:
            self._clear_recomputable_caches()
            pickle.dump(self._model, open(self.export_path("pickle", "model.pickle"), "wb"))
        if self.cfg.csv.do_export:
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
            self.assumptions_to_markdown()
            self.cfg_to_markdown(cfg=self._model.cfg)
        if self.cfg.iamc.do_export:
            # self.write_iamc(model=model)
            self.write_riamc(only_agg=True)
            self.write_riamc(only_agg=False)

    def export_custom(self):
        pass

    def run_path(self) -> str:
        """Per-model-run export folder, created once and shared by exporter and visualizer."""
        if self._run_path is None:
            if self.cfg.bundle_export:
                self.cfg.path = series_export_path(self.cfg.path, self.cfg.prefix)
            name = (
                f"{export_dir_prefix(self._model.cfg.export.prefix)}_{self._model.cfg.model.value}_"
                f"{self._model.cfg.model_switches.scenario}_{self._model.cfg.input.region_mapping}"
            )
            self._run_path = os.path.join(self.cfg.path, name)
            Path(self._run_path).mkdir(parents=True, exist_ok=True)
        return self._run_path

    def _clear_recomputable_caches(self):
        """Drop lifetime-model sf/pdf caches from the historic and future MFA stocks before pickling
        to save memory.

        These arrays (shape ``(n_t, n_t, ...)``) are read only through the ``sf``/``pdf``
        properties, which lazily recompute when the backing attribute is ``None`` -- so clearing
        them here is transparent: the next access (including any later ``stock.compute()``)
        rebuilds them from the stored lifetime parameters.
        """
        for mfa in (self._model.historic_mfa, self._model.future_mfa):
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

    def write_iamc(self):
        iamc_vars = self.iamc_variables()
        if not iamc_vars:
            return
        iamc_vars = self.common_iamc_variables() + iamc_vars

        self._warn_if_iamc_includes_historic()

        constants = self.iamc_constants(self._model)
        mfa = self._model.future_mfa

        iamc_dataframe, split_parent_components, region_weights = self._build_all_iamc_df(
            mfa, iamc_vars, constants
        )

        self._aggregate_iamc_variables(iamc_dataframe, split_parent_components)
        self._aggregate_iamc_regions(iamc_dataframe, region_weights)
        self._convert_iamc_units(iamc_dataframe)

        iamc_dataframe.to_excel(self.export_path("iamc", "output_iamc.xlsx"))

    def iamc_constants(self, model: "CommonModel") -> dict:
        """IAMC constants to include in every exported variable."""
        return {"model": self.model_name, "scenario": model.cfg.model_switches.scenario}

    def write_riamc(self, only_agg: bool = False):

        prefix = f"MFA|{self._model.cfg.model.value}"
        mfa = self._model.future_mfa
        vname_base = f"{prefix}|Future"

        self._riamc_only_agg = only_agg
        suffix = "agg" if only_agg else "complete"

        df_list = []
        self._write_riamc_flows(mfa, vname_base, df_list)
        self._write_riamc_stocks(mfa, vname_base, df_list)
        self._write_riamc_trades(mfa, vname_base, df_list)
        self._write_riamc_parameters(mfa, vname_base, df_list)

        df_out = pd.concat(df_list)

        constants = self.iamc_constants(self._model)
        # TODO: units
        pyam_df = pyam.IamDataFrame(df_out, unit="t/yr", **constants)
        self._convert_iamc_units(pyam_df)
        pyam_df.to_excel(self.export_path("iamc", f"output_iamc_raw_{suffix}.xlsx"))

    def _write_riamc_flows(self, mfa: fd.MFASystem, vname_base, df_list):
        for flow in mfa.flows.values():
            df = self._complete_and_agg(f"{vname_base}|Flows|{flow.name}", flow)
            df["unit"] = "t/yr"
            df_list.append(df)

    def _write_riamc_stocks(self, mfa, vname_base, df_list):
        config = [
            ("Inflow", lambda stock: stock.inflow, "t/yr"),
            ("Outflow", lambda stock: stock.outflow, "t/yr"),
            ("Stock", lambda stock: stock.stock, "t"),
        ]
        for stock in mfa.stocks.values():
            for name, array_func, unit in config:
                df = self._complete_and_agg(
                    vname_base=f"{vname_base}|Stocks|{stock.name}|{name}",
                    array=array_func(stock),
                )
                df["unit"] = unit
                df_list.append(df)

    def _write_riamc_trades(self, mfa, vname_base, df_list):
        config = [
            ("Exports", lambda trade: trade.exports),
            ("Imports", lambda trade: trade.imports),
        ]
        for name, trade in mfa.trade_set.markets.items():
            for name, array_func in config:
                df = self._complete_and_agg(
                    vname_base=f"{vname_base}|Trade|{name}|{name}",
                    array=array_func(trade),
                )
                df["unit"] = "t/yr"
                df_list.append(df)

    def _write_riamc_parameters(self, mfa: fd.MFASystem, vname_base, df_list):
        for name, param in mfa.parameters.items():
            if not isinstance(param, fd.FlodymArray):
                logging.warning(f"IAMC export: Skipping non-FlodymArray parameter {param.name} of type {type(param)}")
                continue
            if "h" in param.dims:
                logging.warning(f"IAMC export: Skipping parameter {param.name} with hostorical dim")
                continue
            dims =  mfa.dims["t", "r"].union_with(mfa.parameters[name].dims)
            param = param.cast_to(dims)
            df = self._complete_and_agg(
                vname_base=f"{vname_base}|Parameters|{name}",
                array=param,
            )
            df["unit"] = "unknown"
            df_list.append(df)

    def _warn_if_iamc_includes_historic(self):
        """Warn if the configured IAMC export range covers historic years.

        Historic years derive partly from proprietary input data (e.g. WorldSteel), so
        including them in a shared output risks leaking that data. The last historic year is
        taken per-material from the model's historic time dimension.
        """
        last_historic_year = self._model.dims["h"].items[-1]
        historic = [y for y in self.cfg.iamc.time_items if y <= last_historic_year]
        if historic:
            logging.warning(
                f"IAMC export range includes historic years ({historic[0]}-{last_historic_year}), "
                "which may derive from proprietary input data (e.g. WorldSteel). "
                "Verify you are permitted to share these years before distributing the output."
            )

    def _build_all_iamc_df(
        self, mfa: "CommonMFASystem", iamc_vars: list[IamcVariable], constants: dict
    ) -> tuple[pyam.IamDataFrame, dict[str, list[str]], dict[str, str]]:
        """Build one IamDataFrame per iamc variable and concatenate them.

        Also collects two side-tables consumed by the later aggregation steps:

        - ``split_parent_components`` maps each ``split_name`` parent variable to the exact child
        variables produced by its split, so the parent is summed from those children
        only. Relying on pyam's default (all direct children of the parent path) would
        wrongly pull in sibling variables under the same path, e.g. "…|Plastics|Per Capita".
        - ``region_weights`` lists variables aggregated to "World" as a weighted mean
        instead of a plain sum (e.g. per-capita variables weighted by Population),
        mapping variable -> weight variable.
        """
        iamc_dataframes = []
        split_parent_components: dict[str, list[str]] = {}
        region_weights: dict[str, str] = {}
        for iamc_var in iamc_vars:
            iamc_df, variables = self._iamc_var_to_iamc_df(mfa, iamc_var, constants)
            iamc_dataframes.append(iamc_df)
            if iamc_var.split_name is not None and iamc_var.aggregate_parent:
                if iamc_var.variable_name in split_parent_components:
                    raise ValueError(
                        f"'{iamc_var.variable_name}' is aggregated from more than one split "
                        f"(latest via split_name='{iamc_var.split_name}'). Each split sums to the "
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
        - ``split_name`` variables were split into children on export, so each is summed back
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
        iamc_dataframe.convert_unit(current="t/yr", to="Mt/yr", inplace=True)
        iamc_dataframe.convert_unit(current="t", to="Mt", inplace=True)
        iamc_dataframe.convert_unit(current="t/cap/yr", to="kg/cap/yr", factor=1000, inplace=True)

    def _iamc_var_to_iamc_df(
        self, mfa: CommonMFASystem, iamc_var: IamcVariable, constants: dict
    ) -> tuple[pyam.IamDataFrame, list[str]]:
        """Build the IamDataFrame for a iamc variable and return it with the variable names it produced."""
        df = self._fd_array_to_df_for_iamc(
            vname_base=iamc_var.variable_name,
            array=iamc_var.calculation_function(mfa),
            split_dims=iamc_var.split_dims,
        )
        variables = list(dict.fromkeys(df["variable"]))
        return pyam.IamDataFrame(df, unit=iamc_var.unit, **constants), variables

    def _complete_and_agg(
            self,
            vname_base: str,
            array: fd.FlodymArray,
        ) -> pd.DataFrame:
        df_agg = self._fd_array_to_df_for_iamc(vname_base, array, split_dims=None)
        if self._riamc_only_agg:
            return df_agg
        df_complete = self._fd_array_to_df_for_iamc(vname_base, array, split_dims="all")
        return pd.concat([df_agg, df_complete], ignore_index=True)

    def _fd_array_to_df_for_iamc(
            self,
            vname_base: str,
            array: fd.FlodymArray,
            split_dims: Optional[list[str] | Literal["all"]] = None,
        ) -> pd.DataFrame:

        require_dims_err_msg = f"Array {array.name} must include 't' or 'h' and 'r' dimensions for IAMC export"
        if "r" not in array.dims:
            raise ValueError(require_dims_err_msg)
        if ("t" in array.dims) +  ("h" in array.dims) != 1:
            raise ValueError(require_dims_err_msg)
        base_dims = ("t", "r") if "t" in array.dims else ("h", "r")

        if split_dims is None:
            split_dims = []
        elif split_dims == "all":
            split_dims = [dim.name for dim in array.dims if dim.letter not in ("h", "t", "r")]

        array = array.sum_to(base_dims + tuple(split_dims))

        df = self.to_iamc_df(array, self.cfg.iamc.time_items)
        df = self._merge_index_columns(df, array.dims, vname_base)
        return df

    def _merge_index_columns(self, df: "pd.DataFrame", dims: fd.DimensionSet,  base_name: str) -> "pd.DataFrame":
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
            df = (
                variable.calculation_function(self._model.future_mfa)
                .to_df()
                .rename(columns={"value": variable.name})
            )
            df.to_csv(self.export_path("mrindustry", f"{variable.name}.csv"))

    def definition_to_markdown(self, definition: RemindMFADefinition):

        if not self.cfg.docs.do_export:
            return

        dfs = definition.to_dfs()

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
            cell = self.display_names[str(cell)]
            return cell.replace("<br>", " ")

        for name, df in dfs.items():
            df.columns = [self.display_names[col] for col in df.columns]
            df = df.map(convert_cell)
            if name == "parameters":
                # Export parameters as CSV to merge with their source info later
                df.to_csv(self.export_path("docs", f"definitions/{name}.csv"), index=False)
            else:
                df.to_markdown(self.export_path("docs", f"definitions/{name}.md"), index=False)

    def assumptions_to_markdown(self):

        if not self.cfg.docs.do_export:
            return

        df = assumptions_df()
        df.to_markdown(self.export_path("docs", "assumptions.md"), index=False)

    def cfg_to_markdown(self, cfg: "CommonCfg"):

        if not self.cfg.docs.do_export:
            return

        schema_df = type(cfg).to_schema_df()
        schema_df = schema_df.map(lambda cell: self.display_names[str(cell)])
        schema_df.to_markdown(self.export_path("docs", "config_schema.md"), index=False)

    def export_path(self, dataset: str, filename: str | None = None) -> str:
        if not hasattr(self.cfg, dataset):
            raise ValueError(f"Dataset {dataset} not found in config")
        cfg_path = getattr(self.cfg, dataset).path

        if cfg_path is not None:
            base_dir = cfg_path
        elif dataset in self.FLAT_DATASETS:
            base_dir = self.run_path()
        else:
            base_dir = os.path.join(self.run_path(), dataset)

        if not os.path.isdir(base_dir):
            Path(base_dir).mkdir(parents=True, exist_ok=True)

        if filename is None:
            return base_dir
        return os.path.join(base_dir, filename)

    def to_iamc_df(self, array: fd.FlodymArray, time_items: list):
        time_out = fd.Dimension(name="Time Out", letter="O", items=time_items)
        time_letter = "t" if "t" in array.dims else "h"
        df = array[{time_letter: time_out}].to_df(dim_to_columns="Time Out", index=False)
        df = df.rename(columns={"Region": "region"})
        return df
