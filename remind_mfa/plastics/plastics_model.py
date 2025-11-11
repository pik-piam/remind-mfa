import os
import flodym as fd


from remind_mfa.common.common_cfg import GeneralCfg
from .plastics_mfa_system import PlasticsMFASystemFuture
from .plastics_mfa_system_historic import PlasticsMFASystemHistoric
from .plastics_export import PlasticsDataExporter
from .plastics_definition import get_definition, PlasticsMFADefinition
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.custom_data_reader import CustomDataReader


class PlasticsModel:

    def __init__(self, cfg: GeneralCfg):
        self.cfg = cfg
        self.definition_historic = get_definition(cfg, historic=True)
        self.definition_future = get_definition(cfg, historic=False)
        self.read_data()
        self.data_writer = PlasticsDataExporter(
            cfg=self.cfg.visualization,
            do_export=self.cfg.do_export,
            output_path=self.cfg.output_path,
        )

    def read_data(self):

        self.data_reader = CustomDataReader(
            input_data_path=self.cfg.input_data_path,
            definition=self.definition_future,
            allow_missing_values=True,
            allow_extra_values=True,
        )

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
        for dimension in self.definition_future.dimensions:
            dimension_filename = dimension_map[dimension.name]
            dimension_files[dimension.name] = os.path.join(
                self.cfg.input_data_path, "dimensions", f"{dimension_filename}.csv"
            )

        parameter_files = {}
        for parameter in self.definition_future.parameters:
            parameter_files[parameter.name] = os.path.join(
                self.cfg.input_data_path, "datasets", f"{parameter.name}.csv"
            )

        # dims and parameters are the same for historic and future
        self.dims = self.data_reader.read_dimensions(self.definition_future.dimensions)
        self.parameters = self.data_reader.read_parameters(
            self.definition_future.parameters, dims=self.dims
        )

    def make_mfa(
        self, definition: PlasticsMFADefinition, mfasystem_class: type
    ) -> PlasticsMFASystemFuture:

        processes = fd.make_processes(definition.processes)

        flows = fd.make_empty_flows(
            processes=processes,
            flow_definitions=definition.flows,
            dims=self.dims,
        )
        stocks = fd.make_empty_stocks(
            processes=processes,
            stock_definitions=definition.stocks,
            dims=self.dims,
        )

        trade_set = TradeSet.from_definitions(
            definitions=definition.trades,
            dims=self.dims,
        )

        return mfasystem_class(
            dims=self.dims,
            parameters=self.parameters,
            processes=processes,
            flows=flows,
            stocks=stocks,
            trade_set=trade_set,
            cfg=self.cfg,
        )

    def run(self):
        self.mfa_historic = self.make_mfa(
            self.definition_historic, mfasystem_class=PlasticsMFASystemHistoric
        )
        self.mfa_future = self.make_mfa(
            self.definition_future, mfasystem_class=PlasticsMFASystemFuture
        )
        self.mfa_historic.compute()
        self.mfa_future.compute(
            historic_stock=self.mfa_historic.stocks["in_use_historic"],
            historic_trade=self.mfa_historic.trade_set,
        )
        self.data_writer.export_mfa(model=self)
        self.data_writer.definition_to_markdown(definition=self.definition_future)
        self.data_writer.assumptions_to_markdown()
        self.data_writer.visualize_results(model=self)
