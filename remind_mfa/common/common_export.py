import logging
import os
import pickle
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Optional

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
from remind_mfa.common.helpers import RemindMFABaseModel, timestamp_prefix

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

    def export(self, model: "CommonModel"):
        if not self.cfg.do_export:
            return
        self._model = model
        self.export_common(model)
        self.export_custom(model)

    def export_common(self, model: "CommonModel"):
        mfa = model.future_mfa
        if self.cfg.pickle.do_export:
            pickle.dump(model, open(self.export_path("pickle", "model.pickle"), "wb"))
        if self.cfg.csv.do_export:
            dir_out = self.export_path("csv", "flows")
            fde.export_mfa_flows_to_csv(mfa=mfa, export_directory=dir_out)
            fde.export_mfa_stocks_to_csv(mfa=mfa, export_directory=dir_out)
        if self.cfg.mrindustry.do_export:
            self.write_mrindustry(model=model)
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

    def run_path(self, model: "CommonModel") -> str:
        """Per-model-run export folder, created once and shared by exporter and visualizer."""
        if self._run_path is None:
            name = (
                f"{timestamp_prefix()}{model.cfg.model.value}_"
                f"{model.cfg.model_switches.scenario}_{model.cfg.input.region_mapping}"
            )
            self._run_path = os.path.join(self.cfg.path, name)
            os.makedirs(self._run_path, exist_ok=True)
        return self._run_path

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

    def write_iamc(self, model: "CommonModel"):
        iamc_vars = self.iamc_variables()
        if not iamc_vars:
            return
        iamc_vars = self.common_iamc_variables() + iamc_vars

        self._warn_if_iamc_includes_historic(model)

        mfa = model.future_mfa
        constants = {"model": self.model_name, "scenario": model.cfg.model_switches.scenario}

        iamc_dataframe, split_parent_components, region_weights = self._build_all_iamc_df(
            mfa, iamc_vars, constants
        )

        self._aggregate_iamc_variables(iamc_dataframe, split_parent_components)
        self._aggregate_iamc_regions(iamc_dataframe, region_weights)
        self._convert_iamc_units(iamc_dataframe)

        iamc_dataframe.to_excel(self.export_path("iamc", "output_iamc.xlsx"))

    def _warn_if_iamc_includes_historic(self, model: "CommonModel"):
        """Warn if the configured IAMC export range covers historic years.

        Historic years derive partly from proprietary input data (e.g. WorldSteel), so
        including them in a shared output risks leaking that data. The last historic year is
        taken per-material from the model's historic time dimension.
        """
        last_historic_year = model.dims["h"].items[-1]
        historic = [y for y in self.cfg.iamc.time_items if y <= last_historic_year]
        if historic:
            logging.warning(
                f"IAMC export range includes historic years ({historic[0]}-{last_historic_year}), "
                "which may derive from proprietary input data (e.g. WorldSteel). "
                "Verify you are permitted to share these years before distributing the output."
            )

    def _build_all_iamc_df(
        self, mfa: "CommonMFASystem", iamc_vars: list, constants: dict
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
            iamc_df, variables = self._build_iamc_df(mfa, iamc_var, constants)
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

    def get_mrindustry_variables(self) -> list[RemindInputVariable]:
        """Return the variables to export as REMIND input. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_mrindustry_variables method")

    def write_mrindustry(self, model: "CommonModel"):
        """Write material flows needed as inputs to REMIND."""
        export_dir = Path(self.export_path("mrindustry"))
        if export_dir.exists() and export_dir.is_dir():
            shutil.rmtree(export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)

        for variable in self.get_mrindustry_variables():
            df = (
                variable.calculation_function(model.future_mfa)
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
            base_dir = self.run_path(self._model)
        else:
            base_dir = os.path.join(self.run_path(self._model), dataset)

        os.makedirs(base_dir, exist_ok=True)

        if filename is None:
            return base_dir
        return os.path.join(base_dir, filename)

    def to_iamc_df(self, array: fd.FlodymArray):
        time_out = fd.Dimension(name="Time Out", letter="O", items=self.cfg.iamc.time_items)
        df = array[{"t": time_out}].to_df(dim_to_columns="Time Out", index=False)
        df = df.rename(columns={"Region": "region"})
        return df
