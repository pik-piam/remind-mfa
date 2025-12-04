import flodym as fd

from remind_mfa.common.common_config import CommonCfg
from remind_mfa.common.scenarios import ScenarioReader
from remind_mfa.common.common_definition import scenario_parameters as common_scn_prm_def
from remind_mfa.common.common_data_reader import CommonDataReader
from remind_mfa.common.common_export import CommonDataExporter
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.common.common_definition import get_definition
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.parameter_extrapolation import ParameterExtrapolationManager


class CommonModel:

    ConfigCls = CommonCfg
    DataReaderCls = CommonDataReader
    DataExporterCls = CommonDataExporter
    HistoricMFASystemCls = CommonMFASystem
    FutureMFASystemCls = CommonMFASystem
    custom_scn_prm_def = []
    get_definition = staticmethod(get_definition)

    def __init__(self, cfg: dict):
        self.cfg = self.ConfigCls(**cfg)
        self.set_definition()
        self.read_data()
        self.read_scenario_parameters()
        self.modify_parameters()
        self.init_data_writer()

    def get_long_term_stock(self):
        raise NotImplementedError

    def run(self):
        self.historic_mfa = self.make_mfa(historic=True)
        self.historic_mfa.compute()

        historic_trade = self.historic_mfa.trade_set
        stock_projection = self.get_long_term_stock()

        # apply scenarios to parameters for future mfa
        self.parameters = ParameterExtrapolationManager(
            self.cfg, self.dims["t"]
        ).apply_prm_extrapolation(self.parameters)

        self.future_mfa = self.make_mfa(historic=False)
        self.future_mfa.compute(stock_projection, historic_trade)

    def export(self):
        self.data_writer.export_mfa(mfa=self.future_mfa)
        self.data_writer.definition_to_markdown(definition=self.definition_future)
        self.data_writer.visualize_results(model=self)

    def set_definition(self):
        self.definition_historic = self.get_definition(self.cfg, historic=True)
        self.definition_future = self.get_definition(self.cfg, historic=False)

    def read_data(self):
        self.data_reader = self.DataReaderCls(
            cfg=self.cfg,
            definition=self.definition_future,
            # TODO: Remove requirement for plastics and then remove these two lines
            allow_extra_values=True,
            # allow_missing_values=True,
        )
        self.dims = self.data_reader.read_dimensions(self.definition_future.dimensions)
        self.parameters = self.data_reader.read_parameters(
            self.definition_future.parameters, dims=self.dims
        )

    def read_scenario_parameters(self):
        parameter_definitions = common_scn_prm_def + self.custom_scn_prm_def
        scenario_reader = ScenarioReader(
            name=self.cfg.model_switches.scenario,
            base_path=self.cfg.scenarios_path,
            model=self.cfg.model,
            dims=self.dims,
            parameter_definitions=parameter_definitions,
        )
        self.scenario_parameters = scenario_reader.get_parameters()

    def modify_parameters(self):
        """Manual changes to parameters"""
        pass

    def init_data_writer(self):
        self.data_writer = self.DataExporterCls(
            cfg=self.cfg.visualization,
            do_export=self.cfg.do_export,
            output_path=self.cfg.output_path,
            docs_path=self.cfg.docs_path,
        )

    def make_mfa(self, historic: bool) -> CommonMFASystem:
        """
        Splitting production and direct trade by IP sector splits, and indirect trade by category trade sector splits (s. step 3)
        subtracting Losses in steel forming from production by IP data
        adding direct trade by IP to production by IP
        transforming that to production by category via some distribution assumptions
        subtracting losses in steel fabrication (transformation of IP to end use products)
        adding indirect trade by category
        This equals the inflow into the in use stock
        via lifetime assumptions I can calculate in use stock from inflow into in use stock and lifetime
        """
        if historic:
            definition = self.definition_historic
            mfasystem_class = self.HistoricMFASystemCls
        else:
            definition = self.definition_future
            mfasystem_class = self.FutureMFASystemCls

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
            cfg=self.cfg,
            parameters=self.parameters,
            processes=processes,
            dims=self.dims,
            flows=flows,
            stocks=stocks,
            trade_set=trade_set,
        )
