import os
from typing import Any, TYPE_CHECKING
from pydantic import model_validator
import flodym as fd
import flodym.export as fde

from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.common.helpers import RemindMFABaseModel
from remind_mfa.common.common_config import ExportCfg
from remind_mfa.common.assumptions_doc import assumptions_str, assumptions_df

if TYPE_CHECKING:
    from remind_mfa.common.common_model import CommonModel
    from remind_mfa.common.common_config import CommonCfg
    from remind_mfa.common.common_mfa_system import CommonMFASystem


class CommonDataExporter(RemindMFABaseModel):
    cfg: ExportCfg
    _display_names: dict = {
        # for markdown export
        "name": "Name",
        "letter": "Letter",
        "dim_letters": "Dimensions",
        "from_process_name": "Origin Process",
        "to_process_name": "Destination Process",
        "process_name": "Process",
        "subclass": "Stock Type",
        "lifetime_model_class": "Lifetime Model",
    }

    @model_validator(mode="after")
    def inherit_display_names(self):
        """
        Ensures that _display_names defined in a subclass are *merged* with
        the base class defaults, rather than replacing them entirely.
        """
        from_sub = self._display_names
        self._display_names = CommonDataExporter._display_names.default.copy()
        self._display_names.update(from_sub)
        return self

    def export(self, model: "CommonModel"):
        if not self.cfg.do_export:
            return
        self.export_common(model)
        self.export_custom(model)

    def export_common(self, model: "CommonModel"):
        mfa = model.future_mfa
        if self.cfg.pickle.do_export:
            fde.export_mfa_to_pickle(mfa=mfa, export_path=self.export_path("pickle", "mfa.pickle"))
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
            self.write_iamc(mfa=mfa)

    def export_custom(self, model: "CommonModel"):
        pass

    def write_iamc(self, mfa: "CommonMFASystem"):
        raise NotImplementedError("Subclasses must implement write_iamc method")

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
            cell = self.display_name(str(cell))
            return cell.replace("<br>", " ")

        for name, df in dfs.items():
            df.columns = [self.display_name(col) for col in df.columns]
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

    def display_name(self, name):
        return self._display_names.get(name, name)

    @staticmethod
    def to_iamc_df(array: fd.FlodymArray):
        time_items = list(range(2025, 2101))  # TODO: more flexible
        time_out = fd.Dimension(name="Time Out", letter="O", items=time_items)
        df = array[{"t": time_out}].to_df(dim_to_columns="Time Out", index=False)
        df = df.rename(columns={"Region": "region"})
        return df
