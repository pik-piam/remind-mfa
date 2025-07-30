import flodym as fd

from remind_mfa.common.common_cfg import GeneralCfg
from remind_mfa.common.data_transformations import Bound, BoundList
from remind_mfa.cement.cement_definition import get_definition
from remind_mfa.cement.cement_mfa_system_historic import (
    InflowDrivenHistoricCementMFASystem,
)
from remind_mfa.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem
from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.cement.cement_data_reader import CementDataReader
from remind_mfa.cement.cement_export import CementDataExporter
from remind_mfa.common.stock_extrapolation import StockExtrapolation
from remind_mfa.common.assumptions_doc import add_assumption_doc


class CementModel:

    def __init__(self, cfg: GeneralCfg):
        self.cfg = cfg
        self.definition = get_definition(self.cfg)
        self.data_reader = CementDataReader(
            input_data_path=self.cfg.input_data_path,
            definition=self.definition,
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
        self.historic_mfa = self.make_historic_mfa()
        self.historic_mfa.compute()

        # future mfa
        self.future_mfa = self.make_future_mfa()
        future_stock = self.get_long_term_stock()
        self.future_mfa.compute(future_stock)

        # visualization and export
        self.data_writer.export_mfa(mfa=self.future_mfa)
        self.data_writer.visualize_results(model=self)

    def make_historic_mfa(self) -> InflowDrivenHistoricCementMFASystem:
        historic_dim_letters = tuple([d for d in self.dims.letters if d != "t"])
        historic_dims = self.dims[historic_dim_letters]
        historic_processes = [
            "sysenv",
            "use",
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

    def get_long_term_stock(self) -> fd.FlodymArray:
        """Extrapolate in use stock to future. """
        indep_fit_dim_letters = ("r",)

        # saturation bound
        sat_level = 180 # t concrete per capita
        sat_bound = Bound(var_name="saturation_level", lower_bound=sat_level, upper_bound=sat_level)
        add_assumption_doc(
            type="ad-hoc fix",
            value=sat_level,
            name="Saturation level of in-use concrete stock",
            description="The saturation level of the in-use concrete stock is set to T/cap. "
            "This is slightly above current EU levels.",
        )

        bound_list = BoundList(
            bound_list=[sat_bound],
            target_dims=self.dims[indep_fit_dim_letters],
        )

        # The following was an attempt to constraint the growth rate of the stock extrapolation
        # This did not work so far and therefore needs a revisit.

        # normalize historic stock to saturation level for extrapolation
        # historic_stock = self.historic_mfa.stocks["historic_in_use"].stock / sat_level

        # get individual extrapolation with only saturation bound
        # individual_stock_extrapolation = StockExtrapolation(
        #     historic_stock,
        #     dims=self.dims,
        #     parameters=self.parameters,
        #     stock_extrapolation_class=self.cfg.customization.stock_extrapolation_class,
        #     target_dim_letters=("t", "r"),
        #     indep_fit_dim_letters=indep_fit_dim_letters,#
        #     bound_list=bound_list,
        # )

        # stretch factor bound: China as upper bound
        # cha_idx = self.historic_mfa.stocks["historic_in_use"].stock.dims["r"].items.index("CHA")
        # stretch_factor_idx = 1
        # cha_stretch_factor = individual_stock_extrapolation.extrapolation.fit_prms[cha_idx][stretch_factor_idx]
        # stretch_bound = Bound(var_name="stretch_factor", lower_bound=0, upper_bound=cha_stretch_factor)
        # add_assumption_doc(
        #     type="expert guess",
        #     value=cha_stretch_factor,
        #     name="China stretch factor",
        #     description="The stretch factor of China as the upper bound for any region. "
        #     "No other region is expected to build their concrete stock faster than China."
        # )

        # # add bounds together
        # bound_list = BoundList(
        #     bound_list=[sat_bound, stretch_bound],
        #     target_dims=self.dims[indep_fit_dim_letters],
        # )


        # after this, a stock extrapolation with updated bounds would be done
        # Then, de-normalize some of the normalized values
        # self.stock_handler.pure_prediction = self.stock_handler.pure_prediction * sat_level
        # self.stock_handler.stocks = self.stock_handler.stocks * sat_level

        self.stock_handler = StockExtrapolation(
            self.historic_mfa.stocks["historic_in_use"].stock,
            dims=self.dims,
            parameters=self.parameters,
            stock_extrapolation_class=self.cfg.customization.stock_extrapolation_class,
            target_dim_letters=("t", "r"),
            indep_fit_dim_letters=indep_fit_dim_letters,
            bound_list=bound_list,
        )
        add_assumption_doc(
            type="ad-hoc fix",
            name="Region specific stock extrapolation.",
            description="Each region has its own stock extrapolation. "
            "Independent fit of stretch_factor and x_offset. "
            "This is problematic especially for regions with low historic stock levels.",
        )

        total_in_use_stock = self.stock_handler.stocks

        total_in_use_stock = total_in_use_stock * self.parameters["use_split"]
        return total_in_use_stock

    def make_future_mfa(self) -> StockDrivenCementMFASystem:
        flows = fd.make_empty_flows(
            processes=self.processes,
            flow_definitions=[f for f in self.definition.flows if "t" in f.dim_letters],
            dims=self.dims,
        )
        stocks = fd.make_empty_stocks(
            processes=self.processes,
            stock_definitions=[s for s in self.definition.stocks if "t" in s.dim_letters],
            dims=self.dims,
        )

        return StockDrivenCementMFASystem(
            dims=self.dims,
            parameters=self.parameters,
            processes=self.processes,
            flows=flows,
            stocks=stocks,
        )
