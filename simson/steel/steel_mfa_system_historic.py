import numpy as np
import flodym as fd

from simson.common.trade import TradeSet
from simson.steel.steel_sector_splits import calc_demand_sector_splits_via_gdp


class InflowDrivenHistoricSteelMFASystem(fd.MFASystem):
    trade_set: TradeSet

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_trade()
        self.compute_flows()
        self.compute_in_use_stock()
        self.check_mass_balance()

    def compute_trade(self):
        """
        Create a trade module that stores and calculates the trade flows between regions and sectors.
        """
        for name, trade in self.trade_set.stages.items():
            trade.imports[...] = self.parameters[f'{name}_imports']
            trade.exports[...] = self.parameters[f'{name}_exports']
        self.trade_set.balance(to='maximum')

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        trd = self.trade_set

        aux = {
            'net_intermediate_trade': self.get_new_array(dim_letters=('h', 'r', 'i')),
            'fabrication_inflow_by_sector': self.get_new_array(dim_letters=('h', 'r', 'g')),
            'fabrication_loss': self.get_new_array(dim_letters=('h', 'r', 'g')),
            'fabrication_error': self.get_new_array(dim_letters=('h', 'r'))
        }

        flw['sysenv => forming'][...] = prm['production_by_intermediate']
        flw['forming => ip_market'][...] = prm['production_by_intermediate'] * prm['forming_yield']
        flw['forming => sysenv'][...] = flw['sysenv => forming'] - flw['forming => ip_market']

        flw['ip_market => sysenv'][...] = trd['intermediate'].exports
        flw['sysenv => ip_market'][...] = trd['intermediate'].imports

        aux['net_intermediate_trade'][...] = flw['sysenv => ip_market'] - flw['ip_market => sysenv']
        flw['ip_market => fabrication'][...] = flw['forming => ip_market'] + aux['net_intermediate_trade']

        aux['fabrication_inflow_by_sector'][...] = self._calc_sector_flows_gdp_curve(flw['ip_market => fabrication'],
                                                                                     prm['gdppc'])

        aux['fabrication_error'] = flw['ip_market => fabrication'] - aux['fabrication_inflow_by_sector']

        flw['fabrication => use'][...] = aux['fabrication_inflow_by_sector'] * prm['fabrication_yield']
        aux['fabrication_loss'][...] = aux['fabrication_inflow_by_sector'] - flw['fabrication => use']
        flw['fabrication => sysenv'][...] = aux['fabrication_error'] + aux['fabrication_loss']

        # Recalculate indirect trade according to available inflow from fabrication
        trd['indirect'].exports[...] = trd['indirect'].exports.minimum(flw['fabrication => use'])
        trd['indirect'].balance(to='minimum')

        flw['sysenv => use'][...] = trd['indirect'].imports
        flw['use => sysenv'][...] = trd['indirect'].exports

        return

    def _calc_sector_flows_gdp_curve(self, intermediate_flow: fd.FlodymArray, gdppc: fd.FlodymArray):
        fabrication_sector_split = calc_demand_sector_splits_via_gdp(gdppc)

        total_intermediate_flow = intermediate_flow.sum_over('i')
        sector_flow_values = np.einsum('hr,hrg->hrg', total_intermediate_flow.values,
                                       fabrication_sector_split[:123])
        sector_flows = self.get_new_array(dim_letters=('h', 'r', 'g'))
        sector_flows.values = sector_flow_values

        return sector_flows

    def compute_in_use_stock(self):
        flw = self.flows
        stk = self.stocks
        prm = self.parameters
        flw = self.flows

        stk['historic_in_use'].inflow[...] = flw['fabrication => use'] + flw['sysenv => use'] - flw['use => sysenv']

        stk['historic_in_use'].lifetime_model.set_prms(
            mean=prm['lifetime_mean'],
            std=prm['lifetime_std'])

        stk['historic_in_use'].compute()  # gives stocks and outflows corresponding to inflow

        flw['use => sysenv'][...] += stk['historic_in_use'].outflow
