import logging
from typing import Optional
import flodym as fd
import numpy as np

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
from remind_mfa.common.data_blending import blend
from remind_mfa.common.stock_extrapolation import StockExtrapolation
from remind_mfa.common.helpers import RegressOverModes


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

    def __init__(self, cfg: dict):
        self.cfg = self.ConfigCls(**cfg)
        self.set_definition()
        self.read_data()
        self.check_parameters()
        self.read_scenario_parameters()
        self.select_gdp_pop_scen()
        self.modify_parameters()
        self.init_export_and_visualization()

    def run(self):
        self.historic_mfa = self.make_mfa(historic=True)
        self.historic_mfa.compute()
        self.transfer_historic_parameters()

        historic_trade = self.historic_mfa.trade_set

        # apply scenarios to parameters for future mfa
        # 1. extend historic parameters into future
        self.parameters = ParameterExtrapolationManager(
            self.cfg, self.dims["t"]
        ).apply_prm_extrapolation(self.parameters, self.scenario_parameters)
        # 2. adjust future parameters based on scenario
        self.apply_scenario_adjustments_to_parameters()

        # compute parameter modifications for transience
        if self.cfg.transience.transience_run:
            self.compute_transience_parameters()

        stock_projection = self.get_long_term_stock()

        self.future_mfa = self.make_mfa(historic=False)
        self.future_mfa.compute(stock_projection, historic_trade, self.baseline_trade, self.baseline_flows)

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
            allow_missing_values=True,  # needed for at least steel scrap data
            allow_extra_values=False,
        )
        self.dims = self.data_reader.read_dimensions(self.definition_future.dimensions)
        self.parameters = self.data_reader.read_parameters(
            self.definition_future.parameters, dims=self.dims
        )
        if self.cfg.transience.baseline_pickle_path is not None:
            self.baseline_trade = self.data_reader.read_baseline_trade()
            self.baseline_flows = self.data_reader.read_baseline_flows()
        else:
            self.baseline_trade = None
            self.baseline_flows = None

    def check_parameters(self, exceptions: Optional[list] = None, raise_error: bool = False):
        """Check if all parameters are free of NaN and negative values after data read-in."""
        logging.info("Checking parameters for NaN and negative values...")
        exceptions = exceptions or []

        all_good = True
        for name, prm in self.parameters.items():
            if name in exceptions:
                continue
            if np.any(np.isnan(prm.values)):
                msg = f"NaN values found in parameter '{name}'!"
                if raise_error:
                    raise ValueError(msg)
                logging.warning(msg)
                all_good = False
            if np.any(prm.values < 0):
                msg = f"Negative values found in parameter '{name}'!"
                if raise_error:
                    raise ValueError(msg)
                logging.warning(msg)
                all_good = False

        if all_good:
            logging.info("Success - No NaN or negative values found in parameters.")

    def select_gdp_pop_scen(self):
        """Select GDP and population scenario parameters based on scenario name"""
        scen_name = self.scenario_parameters["gdp_pop_scen"]
        for prm_name in ["gdppc", "population"]:
            slice = self.parameters[prm_name][{"S": scen_name}]
            self.parameters[prm_name] = fd.Parameter(dims=self.dims["t", "r"])
            self.parameters[prm_name][...] = slice

    def read_scenario_parameters(self):
        scn_prm_def = common_scn_prm_def + self.custom_scn_prm_def
        scenario_reader = ScenarioReader(
            name=self.cfg.model_switches.scenario,
            base_path=self.cfg.input.scenarios_path,
            model=self.cfg.model,
            dims=self.dims,
            parameter_definitions=scn_prm_def,
        )
        self.scenario_parameters = scenario_reader.get_parameters()

    def modify_parameters(self):
        """Manual changes to parameters"""
        pass

    def compute_transience_parameters(self):
        """Calculate parameters for EU region for transience based on flows from EU-MFA"""
        pass

    def apply_scenario_adjustments_to_parameters(self):
        """Apply scenario adjustments to parameters"""
        # lifetime:
        for prm_name in ["lifetime_mean", "lifetime_std"]:
            self.apply_scenario_factor(
                array=self.parameters[prm_name],
                scen_prm_name="lifetime_factor",
            )

    def transfer_historic_parameters(self):
        """Transfer parameters from historic to future MFA system if needed, e.g. material splits of plastics stock."""
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
        stock_sector_split = (self.lifetime_limit() * prm["sector_split_limit"]).get_shares_over(
            self.end_use_good_letter
        )
        return stock_sector_split

    def get_long_term_stock(self) -> fd.FlodymArray:
        saturation_level = self.scenario_parameters["saturation_level"]
        sector_specific_sat_level = self.get_stock_sector_split_limit() * saturation_level

        # add static time-dependent penetration curve if desired.
        if self.cfg.model_switches.do_stock_extrapolation_with_time_factor:
            time_factor = fd.FlodymArray.full(dims=self.dims["t", "r", "g"], fill_value=1.0)
            time = np.array(self.dims["t"].items)
            lifetime = self.lifetime_limit()  # shape (g, r)
            for r in self.dims["r"].items:
                for g in self.dims[self.end_use_good_letter].items:
                    # these are the parameters for a Gompertz function that reaches 20% saturation in 1950 and 80% in 2020
                    # shifted by the lifetimes, so goods with longer lifetimes reach saturation later
                    lt = lifetime[{"r": r, self.end_use_good_letter: g}].values.item()
                    b = 1980 + lt
                    prms = [1, b, 0.01]
                    ExtrapolationClass = self.cfg.model_switches.stock_extrapolation_class
                    time_factor[{"r": r, self.end_use_good_letter: g}] = ExtrapolationClass.func(
                        ExtrapolationClass, time, prms
                    )
        else:
            time_factor = fd.FlodymArray.full(
                dims=fd.DimensionSet(dim_list=[self.dims["t"]]), fill_value=1
            )

        historic_stocks = self.historic_mfa.stocks[self.historic_stock_name].stock
        normalized_historic_stock = (
            historic_stocks / sector_specific_sat_level / time_factor[{"t": self.dims["h"]}]
        )

        # after normalization, target saturation level is 1 across all regions and sectors.
        sat_level_bound = Bound(
            var_name="saturation_level",
            lower_bound=1,
            upper_bound=1,
        )
        growth_rate_bound = Bound(
            var_name="growth_rate",
            lower_bound=0,
            upper_bound=np.inf,
        )
        bound_list_obj = BoundList(
            target_dims=self.dims[self.end_use_good_letter,],
            bound_list=[sat_level_bound, growth_rate_bound],
        )

        if self.cfg.model_switches.regress_over == RegressOverModes.LOGGDPPC_TIME:
            growth_rate_bound_gdp = Bound(
                var_name="x1_growth_rate",
                lower_bound=0,
                upper_bound=np.inf,
            )
            growth_rate_bound_time = Bound(
                var_name="x2_growth_rate",
                lower_bound=0,
                upper_bound=np.inf,
            )
            bound_list_obj = BoundList(
                target_dims=self.dims[self.end_use_good_letter,],
                bound_list=[sat_level_bound, growth_rate_bound_gdp, growth_rate_bound_time],
            )

        self.stock_handler = StockExtrapolation(
            cfg=self.cfg.model_switches,
            historic_stocks=normalized_historic_stock,
            dims=self.dims,
            parameters=self.parameters,
            target_dim_letters="all",
            indep_fit_dim_letters=(self.end_use_good_letter,),
            bound_list=bound_list_obj,
            lifetime=self.lifetime_limit(),
        )
        self.stock_handler.extrapolate()

        # denormalize
        self.time_factor = time_factor  # store for later use in visualization
        self.sector_specific_sat_level = sector_specific_sat_level # store for later use in visualization
        long_term_stock = self.stock_handler.stocks * self.sector_specific_sat_level * self.time_factor

        self.apply_scenario_factor(array=long_term_stock, scen_prm_name="stock_factor")

        return long_term_stock

    def apply_scenario_factor(self, array: fd.FlodymArray, scen_prm_name: str) -> fd.FlodymArray:
        target_dims = array.dims.union_with(self.dims["t"])
        if isinstance(self.scenario_parameters[scen_prm_name], fd.FlodymArray):
            if any(
                l not in array.dims.letters
                for l in self.scenario_parameters[scen_prm_name].dims.letters
            ):
                raise ValueError(
                    f"Dimensions of scenario parameter {scen_prm_name} must also be present in the base parameter."
                )

        factor = blend(
            target_dims=target_dims,
            y_lower=1,
            y_upper=self.scenario_parameters[scen_prm_name],
            x="t",
            x_lower=self.dims["h"].items[-1],
            x_upper=self.scenario_parameters[f"{scen_prm_name}_year"],
        )
        array[...] *= factor

    def lifetime_limit(self):
        """Effective lifetime when saturation level is reached.
        Currently, this is just the last modelled lifetime."""
        return self.parameters["lifetime_mean"][{"t": self.dims["t"].items[-1]}]
