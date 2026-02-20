import flodym as fd

from remind_mfa.common.common_config import CommonCfg
from remind_mfa.common.scenarios import ScenarioReader
from remind_mfa.common.common_definition import scenario_parameters as common_scn_prm_def
from remind_mfa.common.common_data_reader import CommonDataReader
from remind_mfa.common.common_mappings import CommonDimensionFiles, CommonDisplayNames
from remind_mfa.common.common_export import CommonDataExporter
from remind_mfa.common.common_visualization import CommonVisualizer
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.common.common_definition import get_definition
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.parameter_extrapolation import ParameterExtrapolationManager
from remind_mfa.common.data_transformations import Bound, BoundList
from remind_mfa.common.stock_extrapolation import StockExtrapolation


class CommonModel:

    ConfigCls = CommonCfg
    DimensionFilesCls = CommonDimensionFiles
    DataExporterCls = CommonDataExporter
    VisualizerCls = CommonVisualizer
    DisplayNamesCls = CommonDisplayNames
    HistoricMFASystemCls = CommonMFASystem
    FutureMFASystemCls = CommonMFASystem
    custom_scn_prm_def = []
    get_definition = staticmethod(get_definition)

    # TODO: unify, then delete
    end_use_good_letter: str = None
    historic_stock_name: str = None
    stock_projection_saturation_level: int = None

    def __init__(self, cfg: dict):
        self.cfg = self.ConfigCls(**cfg)
        self.set_definition()
        self.read_data()
        self.read_scenario_parameters()
        self.modify_parameters()
        self.init_export_and_visualization()

    def run(self):
        self.historic_mfa = self.make_mfa(historic=True)
        self.historic_mfa.compute()

        historic_trade = self.historic_mfa.trade_set
        stock_projection = self.get_long_term_stock()

        # apply scenarios to parameters for future mfa
        self.parameters = ParameterExtrapolationManager(
            self.cfg, self.dims["t"]
        ).apply_prm_extrapolation(self.parameters, self.scenario_parameters)

        self.future_mfa = self.make_mfa(historic=False)
        self.future_mfa.compute(stock_projection, historic_trade)

    def export(self):
        self.data_writer.export(model=self)

    def visualize(self):
        self.visualizer.visualize(model=self)

    def set_definition(self):
        self.definition_historic = self.get_definition(self.cfg, historic=True)
        self.definition_future = self.get_definition(self.cfg, historic=False)

    def read_data(self):
        self.data_reader = CommonDataReader(
            cfg=self.cfg,
            definition=self.definition_future,
            dimension_file_mapping=self.DimensionFilesCls(),
            allow_missing_values=True,  # needed for steel scrap data, among others
        )
        self.dims = self.data_reader.read_dimensions(self.definition_future.dimensions)
        self.parameters = self.data_reader.read_parameters(
            self.definition_future.parameters, dims=self.dims
        )

    def read_scenario_parameters(self):
        parameter_definitions = common_scn_prm_def + self.custom_scn_prm_def
        scenario_reader = ScenarioReader(
            name=self.cfg.model_switches.scenario,
            base_path=self.cfg.input.scenarios_path,
            model=self.cfg.model,
            dims=self.dims,
            parameter_definitions=parameter_definitions,
        )
        self.scenario_parameters = scenario_reader.get_parameters()

    def modify_parameters(self):
        """Manual changes to parameters"""
        pass

    def init_export_and_visualization(self):
        display_names = self.DisplayNamesCls()
        self.data_writer = self.DataExporterCls(
            cfg=self.cfg.export,
            display_names=display_names,
        )
        self.visualizer = self.VisualizerCls(
            cfg=self.cfg.visualization,
            display_names=display_names,
        )

    def make_mfa(self, historic: bool) -> CommonMFASystem:
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

    def get_stock_sector_split_limit(self):
        prm = self.parameters
        last_lifetime = prm["lifetime_mean"][{"t": self.dims["t"].items[-1]}]
        last_gdppc = prm["gdppc"][{"t": self.dims["t"].items[-1]}]
        av_lifetime = (last_lifetime * last_gdppc).sum_over("r") / last_gdppc.sum_over("r")
        stock_sector_split = (av_lifetime * prm["sector_split_limit"]).get_shares_over(
            self.end_use_good_letter
        )
        return stock_sector_split

    def get_long_term_stock(self) -> fd.FlodymArray:
        saturation_level = self.stock_projection_saturation_level
        arr = self.get_stock_sector_split_limit() * saturation_level
        bound = Bound(
            var_name="saturation_level",
            lower_bound=arr,
            upper_bound=arr,
        )
        historic_stocks = self.historic_mfa.stocks[self.historic_stock_name].stock

        bound_list_obj = BoundList(
            target_dims=self.dims[self.end_use_good_letter,],
            bound_list=[bound],
        )

        self.stock_handler = StockExtrapolation(
            cfg=self.cfg.model_switches,
            historic_stocks=historic_stocks,
            dims=self.dims,
            parameters=self.parameters,
            target_dim_letters="all",
            indep_fit_dim_letters=(self.end_use_good_letter,),
            bound_list=bound_list_obj,
        )
        self.stock_handler.extrapolate()
        return self.stock_handler.stocks
