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

if TYPE_CHECKING:
    from remind_mfa.common.common_model import CommonModel
    from remind_mfa.common.common_config import CommonCfg
    from remind_mfa.common.common_mfa_system import CommonMFASystem


class IamcVariable(RemindMFABaseModel):
    """Declarative specification of a single IAMC output variable."""

    variable: str
    """IAMC variable path, e.g. "Production|Iron and Steel|Steel"."""
    getter: Callable[..., fd.FlodymArray]
    """Given the future MFA system, returns the array to report, reduced to (t, r) or (t, r, <per-dim>)."""
    unit: str
    """Base unit of the array, e.g. "t/yr" or "t"."""
    per: Optional[str] = None
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
                variable="Population",
                getter=lambda mfa: mfa.parameters["population"].sum_to(("t", "r")),
                unit="cap",
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
        specs = self.iamc_variables()
        if not specs:
            return
        specs = self.common_iamc_variables() + specs

        mfa = model.future_mfa
        constants = {"model": self.model_name, "scenario": model.cfg.model_switches.scenario}

        idfs = []
        # Map each `per` parent to the exact child variables produced by its split, so the
        # parent is summed from those children only. Relying on pyam's default (all direct
        # children of the parent path) would wrongly pull in sibling variables that happen to
        # live under the same path, e.g. "…|Plastics|Per Capita".
        per_parent_components: dict[str, list[str]] = {}
        # Variables aggregated to "World" as a weighted mean instead of a plain sum
        # (e.g. per-capita variables weighted by Population). Maps variable -> weight variable.
        region_weights: dict[str, str] = {}
        for spec in specs:
            idf, variables = self._build_idf(mfa, spec, constants)
            idfs.append(idf)
            if spec.per is not None:
                per_parent_components.setdefault(spec.variable, []).extend(variables)
            if spec.region_weight is not None:
                region_weights.update({v: spec.region_weight for v in variables})

        idf = pyam.concat(idfs)

        # A `per` variable is split into children on export, so sum it back to its parent.
        for parent, components in per_parent_components.items():
            idf.aggregate(variable=parent, components=components, append=True)
        # `iamc_aggregates` adds any further parents whose children are separate specs
        # (e.g. summing sibling "…|Primary" and "…|Secondary" variables).
        for parent in self.iamc_aggregates():
            if parent in per_parent_components:
                continue
            idf.aggregate(variable=parent, append=True)

        # Sum most variables across regions to "World", but aggregate per-capita (and other
        # weighted) variables as a weight-weighted mean so, e.g., World per-capita demand is
        # World total demand / World population rather than the sum of regional per-capita values.
        plain_vars = [v for v in idf.variable if v not in region_weights]
        idf.aggregate_region(variable=plain_vars, region="World", append=True)
        for variable, weight in region_weights.items():
            idf.aggregate_region(variable=variable, region="World", weight=weight, append=True)

        idf.convert_unit(current="t/yr", to="Mt/yr", inplace=True)
        idf.convert_unit(current="t", to="Mt", inplace=True)
        idf.convert_unit(current="t/cap/yr", to="kg/cap/yr", factor=1000, inplace=True)

        idf.to_excel(self.export_path("iamc", "output_iamc.xlsx"))

    def _build_idf(
        self, mfa: "CommonMFASystem", spec: IamcVariable, constants: dict
    ) -> tuple[pyam.IamDataFrame, list[str]]:
        """Build the IamDataFrame for a spec and return it with the variable names it produced."""
        df = self.to_iamc_df(spec.getter(mfa))
        if spec.per is not None:
            df["variable"] = spec.variable + "|" + df[spec.per]
            df = df.drop(columns=[spec.per])
        else:
            df["variable"] = spec.variable
        variables = list(dict.fromkeys(df["variable"]))
        return pyam.IamDataFrame(df, unit=spec.unit, **constants), variables

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
