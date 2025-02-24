import numpy as np
import flodym as fd

from simson.common.common_cfg import GeneralCfg
from simson.cement.cement_definition import get_definition
from simson.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem
from simson.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from simson.cement.cement_data_reader import CementDataReader
from simson.cement.cement_export import CementDataExporter
from simson.common.data_transformations import extrapolate_stock, extrapolate_to_future
from simson.common.data_blending import blend, blend_over_time

class CementModel:

    def __init__(self, cfg: GeneralCfg):
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

        # future mfa
        self.future_mfa = self.make_future_mfa()
        # TODO have return_fit defined in yml...
        future_demand, fit = self.get_future_demand(return_fit=True)
        self.future_mfa.compute(future_demand)

        self.data_writer.export_mfa(mfa=self.future_mfa)
        self.data_writer.visualize_results(mfa=self.future_mfa, fit=fit)

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
    
    def get_future_demand(self, return_fit=False):
        long_term_stock = self.get_long_term_stock()
        long_term_demand = self.get_demand_from_stock(long_term_stock)
        short_term_demand = self.get_short_term_demand_trend(
            historic_demand=self.historic_mfa.stocks["historic_in_use"].inflow,
        )
        demand = blend_over_time(
            target_dims=long_term_demand.dims,
            y_lower=short_term_demand,
            y_upper=long_term_demand,
            t_lower=self.historic_mfa.dims["h"].items[-1],
            t_upper=self.historic_mfa.dims["h"].items[-1] + 20,
        )
        if return_fit:
            fit = {
                "long_term_stock": long_term_stock,
                "short_term_demand": short_term_demand,
                "long_term_demand": long_term_demand,
            }
            return demand, fit
        
        return demand
    
    def get_long_term_stock(self):
        # extrapolate in use stock to future
        total_in_use_stock = extrapolate_stock(
            self.historic_mfa.stocks["historic_in_use"].stock,
            dims=self.dims,
            parameters=self.parameters,
            curve_strategy=self.cfg.customization.curve_strategy,
            target_dim_letters=("t", "r"),
        )

        # calculate and apply sector splits for in use stock
        # sector_splits = self.calc_stock_sector_splits(
        #     self.historic_mfa.stocks["historic_in_use"].stock.get_shares_over("g"),
        # )
        long_term_stock = total_in_use_stock * self.parameters["use_split"]
        return long_term_stock
    
    def get_demand_from_stock(self, long_term_stock):
        # create dynamic stock model for in use stock
        in_use_dsm_long_term = fd.StockDrivenDSM(
            dims=self.dims["t", "s"],
            lifetime_model=self.cfg.customization.lifetime_model,
        )
        in_use_dsm_long_term.lifetime_model.set_prms(
            mean=self.parameters["use_lifetime_mean"], std=self.parameters["use_lifetime_std"]
        )
        in_use_dsm_long_term.stock[...] = long_term_stock
        in_use_dsm_long_term.compute()
        return in_use_dsm_long_term.inflow

    def get_short_term_demand_trend(self, historic_demand: fd.FlodymArray):
        # TODO correct scale_by by removing the sum over "r" when different regions are implemented.
        demand_via_gdp = extrapolate_to_future(historic_demand, scale_by=self.parameters["gdppc"].sum_over("r"))
        return demand_via_gdp
    
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
