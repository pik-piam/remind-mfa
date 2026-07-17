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

        mfa = model.future_mfa
        constants = {"model": self.model_name, "scenario": model.cfg.model_switches.scenario}

        idf = pyam.concat([self._build_idf(mfa, spec, constants) for spec in specs])

        # A `per` variable is split into children on export, so sum it back to its parent.
        # `iamc_aggregates` adds any further parents (e.g. summing sibling variables).
        per_parents = [spec.variable for spec in specs if spec.per is not None]
        for parent in dict.fromkeys(per_parents + self.iamc_aggregates()):
            idf.aggregate(variable=parent, append=True)

        idf.aggregate_region(variable=idf.variable, region="World", append=True)

        idf.convert_unit(current="t/yr", to="Mt/yr", inplace=True)
        idf.convert_unit(current="t", to="Mt", inplace=True)

        idf.to_excel(self.export_path("iamc", "output_iamc.xlsx"))

    def _build_idf(
        self, mfa: "CommonMFASystem", spec: IamcVariable, constants: dict
    ) -> pyam.IamDataFrame:
        df = self.to_iamc_df(spec.getter(mfa))
        if spec.per is not None:
            df["variable"] = spec.variable + "|" + df[spec.per]
            df = df.drop(columns=[spec.per])
        else:
            df["variable"] = spec.variable
        return pyam.IamDataFrame(df, unit=spec.unit, **constants)

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
        time_items = list(range(2025, 2101))  # TODO: more flexible
        time_out = fd.Dimension(name="Time Out", letter="O", items=time_items)
        df = array[{"t": time_out}].to_df(dim_to_columns="Time Out", index=False)
        df = df.rename(columns={"Region": "region"})
        return df
