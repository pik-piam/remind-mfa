from flodym import (
    SimpleFlowDrivenStock,
    StockArray,
    make_processes,
    StockDrivenDSM,
    InflowDrivenDSM,
)
from flodym.stock_helper import make_empty_stocks
from flodym.flow_helper import make_empty_flows

from simson.common.common_cfg import CommonCfg
from simson.common.data_transformations import extrapolate_stock, extrapolate_to_future, smooth
from simson.common.custom_data_reader import CustomDataReader
from simson.steel.steel_export import SteelDataExporter
from simson.steel.stock_driven_steel import StockDrivenSteelMFASystem
from simson.steel.inflow_driven_steel_historic import InflowDrivenHistoricSteelMFASystem
from simson.steel.steel_trade_model import SteelTradeModel
from simson.steel.steel_sector_splits import calc_stock_sector_splits
from simson.steel.steel_definition import get_definition


class SteelModel:

    def __init__(self, cfg: CommonCfg):
        self.cfg = cfg
        self.definition = get_definition()
        self.data_reader = CustomDataReader(input_data_path=self.cfg.input_data_path, definition=self.definition)
        self.data_writer = SteelDataExporter(
            **dict(self.cfg.visualization), output_path=self.cfg.output_path,
        )

        self.dims = self.data_reader.read_dimensions(self.definition.dimensions)
        # TODO: confirm all required data is being loaded
        # loading the steel production data
        # loading steel direct and indirect trade data (
        # direct is for intermediate steel products, indirect for finished products like cars)
        # loading steel sector splits for intermediate products, and indirect trade
        self.parameters = self.data_reader.read_parameters(self.definition.parameters, dims=self.dims)
        self.processes = make_processes(self.definition.processes)

    def run(self):
        trade_model = self.make_trade_model()
        trade_model.balance_historic_trade()
        historic_mfa = self.make_historic_mfa(trade_model)
        historic_mfa.compute()
        historic_in_use_stock = self.model_historic_stock(historic_mfa.stocks['in_use'])
        future_in_use_stock = self.create_future_stock_from_historic(historic_in_use_stock)
        trade_model = trade_model.predict(future_in_use_stock)
        trade_model.balance_future_trade()
        mfa = self.make_future_mfa(future_in_use_stock, trade_model)
        mfa.compute()
        self.data_writer.export_mfa(mfa=mfa)
        self.data_writer.visualize_results(mfa=mfa)

    def make_historic_mfa(self, trade_model) -> InflowDrivenHistoricSteelMFASystem:
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

        historic_dims = self.dims.get_subset(('h', 'e', 'r', 'i', 'g'))
        historic_processes = [
            'sysenv',
            'forming',
            'ip_market',
            # 'ip_trade', # todo decide whether to incorporate, depending on trade balancing
            'fabrication',
            # 'indirect_trade', # todo decide whether to incorporate, depending on trade balancing
            'use'
        ]
        processes = make_processes(historic_processes)
        flows = make_empty_flows(
            processes=processes,
            flow_definitions=[f for f in self.definition.flows if 'h' in f.dim_letters],
            dims=historic_dims
        )
        stocks = make_empty_stocks(
            processes=processes,
            stock_definitions=[s for s in self.definition.stocks if 'h' in s.dim_letters],
            dims=historic_dims
        )

        return InflowDrivenHistoricSteelMFASystem(
            cfg=self.cfg,
            parameters=self.parameters,
            processes=processes,
            dims=historic_dims,
            flows=flows,
            stocks=stocks,
            trade_model=trade_model,
        )

    def model_historic_stock(self, historic_in_use_stock):
        """
        Calculate stocks and outflow through dynamic stock model
        """
        prm = self.parameters

        dsm = InflowDrivenDSM(
            dims=historic_in_use_stock.dims,
            name='in_use',
            process=self.processes['use'],
            lifetime_model=self.cfg.customization.lifetime_model,
            inflow=historic_in_use_stock.inflow,
            time_letter='h',
        )
        dsm.lifetime_model.set_prms(
            mean=prm['lifetime_mean'],
            std=prm['lifetime_std'])

        dsm.compute()  # gives stocks and outflows corresponding to inflow

        historic_in_use_stock.stock[...] = dsm.stock
        historic_in_use_stock.outflow[...] = dsm.outflow

        return historic_in_use_stock

    def create_future_stock_from_historic(self, historic_in_use_stock):
        # extrapolate in use stock to future
        total_in_use_stock = extrapolate_stock(
            historic_in_use_stock.stock, dims=self.dims, parameters=self.parameters,
            curve_strategy=self.cfg.customization.curve_strategy, target_dim_letters=('t', 'r')
        )

        # calculate and apply sector splits for in use stock

        sector_splits = calc_stock_sector_splits(self.dims,
                                                 self.parameters['gdppc'].values,
                                                 self.parameters['lifetime_mean'].values,
                                                 historic_in_use_stock.stock.get_shares_over('g').values)

        in_use_stock = sector_splits * total_in_use_stock
        in_use_stock = StockArray(**dict(in_use_stock))  # cast to Stock Array

        # create dynamic stock model for in use stock

        dsm = StockDrivenDSM(
            dims=in_use_stock.dims,
            name='in_use',
            process=self.processes['use'],
            lifetime_model=self.cfg.customization.lifetime_model,
            stock=in_use_stock,
        )
        dsm.lifetime_model.set_prms(
            mean=self.parameters['lifetime_mean'],
            std=self.parameters['lifetime_std'])
        dsm.compute()  # gives inflows and outflows corresponding to in-use stock

        # smooth short-term demand

        historic_demand = historic_in_use_stock.inflow
        demand_via_gdp = extrapolate_to_future(historic_demand, scale_by=self.parameters['gdppc'])
        demand_via_stock = dsm.inflow

        smoothing_start_idx = historic_demand.values.shape[0]
        demand = smooth(demand_via_stock, demand_via_gdp, type='sigmoid',
                        start_idx=smoothing_start_idx,
                        duration=20)

        # create final dynamic stock model

        new_dsm = InflowDrivenDSM(
            dims=in_use_stock.dims,
            name='in_use',
            process=self.processes['use'],
            lifetime_model=self.cfg.customization.lifetime_model,
            inflow=demand,
        )
        new_dsm.lifetime_model.set_prms(
            mean=self.parameters['lifetime_mean'],
            std=self.parameters['lifetime_std'])
        new_dsm.compute()  # gives inflows and outflows corresponding to in-use stock

        return SimpleFlowDrivenStock(
            dims=new_dsm.dims,
            stock=new_dsm.stock,
            inflow=new_dsm.inflow,
            outflow=new_dsm.outflow,
            name='in_use',
            process_name='use',
            process=self.processes['use'],
        )

    def make_trade_model(self):
        """
        Create a trade module that stores and calculates the trade flows between regions and sectors.
        """
        trade_prm_names = [
            'direct_imports',
            'direct_exports',
            'indirect_imports',
            'indirect_exports',
            'scrap_imports',
            'scrap_exports'
        ]
        trade_prms = {name: self.parameters[name] for name in trade_prm_names}
        self.parameters = {name: self.parameters[name] for name in self.parameters if name not in trade_prm_names}
        return SteelTradeModel.create(dims=self.dims, trade_data=trade_prms)

    def make_future_mfa(self, future_in_use_stock, trade_model):
        flows = make_empty_flows(
            processes=self.processes,
            flow_definitions=[f for f in self.definition.flows if 't' in f.dim_letters],
            dims=self.dims
        )
        stocks = make_empty_stocks(
            processes=self.processes,
            stock_definitions=[s for s in self.definition.stocks if 't' in s.dim_letters],
            dims=self.dims
        )
        stocks['use'] = future_in_use_stock
        return StockDrivenSteelMFASystem(
            dims=self.dims, parameters=self.parameters,
            processes=self.processes, flows=flows, stocks=stocks,
            trade_model=trade_model,
        )
