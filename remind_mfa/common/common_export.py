import os
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Callable, Optional, TYPE_CHECKING
import flodym as fd
import flodym.export as fde
import pickle
import pyam

from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.common.helpers import RemindMFABaseModel
from remind_mfa.common.common_config import ExportCfg
from remind_mfa.common.assumptions_doc import assumptions_str, assumptions_df
from remind_mfa.common.common_mappings import CommonDisplayNames
from remind_mfa.common.common_config import CommonCfg
from remind_mfa.common.common_mfa_system import CommonMFASystem

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
    split_name: Optional[str] = None
    """Display-column name to split into child variables (e.g. "Good"). None = single variable."""
    region_weight: Optional[str] = None
    """Variable to weight by when aggregating to "World" (e.g. "Population" for per-capita
    variables). None = plain sum across regions."""


class CommonDataExporter(RemindMFABaseModel):
    cfg: ExportCfg
    display_names: CommonDisplayNames

    def export(self, model: "CommonModel"):
        if not self.cfg.do_export:
            return
        self.export_common(model)
        self.export_custom(model)

    def export_common(self, model: "CommonModel"):
        mfa = model.future_mfa
        if self.cfg.pickle.do_export:
            fde.export_mfa_to_pickle(mfa=mfa, export_path=self.export_path("pickle", "mfa.pickle"))
            self.export_model_to_pickle(model=model)
            pickle.dump(model, open(self.export_path("pickle", "model.pickle"), "wb"))
        if self.cfg.csv.do_export:
            dir_out = self.export_path("csv", "flows")
            fde.export_mfa_flows_to_csv(mfa=mfa, export_directory=dir_out)
            fde.export_mfa_stocks_to_csv(mfa=mfa, export_directory=dir_out)
        if self.cfg.assumptions.do_export:
            file_out = self.export_path("assumptions", "assumptions.txt")
            with open(file_out, "w") as f:
                f.write(assumptions_str())
        if self.cfg.docs.do_export:
            self.definition_to_markdown(model.definition_future)
            self.assumptions_to_markdown()
            self.cfg_to_markdown(cfg=model.cfg)
        if self.cfg.iamc.do_export:
            self.write_iamc(model=model)

    def export_custom(self, model: "CommonModel"):
        pass

    def export_model_to_pickle(self, model: "CommonModel"):
        material = model.cfg.model.value
        scenario = model.cfg.model_switches.scenario
        region_mapping = model.cfg.input.region_mapping
        datetime_str = datetime.now().strftime("%Y-%m-%d--%H-%M-%S")
        filename = f"model_{material}_{scenario}_{region_mapping}_{datetime_str}.pickle"
        export_path = self.export_path("pickle", filename)
        with open(export_path, "wb") as f:
            pickle.dump(model, f)

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
        """Material-specific IAMC variable specifications. Override in subclasses."""
        return []

    def iamc_aggregates(self) -> list[str]:
        """Extra parent variables to aggregate, beyond the automatic per-split parents.

        Variables declared with a ``per`` dimension are summed back to their parent
        automatically. Use this only for parents whose children are separate specs rather
        than a ``per`` split (e.g. summing "…|Primary" and "…|Secondary" into their parent).
        Override in subclasses.
        """
        return []

    def write_iamc(self, model: "CommonModel"):
        iamc_vars = self.iamc_variables()
        if not iamc_vars:
            return
        iamc_vars = self.common_iamc_variables() + iamc_vars

        mfa = model.future_mfa
        constants = {"model": self.model_name, "scenario": model.cfg.model_switches.scenario}

        iamc_dataframe, split_parent_components, region_weights = self._build_iamc_dataframe(
            mfa, iamc_vars, constants
        )

        self._aggregate_iamc_variables(iamc_dataframe, split_parent_components)
        self._aggregate_iamc_regions(iamc_dataframe, region_weights)
        self._convert_iamc_units(iamc_dataframe)

        iamc_dataframe.to_excel(self.export_path("iamc", "output_iamc.xlsx"))

    def _build_iamc_dataframe(
        self, mfa: "CommonMFASystem", iamc_vars: list, constants: dict
    ) -> tuple[pyam.IamDataFrame, dict[str, list[str]], dict[str, str]]:
        """Build one IamDataFrame per variable spec and concatenate them.

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
            iamc_df, variables = self._build_iamc_df(mfa, iamc_var, constants)
            iamc_dataframes.append(iamc_df)
            if iamc_var.split_name is not None:
                split_parent_components.setdefault(iamc_var.variable_name, []).extend(variables)
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

    def _build_iamc_df(
        self, mfa: CommonMFASystem, iamc_var: IamcVariable, constants: dict
    ) -> tuple[pyam.IamDataFrame, list[str]]:
        """Build the IamDataFrame for a iamc variable and return it with the variable names it produced."""
        df = self.to_iamc_df(iamc_var.calculation_function(mfa))
        df["variable"] = iamc_var.variable_name
        if iamc_var.split_name is not None:
            df["variable"] += "|" + df[iamc_var.split_name]
            df = df.drop(columns=[iamc_var.split_name])

        variables = list(dict.fromkeys(df["variable"]))
        return pyam.IamDataFrame(df, unit=iamc_var.unit, **constants), variables

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

    def export_path(self, dataset: str, filename: str = None):
        if not hasattr(self.cfg, dataset):
            raise ValueError(f"Dataset {dataset} not found in config")
        cfg_path = getattr(self.cfg, dataset).path

        if cfg_path is not None:
            path_tuple = (cfg_path,)
        else:
            path_tuple = (self.cfg.path, dataset)

        base_dir = os.path.join(*path_tuple)
        if not os.path.isdir(base_dir):
            os.mkdir(base_dir)

        if filename is not None:
            path_tuple += (filename,)

        return os.path.join(*path_tuple)

    @staticmethod
    def to_iamc_df(array: fd.FlodymArray):
        time_items = list(range(1950, 2101))  # TODO: more flexible
        time_out = fd.Dimension(name="Time Out", letter="O", items=time_items)
        df = array[{"t": time_out}].to_df(dim_to_columns="Time Out", index=False)
        df = df.rename(columns={"Region": "region"})
        return df
