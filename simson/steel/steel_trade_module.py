from sodym.trade_module import TradeModule
from sodym import Parameter
from simson.common.data_transformations import extrapolate_to_future

class SteelTradeModule(TradeModule):
    """A TradeModule for the steel sector."""

    def balance_historic_trade(self):
        self.trade_data['direct_imports'], self.trade_data['direct_exports'] = (
            self.balance_trade(imports= self.trade_data['direct_imports'],
                               exports= self.trade_data['direct_exports'],
                               by='maximum'))

        self.trade_data['indirect_imports'], self.trade_data['indirect_exports'] = (
            self.balance_trade(imports= self.trade_data['indirect_imports'],
                               exports= self.trade_data['indirect_exports'],
                               by='maximum'))

        self.trade_data['scrap_imports'], self.trade_data['scrap_exports'] = (
            self.balance_trade(imports= self.trade_data['scrap_imports'],
                               exports= self.trade_data['scrap_exports'],
                               by='maximum'))

    def balance_future_trade(self):
        pass

    def predict(self, future_in_use_stock):
        assert all(['h' in trade_parameter.dims.letters for trade_parameter in self.trade_data.values()]), \
            "Trade data must have a historic time dimension."

        product_demand = future_in_use_stock.inflow
        eol_products = future_in_use_stock.outflow

        future_trade = {}

        for name, prm in self.trade_data.items():
            new_dims = prm.dims.replace('h', self.dims['t'])
            if 'scrap' in name:
                new_dims = new_dims.expand_by([self.dims['g']])
            future_trade[name] =  Parameter(name=name, dims=new_dims)

        # indirect trade

        future_trade['indirect_imports'][...] = extrapolate_to_future(
            historic_values=self.trade_data['indirect_imports'],
            scale_by=product_demand)

        global_indirect_imports = future_trade['indirect_imports'].sum_nda_over(sum_over_dims='r')
        future_trade['indirect_exports'][...] = extrapolate_to_future(
            historic_values=self.trade_data['indirect_exports'],
            scale_by=global_indirect_imports)

        # intermediate trade

        total_product_demand = product_demand.sum_nda_over(sum_over_dims='g')
        future_trade['direct_imports'][...] = extrapolate_to_future(
            historic_values=self.trade_data['direct_imports'],
            scale_by=total_product_demand)

        global_direct_imports = future_trade['direct_imports'].sum_nda_over(sum_over_dims='r')
        future_trade['direct_exports'][...] = extrapolate_to_future(
            historic_values=self.trade_data['direct_exports'],
            scale_by=global_direct_imports)

        # scrap trade

        total_eol_products = eol_products.sum_nda_over(sum_over_dims='g')
        total_scrap_exports = extrapolate_to_future(
            historic_values=self.trade_data['scrap_exports'],
            scale_by=total_eol_products)  # shouldn't this be total _collected_ scrap?

        global_scrap_exports = total_scrap_exports.sum_nda_over(sum_over_dims='r')
        total_scrap_imports = extrapolate_to_future(
            historic_values=self.trade_data['scrap_imports'],
            scale_by=global_scrap_exports)

        future_trade['scrap_exports'][...] = total_scrap_exports * eol_products.get_shares_over('g')
        future_trade['scrap_imports'][...] = total_scrap_imports * future_trade['scrap_exports'].get_shares_over('g')

        self.trade_data = future_trade