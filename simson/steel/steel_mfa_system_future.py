import flodym as fd

from simson.common.trade import TradeSet
from simson.common.trade_predictors import predict_by_extrapolation

class StockDrivenSteelMFASystem(fd.MFASystem):

    trade_set : TradeSet

    def compute(self, demand: fd.FlodymArray, historic_trade: TradeSet):
        """
        Perform all computations for the MFA system.
        """
        self.compute_in_use_stock(demand)
        self.compute_trade(historic_trade)
        self.compute_flows()
        self.compute_other_stocks()
        self.check_mass_balance()

    def compute_in_use_stock(self, demand):
        self.stocks['in_use'].inflow = demand
        self.stocks['in_use'].lifetime_model.set_prms(
            mean=self.parameters['lifetime_mean'],
            std=self.parameters['lifetime_std'])
        self.stocks['in_use'].compute()

    def compute_trade(self, historic_trade: TradeSet):
        product_demand = self.stocks['in_use'].inflow
        eol_products = self.stocks['in_use'].outflow

        intermediate = predict_by_extrapolation(historic_trade['intermediate'], product_demand, 'imports')
        indirect = predict_by_extrapolation(historic_trade['indirect'], product_demand, 'imports')
        scrap = predict_by_extrapolation(historic_trade['scrap'], eol_products, 'exports', adopt_scaler_dims=True)

        future_trade = TradeSet(stages={
            'intermediate': intermediate,
            'indirect': indirect,
            'scrap': scrap,
            })
        future_trade.balance()
        return future_trade

    def compute_flows(self):
        # abbreviations for better readability
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        trd = self.trade_set

        # auxiliary arrays;
        # It is important to initialize them to define their dimensions. See the FlodymArray documentation for details.
        # could also be single variables instead of dict, but this way the code looks more uniform
        aux = {
            'net_indirect_trade' : self.get_new_array(dim_letters=('t', 'e', 'r', 'g')),
            'net_direct_trade' : self.get_new_array(dim_letters=('t', 'e', 'r', 'i')),
            'net_scrap_trade' : self.get_new_array(dim_letters=('t', 'e', 'r', 'g')),
            'total_fabrication': self.get_new_array(dim_letters=('t', 'e', 'r', 'g')),
            'production': self.get_new_array(dim_letters=('t', 'e', 'r', 'i')),
            'forming_outflow': self.get_new_array(dim_letters=('t', 'e', 'r')),
            'scrap_in_production': self.get_new_array(dim_letters=('t', 'e', 'r')),
            'available_scrap': self.get_new_array(dim_letters=('t', 'e', 'r')),
            'eaf_share_production': self.get_new_array(dim_letters=('t', 'e', 'r')),
            'production_inflow': self.get_new_array(dim_letters=('t', 'e', 'r')),
            'max_scrap_production': self.get_new_array(dim_letters=('t', 'e', 'r')),
            'scrap_share_production': self.get_new_array(dim_letters=('t', 'e', 'r')),
            'bof_production_inflow': self.get_new_array(dim_letters=('t', 'e', 'r')),
        }

        # Slicing on the left-hand side of the assignment (foo[...] = bar) is used to assign only the values of the flows, not the FlodymArray object managing the dimensions.
        # This way, the dimensions of the right-hand side of the assignment can be automatically reduced and re-ordered to the dimensions of the left-hand side.
        # For further details on the syntax, see the FlodymArray documentation.

        # Pre-use


        flw['sysenv => use']['Fe'][...]                 = trd['indirect'].imports
        flw['use => sysenv']['Fe'][...]                 = trd['indirect'].exports

        aux['net_indirect_trade'][...]                  = flw['sysenv => use']                  -   flw['use => sysenv']
        flw['fabrication => use']['Fe'][...]            = stk['in_use'].inflow                  -   aux['net_indirect_trade']['Fe']

        aux['total_fabrication'][...]                   = flw['fabrication => use']             /   prm['fabrication_yield']
        flw['fabrication => scrap_market'][...]         = aux['total_fabrication']              -   flw['fabrication => use']
        flw['ip_market => fabrication'][...]            = aux['total_fabrication']              *   prm['good_to_intermediate_distribution']

        flw['sysenv => ip_market']['Fe'][...]           = trd['intermediate'].imports
        flw['ip_market => sysenv']['Fe'][...]           = trd['intermediate'].exports
        aux['net_direct_trade'][...]                    = flw['sysenv => ip_market']            -   flw['ip_market => sysenv']

        flw['forming => ip_market'][...]                = flw['ip_market => fabrication']       -   aux['net_direct_trade']
        aux['production'][...]                          = flw['forming => ip_market']           /   prm['forming_yield']
        aux['forming_outflow'][...]                     = aux['production']                     -   flw['forming => ip_market']
        flw['forming => sysenv'][...]                   = aux['forming_outflow']                *   prm['forming_losses']
        flw['forming => scrap_market'][...]             = aux['forming_outflow']                -   flw['forming => sysenv']

        # Post-use

        flw['use => eol_market']['Fe'][...]             = stk['in_use'].outflow                 *   prm['recovery_rate']
        flw['use => obsolete']['Fe'][...]               = stk['in_use'].outflow                 -   flw['use => eol_market']['Fe']

        flw['sysenv => eol_market']['Fe'][...]          = trd['scrap'].imports
        flw['eol_market => sysenv']['Fe'][...]          = trd['scrap'].exports
        aux['net_scrap_trade'][...]                     = flw['sysenv => eol_market']           -   flw['eol_market => sysenv']

        flw['eol_market => recycling'][...]             = flw['use => eol_market']              +   aux['net_scrap_trade']
        flw['recycling => scrap_market'][...]           = flw['eol_market => recycling']


        # PRODUCTION

        aux['production_inflow'][...]                   = aux['production']                     /   prm['production_yield']
        aux['max_scrap_production'][...]                = aux['production_inflow']              *   prm['max_scrap_share_base_model']
        aux['available_scrap'][...]                     = flw['recycling => scrap_market']      +   flw['forming => scrap_market']          +   flw['fabrication => scrap_market']
        aux['scrap_in_production'][...]                 = aux['available_scrap'].minimum(aux['max_scrap_production'])  # using NumPy Minimum functionality
        flw['scrap_market => excess_scrap'][...]        = aux['available_scrap']                -   aux['scrap_in_production']
        #  TODO include copper like this:aux['scrap_share_production']['Fe'][...]        = aux['scrap_in_production']['Fe']      /   aux['production_inflow']['Fe']
        aux['scrap_share_production'][...]              = aux['scrap_in_production']            /   aux['production_inflow']
        aux['eaf_share_production'][...]                = aux['scrap_share_production']         -   prm['scrap_in_bof_rate'].cast_to(aux['scrap_share_production'].dims)
        aux['eaf_share_production'][...]                = aux['eaf_share_production']           /   (1 - prm['scrap_in_bof_rate'])
        aux['eaf_share_production'][...]                = aux['eaf_share_production'].minimum(1).maximum(0)
        flw['scrap_market => eaf_production'][...]      = aux['production_inflow']              *   aux['eaf_share_production']
        flw['scrap_market => bof_production'][...]      = aux['scrap_in_production']            -   flw['scrap_market => eaf_production']
        aux['bof_production_inflow'][...]               = aux['production_inflow']              -   flw['scrap_market => eaf_production']
        flw['sysenv => bof_production'][...]            = aux['bof_production_inflow']          -   flw['scrap_market => bof_production']
        flw['bof_production => forming'][...]           = aux['bof_production_inflow']          *   prm['production_yield']
        flw['bof_production => sysenv'][...]            = aux['bof_production_inflow']          -   flw['bof_production => forming']
        flw['eaf_production => forming'][...]           = flw['scrap_market => eaf_production'] *   prm['production_yield']
        flw['eaf_production => sysenv'][...]            = flw['scrap_market => eaf_production'] -   flw['eaf_production => forming']

        return

    def compute_other_stocks(self):
        stk = self.stocks
        flw = self.flows

        # in-use stock is already computed in compute_in_use_stock
        stk['obsolete'].inflow[...] = flw['use => obsolete']
        stk['obsolete'].compute()

        stk['excess_scrap'].inflow[...] = flw['scrap_market => excess_scrap']
        stk['excess_scrap'].compute()

