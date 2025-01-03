import numpy as np
from numpy.linalg import inv
from simson.common.inflow_driven_mfa import InflowDrivenHistoricMFA
from simson.steel.steel_trade_model import SteelTradeModel
from sodym.stock_helper import create_dynamic_stock


class InflowDrivenHistoricSteelMFASystem(InflowDrivenHistoricMFA):
    trade_model: SteelTradeModel

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_historic_flows()
        self.compute_historic_in_use_stock()
        self.check_mass_balance()

    def compute_historic_flows(self):
        prm = self.parameters
        flw = self.flows
        trd = self.trade_model

        aux = {
            'net_intermediate_trade': self.get_new_array(dim_letters=('h', 'r', 'i')),
            'fabrication_inflow_by_sector': self.get_new_array(dim_letters=('h', 'r', 'g'))
        }

        flw['sysenv => forming'][...] = prm['production_by_intermediate']
        flw['forming => ip_market'][...] = prm['production_by_intermediate'] * prm['forming_yield']
        flw['forming => sysenv'][...] = flw['sysenv => forming'] - flw['forming => ip_market']

        flw['ip_market => sysenv'][...] = trd.intermediate.exports
        flw['sysenv => ip_market'][...] = trd.intermediate.imports

        aux['net_intermediate_trade'][...] = flw['sysenv => ip_market'] - flw['ip_market => sysenv']
        flw['ip_market => fabrication'][...] = flw['forming => ip_market'] + aux['net_intermediate_trade']

        aux['fabrication_inflow_by_sector'][...] = self._calc_sector_flows_gdp_curve(flw['ip_market => fabrication'],
                                                                                     prm['gdppc'],
                                                                                     prm['fabrication_yield'])

        flw['fabrication => use'][...] = aux['fabrication_inflow_by_sector'] * prm['fabrication_yield']

        test = flw['fabrication => use'].values
        test_spits = np.einsum('hrg,hr->hrg', test, 1 / np.sum(test, axis=2))

        flw['fabrication => sysenv'][...] = aux['fabrication_inflow_by_sector'] - flw['fabrication => use']

        # Recalculate indirect trade according to available inflow from fabrication
        trd.indirect.exports[...] = trd.indirect.exports.minimum(flw['fabrication => use'])
        trd.indirect.balance(by='minimum')

        flw['sysenv => use'][...] = trd.indirect.imports
        flw['use => sysenv'][...] = trd.indirect.exports

        return

    def _calc_sector_flows_gdp_curve(self, intermediate_flow, gdppc, fabrication_yield):
        # you have this already
        names = ['Construction', 'Machinery', 'Products', 'Transport']
        s_ind = np.array([0.47, 0.32, 0.10, 0.11])
        s_usa = np.array([0.47, 0.10, 0.13, 0.30])
        # please get exact values for this from your data
        gdppc_ind = 2091
        gdppc_usa = 43458

        # this is just the values we plot over
        # this is the core of the calculation: sigmoid over gdppc
        # -3 and +3 are x-values where the sigmoid has almost reached its limits (0 and 1)
        def alpha(gdppc):
            x = -3. + 6. * (np.log(gdppc) - np.log(gdppc_ind)) / (np.log(gdppc_usa) - np.log(gdppc_ind))
            return 1. / (1. + np.exp(-x))

        a = alpha(gdppc.values)
        # stretch a such that it is 0 at gdppc_ind and 1 at gdppc_usa (actually overhsooting/extrpolating their values slightly)
        a_ind = alpha(gdppc_ind)
        a_usa = alpha(gdppc_usa)
        a = (a - a_ind) / (a_usa - a_ind)

        # s = a*s_usa + (1-a)*s_ind
        # with correct numpy dimensions
        post_fabrication_sector_split = a[:, :, np.newaxis] * s_usa + (1 - a[:, :, np.newaxis]) * s_ind

        c = np.einsum('trg,f->trgf', post_fabrication_sector_split, fabrication_yield.values)
        d = np.einsum('trgf,trfg->trgf', c, 1 / c)
        e = np.sum(d, axis=2)
        pre_fabrication_sector_split = 1 / e

        total_intermediate_flow = intermediate_flow.sum_nda_over('i')
        sector_flow_values = np.einsum('hr,hrg->hrg', total_intermediate_flow.values,
                                       pre_fabrication_sector_split[:123])
        sector_flows = self.get_new_array(dim_letters=('h', 'r', 'g'))
        sector_flows.values = sector_flow_values

        # todo delete below

        test = np.einsum('hrg,g->hrg', sector_flows.values, fabrication_yield.values)
        test_spits = np.einsum('hrg,hr->hrg', test, 1 / np.sum(test, axis=2))

        return sector_flows

    def _calc_sector_flows_ig_distribtution(self, intermediate_flow, gi_distribution):  # TODO: Delete?
        """
        Estimate the fabrication by in-use-good according to the inflow of intermediate products
        and the good to intermediate product distribution.
        """

        # The following calculation is based on
        # https://en.wikipedia.org/wiki/Overdetermined_system#Approximate_solutions
        # gi_values represents 'A', hence the variable at_a is A transposed times A
        # 'b' is the intermediate flow and x are the sector flows that we are trying to find out

        gi_values = gi_distribution.values.transpose()
        at_a = np.matmul(gi_values.transpose(), gi_values)
        inverse_at_a = inv(at_a)
        inverse_at_a_times_at = np.matmul(inverse_at_a, gi_values.transpose())
        sector_flow_values = np.einsum('gi,hri->hrg', inverse_at_a_times_at, intermediate_flow.values)

        # don't allow negative sector flows
        sector_flow_values = np.maximum(0, sector_flow_values)

        sector_flows = self.get_new_array(dim_letters=('h', 'r', 'g'))
        sector_flows.values = sector_flow_values

        return sector_flows

    def compute_historic_in_use_stock(self):
        flw = self.flows
        stk = self.stocks

        stk['in_use'].inflow[...] = flw['fabrication => use'] + flw['sysenv => use'] - flw['use => sysenv']
