import numpy as np
import flodym as fd

from simson.common.common_cfg import CommonCfg
from simson.cement.cement_definition import get_definition
from simson.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem
from simson.cement.cement_data_reader import CementDataReader
from simson.cement.cement_export import CementDataExporter

class CementModel:

    def __init__(self, cfg: CommonCfg):
        self.cfg = cfg
        self.definition = get_definition(self.cfg)
        self.data_reader = CementDataReader(
            input_data_path=self.cfg.input_data_path, definition=self.definition
        )
        self.data_writer = CementDataExporter(
            **dict(self.cfg.visualization),
            output_path=self.cfg.output_path,
        )
        self.dims = self.data_reader.read_dimensions(self.definition.dimensions)
        self.parameters = self.data_reader.read_parameters(
            self.definition.parameters, dims=self.dims
        )
        self.processes = fd.make_processes(self.definition.processes)

    def run(self):
        self.historic_mfa = self.make_historic_mfa()
        self.historic_mfa.compute()

        self.data_writer.export_mfa(mfa=self.historic_mfa)
        self.data_writer.visualize_results(mfa=self.historic_mfa)

        # TODO future mfa

        # TODO visualize future mfa
        #self.data_writer.export_mfa(mfa=self.future_mfa)
        #self.data_writer.visualize_results(mfa=self.future_mfa)

    def make_historic_mfa(self) -> InflowDrivenHistoricCementMFASystem:

        historic_dim_letters = tuple([d for d in self.dims.letters if d != "t"])
        historic_dims = self.dims[historic_dim_letters]
        historic_processes = [
            "sysenv",
            "raw_meal_preparation",
            "clinker_production",
            "cement_grinding",
            "concrete_production",
            "use",
            "eol",
        ]
        processes = fd.make_processes(historic_processes)
        flows = fd.make_empty_flows(
            processes=processes,
            flow_definitions=[f for f in self.definition.flows if "h" in f.dim_letters],
            dims=historic_dims,
        )
        stocks = fd.make_empty_stocks(
            processes=processes,
            stock_definitions=[s for s in self.definition.stocks if "h" in s.dim_letters],
            dims=historic_dims,
        )

        return InflowDrivenHistoricCementMFASystem(
            cfg=self.cfg,
            parameters=self.parameters,
            processes=processes,
            dims=historic_dims,
            flows=flows,
            stocks=stocks,
        )
    