import os
import flodym as fd


from remind_mfa.common.common_cfg import GeneralCfg
from .plastics_mfa_system import PlasticsMFASystem
from .plastics_export import PlasticsDataExporter
from .plastics_definition import get_definition
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.custom_data_reader import CustomDataReader

class PlasticsModel:

    def __init__(self, cfg: GeneralCfg):
        self.cfg = cfg
        self.definition = get_definition(cfg)
        self.data_reader = CustomDataReader(
            input_data_path=self.cfg.input_data_path, 
            definition=self.definition,
            allow_missing_values=True,
        )
        self.data_writer = PlasticsDataExporter(
            cfg=self.cfg.visualization,
            do_export=self.cfg.do_export,
            output_path=self.cfg.output_path,
        )

        self.dims = self.data_reader.read_dimensions(self.definition.dimensions)
        self.parameters = self.data_reader.read_parameters(
            self.definition.parameters, dims=self.dims
        )
        self.processes = fd.make_processes(self.definition.processes)

        self.make_plastics_mfa()

    def init_mfa(self):

        dimension_map = {
            "Time": "time_in_years",
            "Historic Time": "historic_years",
            "Element": "elements",
            "Region": "regions",
            "Material": "materials",
            "Good": "goods_in_use",
            "Intermediate": "intermediate_products",
            "Scenario": "scenarios",
        }

        dimension_files = {}
        for dimension in self.definition.dimensions:
            dimension_filename = dimension_map[dimension.name]
            dimension_files[dimension.name] = os.path.join(
                self.cfg.input_data_path, "dimensions", f"{dimension_filename}.csv"
            )

        parameter_files = {}
        for parameter in self.definition.parameters:
            parameter_files[parameter.name] = os.path.join(
                self.cfg.input_data_path, "datasets", f"{parameter.name}.csv"
            )
        self.mfa = PlasticsMFASystem.from_csv(
            definition=self.definition,
            dimension_files=dimension_files,
            parameter_files=parameter_files,
            allow_missing_parameter_values=True,
        )
        self.mfa.cfg = self.cfg

    def make_plastics_mfa(self) -> PlasticsMFASystem:

        dimension_map = {
            "Time": "time_in_years",
            "Historic Time": "historic_years",
            "Element": "elements",
            "Region": "regions",
            "Material": "materials",
            "Good": "goods_in_use",
            "Intermediate": "intermediate_products",
            "Scenario": "scenarios",
        }

        dimension_files = {}
        for dimension in self.definition.dimensions:
            dimension_filename = dimension_map[dimension.name]
            dimension_files[dimension.name] = os.path.join(
                self.cfg.input_data_path, "dimensions", f"{dimension_filename}.csv"
            )

        parameter_files = {}
        for parameter in self.definition.parameters:
            parameter_files[parameter.name] = os.path.join(
                self.cfg.input_data_path, "datasets", f"{parameter.name}.csv"
            )

        flows = fd.make_empty_flows(
            processes=self.processes,
            flow_definitions=[f for f in self.definition.flows if "t" in f.dim_letters],
            dims=self.dims,
        )
        stocks = fd.make_empty_stocks(
            processes=self.processes,
            stock_definitions = [s for s in self.definition.stocks if any(d in s.dim_letters for d in ("t", "h"))],
            dims=self.dims,
        )

        trade_set = TradeSet.from_definitions(
            definitions=[td for td in self.definition.trades if any(d in td.dim_letters for d in ("t", "h"))],
            dims=self.dims,
        )

        return PlasticsMFASystem(
            dims=self.dims,
            parameters=self.parameters,
            processes=self.processes,
            flows=flows,
            stocks=stocks,
            trade_set=trade_set,
            cfg=self.cfg,
        )
    
    def run(self):
        self.mfa = self.make_plastics_mfa()
        self.mfa.compute()
        self.data_writer.export_mfa(mfa=self.mfa)
        self.data_writer.visualize_results(model=self)
