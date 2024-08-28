from sodym import MFASystem


class StockDrivenSteelMFASystem(MFASystem):

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_flows()
        self.compute_other_stocks()
        self.check_mass_balance()

    def compute_flows(self):
        # abbreviations for better readability
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        scp = self.scalar_parameters

        # auxiliary arrays;
        # It is important to initialize them to define their dimensions. See the NamedDimArray documentation for details.
        # could also be single variables instead of dict, but this way the code looks more uniform
        aux = {
            'total_fabrication': self.get_new_array(dim_letters=('t', 'e', 'r', 'g', 's')),
            'production': self.get_new_array(dim_letters=('t', 'e', 'r', 'i', 's')),
            'forming_outflow': self.get_new_array(dim_letters=('t', 'e', 'r', 's')),
            'scrap_in_production': self.get_new_array(dim_letters=('t', 'e', 'r', 's')),
            'available_scrap': self.get_new_array(dim_letters=('t', 'e', 'r', 's')),
            'eaf_share_production': self.get_new_array(dim_letters=('t', 'e', 'r', 's')),
            'production_inflow': self.get_new_array(dim_letters=('t', 'e', 'r', 's')),
            'max_scrap_production': self.get_new_array(dim_letters=('t', 'e', 'r', 's')),
            'scrap_share_production': self.get_new_array(dim_letters=('t', 'e', 'r', 's')),
            'bof_production_inflow': self.get_new_array(dim_letters=('t', 'e', 'r', 's')),
        }

        # Slicing on the left-hand side of the assignment (foo[...] = bar) is used to assign only the values of the flows, not the NamedDimArray object managing the dimensions.
        # This way, the dimensions of the right-hand side of the assignment can be automatically reduced and re-ordered to the dimensions of the left-hand side.
        # For further details on the syntax, see the NamedDimArray documentation.

        # Pre-use

        flw['fabrication => use'][...]                  = stk['use'].inflow
        aux['total_fabrication'][...]                   = flw['fabrication => use']             /   prm['fabrication_yield']
        flw['fabrication => fabrication_buffer'][...]   = aux['total_fabrication']              -   flw['fabrication => use']
        flw['ip_market => fabrication'][...]            = aux['total_fabrication']              *   prm['good_to_intermediate_distribution']
        flw['forming => ip_market'][...]                = flw['ip_market => fabrication']
        aux['production'][...]                          = flw['forming => ip_market']           /   prm['forming_yield']
        aux['forming_outflow'][...]                     = aux['production']                     -   flw['forming => ip_market']
        flw['forming => sysenv'][...]                   = aux['forming_outflow']                *   scp['forming_losses']
        flw['forming => fabrication_buffer'][...]       = aux['forming_outflow']                -   flw['forming => sysenv']

        # Post-use

        flw['use => outflow_buffer'][...]               = stk['use'].outflow
        flw['outflow_buffer => eol_market'][...]        = flw['use => outflow_buffer']          *   prm['recovery_rate']
        flw['outflow_buffer => obsolete'][...]          = flw['use => outflow_buffer']          -   flw['outflow_buffer => eol_market']
        flw['eol_market => recycling'][...]             = flw['outflow_buffer => eol_market']
        flw['recycling => scrap_market'][...]           = flw['eol_market => recycling']
        flw['fabrication_buffer => scrap_market'][...]  = flw['forming => fabrication_buffer']  +   flw['fabrication => fabrication_buffer']


        # PRODUCTION

        aux['production_inflow'][...]                   = aux['production']                     /   scp['production_yield']
        aux['max_scrap_production'][...]                = aux['production_inflow']              *   scp['max_scrap_share_base_model']
        aux['available_scrap'][...]                     = flw['recycling => scrap_market']      +   flw['fabrication_buffer => scrap_market']
        aux['scrap_in_production'][...]                 = aux['available_scrap'].minimum(aux['max_scrap_production'])  # using NumPy Minimum functionality
        flw['scrap_market => excess_scrap'][...]        = aux['available_scrap']                -   aux['scrap_in_production']
        aux['scrap_share_production']['Fe'][...]        = aux['scrap_in_production']['Fe']      /   aux['production_inflow']['Fe']
        aux['eaf_share_production'][...]                = aux['scrap_share_production']         -   scp['scrap_in_bof_rate']
        aux['eaf_share_production'][...]                = aux['eaf_share_production']           /   (1 - scp['scrap_in_bof_rate'])
        aux['eaf_share_production'][...]                = aux['eaf_share_production'].minimum(1).maximum(0)
        flw['scrap_market => eaf_production'][...]      = aux['production_inflow']              *   aux['eaf_share_production']
        flw['scrap_market => bof_production'][...]      = aux['scrap_in_production']            -   flw['scrap_market => eaf_production']
        aux['bof_production_inflow'][...]               = aux['production_inflow']              -   flw['scrap_market => eaf_production']
        flw['sysenv => bof_production'][...]            = aux['bof_production_inflow']          -   flw['scrap_market => bof_production']
        flw['bof_production => forming'][...]           = aux['bof_production_inflow']          *   scp['production_yield']
        flw['bof_production => sysenv'][...]            = aux['bof_production_inflow']          -   flw['bof_production => forming']
        flw['eaf_production => forming'][...]           = flw['scrap_market => eaf_production'] *   scp['production_yield']
        flw['eaf_production => sysenv'][...]            = flw['scrap_market => eaf_production'] -   flw['eaf_production => forming']

        return

    def compute_other_stocks(self):
        stk = self.stocks
        flw = self.flows

        # in-use stock is already computed in compute_in_use_stock

        stk['obsolete'].inflow[...] = flw['outflow_buffer => obsolete']
        stk['obsolete'].compute()

        stk['excess_scrap'].inflow[...] = flw['scrap_market => excess_scrap']
        stk['excess_scrap'].compute()

        # TODO: Delay buffers?

        stk['outflow_buffer'].inflow[...] = flw['use => outflow_buffer']
        stk['outflow_buffer'].outflow[...] = flw['outflow_buffer => eol_market'] + flw['outflow_buffer => obsolete']
        stk['outflow_buffer'].compute()

        stk['fabrication_buffer'].inflow[...] = flw['forming => fabrication_buffer'] + flw['fabrication => fabrication_buffer']
        stk['fabrication_buffer'].outflow[...] = flw['fabrication_buffer => scrap_market']
        stk['fabrication_buffer'].compute()
