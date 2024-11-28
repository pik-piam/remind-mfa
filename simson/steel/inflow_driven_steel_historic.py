from typing import Dict
import numpy as np
from numpy.linalg import inv
from simson.common.inflow_driven_mfa import InflowDrivenHistoricMFA
from sodym.trade import Trade
from simson.steel.steel_trade_model import SteelTradeModel

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
            'net_intermediate_trade': self.get_new_array(dim_letters=('h','r','i')),
            'fabrication_by_sector': self.get_new_array(dim_letters=('h','r','g')),
            'fabrication_loss': self.get_new_array(dim_letters=('h','r','g')),
            'fabrication_error': self.get_new_array(dim_letters=('h','r'))
        }

        flw['sysenv => forming'][...]           = prm['production_by_intermediate']
        flw['forming => ip_market'][...]        = prm['production_by_intermediate']     *   prm['forming_yield']
        flw['forming => sysenv'][...]           = flw['sysenv => forming']              -   flw['forming => ip_market']

        flw['ip_market => sysenv'][...]         = trd.intermediate.exports
        flw['sysenv => ip_market'][...]         = trd.intermediate.imports

        aux['net_intermediate_trade'][...]      = flw['sysenv => ip_market']            -   flw['ip_market => sysenv']
        flw['ip_market => fabrication'][...]    = flw['forming => ip_market']           +   aux['net_intermediate_trade']

        # todo: cleanup

        """aux['fabrication_by_sector'][...] = self._calc_sector_flows(flw['ip_market => fabrication'],
                                                                    prm['good_to_intermediate_distribution'],
                                                                    prm['gdppc'])"""

        #aux['fabrication_by_sector'][...] = self._calc_sector_flows_ig_distribution(flw['ip_market => fabrication'],prm['good_to_intermediate_distribution'])
        aux['fabrication_by_sector'][...] = self._calc_sector_flows_gdp_curve(flw['ip_market => fabrication'],prm['gdppc'])

        fabrication_by_sector = aux['fabrication_by_sector'].values
        global_fabrication_by_sector = fabrication_by_sector.sum(axis=1)
        global_fabrication = global_fabrication_by_sector.sum(axis=1)
        global_sector_split = global_fabrication_by_sector / global_fabrication[:, np.newaxis]
        global_2019_sector_split = global_sector_split[119]

        aux['fabrication_error']                = flw['ip_market => fabrication']       -   aux['fabrication_by_sector']

        flw['fabrication => use'][...]          = aux['fabrication_by_sector']          *   prm['fabrication_yield']
        aux['fabrication_loss'][...]            = aux['fabrication_by_sector']          -   flw['fabrication => use']
        flw['fabrication => sysenv'][...]       = aux['fabrication_error']              +   aux['fabrication_loss']

        # Recalculate indirect trade according to available inflow from fabrication
        trd.indirect.exports[...]        = trd.indirect.exports.minimum(flw['fabrication => use'])
        trd.indirect.balance(by='minimum')

        flw['sysenv => use'][...]               = trd.indirect.imports
        flw['use => sysenv'][...]               = trd.indirect.exports

        return

    def _calc_sector_flows(self, intermediate_flow, gi_distribution, gdppc):
        sectors_dist = self._calc_sector_flows_ig_distribution(intermediate_flow, gi_distribution)
        sectors_gdp = self._calc_sector_flows_gdp_curve(intermediate_flow, gdppc)

        a = 0.3

        dist_values = sectors_dist.values
        gdp_values = sectors_gdp.values

        values = a * dist_values + (1 - a) * gdp_values
        ws_splits_2019 = np.array([0.52,0.16,0.15,0.17])
        global_values_2019 = values[119].sum(axis=0)
        global_splits_2019 = global_values_2019 / global_values_2019.sum()
        values = values * (ws_splits_2019 / global_splits_2019)

        new_global_values_2019 = values[119].sum(axis=0)
        new_global_splits_2019 = new_global_values_2019 / new_global_values_2019.sum()

        sector_flows = self.get_new_array(dim_letters=('h', 'r', 'g'))
        sector_flows.values = values

        # scale to same total quantity
        total_intermediate_flow = intermediate_flow.sum_nda_over('i')
        total_sector_flows = sector_flows.sum_nda_over('g')
        scaling_factor = total_intermediate_flow / total_sector_flows.maximum(1e-10)
        sector_flows *= scaling_factor

        # visualise
        regions = ['CAZ', 'CHA', 'EUR', 'IND', 'JPN', 'LAM', 'MEA', 'NEU', 'OAS', 'REF', 'SSA', 'USA']
        names = ['Construction', 'Machinery', 'Products', 'Transport']
        values = sector_flows.values
        sector_shares = values / values.sum(axis=-1)[:, :, np.newaxis]

        import plotly.express as px
        import pandas as pd
        for r, region in enumerate(regions):
            df = pd.DataFrame(sector_shares[:123, r, :], columns=names)
            df['year'] = range(1900, 2023)
            fig = px.line(df, x='year', y=names, title=region)
            fig.write_image(f"{region}_proposal_sector_splits.png")

        # global
        global_values = values.sum(axis=1)
        global_sector_shares = global_values / global_values.sum(axis=-1)[:, np.newaxis]
        df = pd.DataFrame(global_sector_shares[:123, :], columns=names)
        df['year'] = range(1900, 2023)
        fig = px.line(df, x='year', y=names, title='Global')
        fig.write_image(f"global_proposal_sector_splits.png")

        return sector_flows

    def _calc_sector_flows_gdp_curve(self, intermediate_flow, gdppc):

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
        s = a[:,:, np.newaxis] * s_usa + (1 - a[:, :,np.newaxis]) * s_ind

        total_intermediate_flow = intermediate_flow.sum_nda_over('i')
        sector_flow_values = np.einsum('hr,hrg->hrg', total_intermediate_flow.values, s[:123])

        sector_flows = self.get_new_array(dim_letters=('h', 'r', 'g'))
        sector_flows.values = sector_flow_values

        # visualise
        regions = ['CAZ', 'CHA', 'EUR', 'IND', 'JPN', 'LAM', 'MEA', 'NEU', 'OAS', 'REF', 'SSA', 'USA']

        import plotly.express as px
        import pandas as pd
        for r, region in enumerate(regions):
            df = pd.DataFrame(s[:123,r,:], columns=names)
            df['year'] = range(1900,2023)
            fig = px.line(df, x='year', y=names, title=region)
            fig.write_image(f"{region}_GDP_curve_sector_splits.png")

        # global
        global_values = s.sum(axis=1)
        global_sector_shares = global_values / global_values.sum(axis=-1)[:, np.newaxis]
        df = pd.DataFrame(global_sector_shares[:123, :], columns=names)
        df['year'] = range(1900, 2023)
        fig = px.line(df, x='year', y=names, title='Global')
        fig.write_image(f"global_GDP_curve_sector_splits.png")

        return sector_flows


    def _calc_sector_flows_ig_distribution(self, intermediate_flow, gi_distribution):
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
        sector_flow_values = np.einsum('gi,hri->hrg',inverse_at_a_times_at, intermediate_flow.values)

        # don't allow negative sector flows
        sector_flow_values = np.maximum(0, sector_flow_values)

        sector_flows = self.get_new_array(dim_letters=('h','r','g'))
        sector_flows.values = sector_flow_values

        # scale to same total quantity
        total_intermediate_flow = intermediate_flow.sum_nda_over('i')
        total_sector_flows = sector_flows.sum_nda_over('g')
        scaling_factor = total_intermediate_flow / total_sector_flows.maximum(1e-10)
        sector_flows *= scaling_factor

        # visualise
        regions = ['CAZ', 'CHA', 'EUR', 'IND', 'JPN', 'LAM', 'MEA', 'NEU', 'OAS', 'REF', 'SSA', 'USA']
        names = ['Construction', 'Machinery', 'Products', 'Transport']
        values = sector_flows.values
        sector_shares = values / values.sum(axis=-1)[:, :, np.newaxis]

        import plotly.express as px
        import pandas as pd
        for r, region in enumerate(regions):
            df = pd.DataFrame(sector_shares[:123, r, :], columns=names)
            df['year'] = range(1900, 2023)
            fig = px.line(df, x='year', y=names, title=region)
            fig.write_image(f"{region}_IG_dist_sector_splits.png")

        #global
        global_values = values.sum(axis=1)
        global_sector_shares = global_values / global_values.sum(axis=-1)[:, np.newaxis]
        df = pd.DataFrame(global_sector_shares[:123, :], columns=names)
        df['year'] = range(1900, 2023)
        fig = px.line(df, x='year', y=names, title='Global')
        fig.write_image(f"global_IG_dist_sector_splits.png")


        return sector_flows

    def compute_historic_in_use_stock(self):
        flw = self.flows
        stk = self.stocks
        stk['in_use'].inflow[...] = flw['fabrication => use'] + flw['sysenv => use'] - flw['use => sysenv']

        stk['in_use'].compute()

