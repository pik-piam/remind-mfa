import flodym as fd

from simson.common.common_cfg import CommonCfg
from simson.common.data_transformations import extrapolate_stock, extrapolate_to_future, blend_short_term_to_long_term
from simson.common.custom_data_reader import CustomDataReader
from simson.common.trade import TradeSet
from simson.steel.steel_export import SteelDataExporter
from simson.steel.steel_mfa_system_future import StockDrivenSteelMFASystem
from simson.steel.steel_mfa_system_historic import InflowDrivenHistoricSteelMFASystem
from simson.steel.steel_sector_splits import calc_stock_sector_splits
from simson.steel.steel_definition import get_definition


class SteelModel:

    def __init__(self, cfg: CommonCfg):
        self.cfg = cfg
        self.definition = get_definition(self.cfg)
        self.data_reader = CustomDataReader(input_data_path=self.cfg.input_data_path, definition=self.definition)
        self.data_writer = SteelDataExporter(
            **dict(self.cfg.visualization), output_path=self.cfg.output_path,
        )
        self.dims = self.data_reader.read_dimensions(self.definition.dimensions)
        self.parameters = self.data_reader.read_parameters(self.definition.parameters, dims=self.dims)
        self.processes = fd.make_processes(self.definition.processes)

    def run(self):
        self.historic_mfa = self.make_historic_mfa()
        self.historic_mfa.compute()

        self.future_mfa = self.make_future_mfa()
        future_demand = self.get_future_demand()
        self.future_mfa.compute(future_demand, self.historic_mfa.trade_set)

        self.data_writer.export_mfa(mfa=self.future_mfa)
        self.data_writer.visualize_results(mfa=self.future_mfa)

    def make_historic_mfa(self) -> InflowDrivenHistoricSteelMFASystem:
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

        historic_dim_letters = tuple([d for d in self.dims.letters if d != 't'])
        historic_dims = self.dims[historic_dim_letters]
        historic_processes = [
            'sysenv',
            'forming',
            'ip_market',
            # 'ip_trade', # todo decide whether to incorporate, depending on trade balancing
            'fabrication',
            # 'indirect_trade', # todo decide whether to incorporate, depending on trade balancing
            'use'
        ]
        processes = fd.make_processes(historic_processes)
        flows = fd.make_empty_flows(
            processes=processes,
            flow_definitions=[f for f in self.definition.flows if 'h' in f.dim_letters],
            dims=historic_dims
        )
        stocks = fd.make_empty_stocks(
            processes=processes,
            stock_definitions=[s for s in self.definition.stocks if 'h' in s.dim_letters],
            dims=historic_dims
        )
        trade_set = TradeSet.from_definitions(
            definitions=[td for td in self.definition.trades if 'h' in td.dim_letters],
            dims=historic_dims)

        return InflowDrivenHistoricSteelMFASystem(
            cfg=self.cfg,
            parameters=self.parameters,
            processes=processes,
            dims=historic_dims,
            flows=flows,
            stocks=stocks,
            trade_set=trade_set,
        )

    def get_future_demand(self):
        raw_future_stock = self.get_raw_future_stock()
        demand_via_stock = self.get_demand_from_stock(raw_future_stock)
        short_term_demand = self.get_short_term_demand_trend(
            historic_demand=self.historic_mfa.stocks['historic_in_use'].inflow,
        )
        demand = blend_short_term_to_long_term(
            demand_via_stock,
            short_term_demand,
            type='sigmoid',
            start_idx=self.historic_mfa.dims['h'].len,
            duration=20,
        )
        return demand

    def get_raw_future_stock(self):
        # extrapolate in use stock to future
        total_in_use_stock = extrapolate_stock(
            self.historic_mfa.stocks['historic_in_use'].stock, dims=self.dims, parameters=self.parameters,
            curve_strategy=self.cfg.customization.curve_strategy, target_dim_letters=('t', 'r')
        )

        # calculate and apply sector splits for in use stock
        sector_splits = calc_stock_sector_splits(self.dims,
                                                 self.parameters['gdppc'].values,
                                                 self.parameters['lifetime_mean'].values,
                                                 self.historic_mfa.stocks['historic_in_use'].stock.get_shares_over('g').values)
        raw_future_stock = total_in_use_stock * sector_splits
        return raw_future_stock

    def get_demand_from_stock(self, raw_future_stock):
        # create dynamic stock model for in use stock
        dsm = fd.StockDrivenDSM(
            dims=self.dims['t', 'r', 'g'],
            lifetime_model=self.cfg.customization.lifetime_model,
        )
        dsm.lifetime_model.set_prms(
            mean=self.parameters['lifetime_mean'],
            std=self.parameters['lifetime_std'])
        dsm.stock[...] = raw_future_stock
        dsm.compute()  # gives inflows and outflows corresponding to in-use stock
        return dsm.inflow

    def get_short_term_demand_trend(self, historic_demand: fd.FlodymArray):
        demand_via_gdp = extrapolate_to_future(historic_demand, scale_by=self.parameters['gdppc'])
        return demand_via_gdp

    def make_future_mfa(self) -> StockDrivenSteelMFASystem:
        flows = fd.make_empty_flows(
            processes=self.processes,
            flow_definitions=[f for f in self.definition.flows if 't' in f.dim_letters],
            dims=self.dims
        )
        stocks = fd.make_empty_stocks(
            processes=self.processes,
            stock_definitions=[s for s in self.definition.stocks if 't' in s.dim_letters],
            dims=self.dims
        )

        trade_set = TradeSet.from_definitions(
            definitions=[td for td in self.definition.trades if 't' in td.dim_letters],
            dims=self.dims
        )

        return StockDrivenSteelMFASystem(
            dims=self.dims, parameters=self.parameters,
            processes=self.processes, flows=flows, stocks=stocks,
            trade_set=trade_set,
        )
