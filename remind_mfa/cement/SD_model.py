import flodym as fd

from remind_mfa.common.common_cfg import GeneralCfg
from remind_mfa.cement.cement_definition import get_definition

from remind_mfa.cement.cement_mfa_system_sd import StockDrivenSDcementMFASystem
from remind_mfa.cement.cement_data_reader import CementDataReader
from remind_mfa.cement.cement_export import CementDataExporter


class CementModel:

    def __init__(self, cfg: GeneralCfg):
        self.cfg = cfg
        self.definition = get_definition(self.cfg)
        self.data_reader = CementDataReader(
            input_data_path=self.cfg.input_data_path,
            definition=self.definition,
            allow_missing_values=True,
        )
        self.data_writer = CementDataExporter(
            cfg=self.cfg.visualization,
            do_export=self.cfg.do_export,
            output_path=self.cfg.output_path,
        )
        self.dims = self.data_reader.read_dimensions(self.definition.dimensions)
        self.parameters = self.data_reader.read_parameters(
            self.definition.parameters, dims=self.dims
        )
        self.processes = fd.make_processes(self.definition.processes)

    def run(self):
        # historic mfa
        self.sd_mfa = self.make_sd_mfa()
        self.sd_mfa.compute()

        # visualization and export
        self.data_writer.export_mfa(mfa=self.sd_mfa)
        self.data_writer.visualize_results(model=self)

    def make_sd_mfa(self) -> StockDrivenSDcementMFASystem:
        sd_dims = self.dims
        sd_processes = [
            "sysenv",
            "use",
        ]
        processes = fd.make_processes(sd_processes)
        flows = fd.make_empty_flows(
            processes=processes,
            flow_definitions=self.definition.flows,
            dims=sd_dims,
        )
        stocks = fd.make_empty_stocks(
            processes=processes,
            stock_definitions=self.definition.stocks,
            dims=sd_dims,
        )
        return StockDrivenSDcementMFASystem(
            cfg=self.cfg,
            parameters=self.parameters,
            processes=processes,
            dims=sd_dims,
            flows=flows,
            stocks=stocks,
        )
