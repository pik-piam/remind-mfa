from src.new_odym.mfa_system import MFASystem
from src.new_odym.named_dim_arrays import NamedDimArray, MathOperationArrayDict
from src.tools.tools import get_dsm_data

class PlasticsMFASystem(MFASystem):

    def fill_definition(self):

        self.definition.dimensions = [
            dict(name='Time',     dim_letter='t', dtype=int, filename='years'),
            dict(name='Element',  dim_letter='e', dtype=str, filename='elements'),
            dict(name='Region',   dim_letter='r', dtype=str, filename='regions'),
            dict(name='Material', dim_letter='m', dtype=str, filename='materials'),
            dict(name='Good',     dim_letter='g', dtype=str, filename='in_use_categories')
        ]

        self.definition.processes = [
            'sysenv',
            'virginfoss',
            'virginbio',
            'virgindaccu',
            'virginccu',
            'virgin',
            'fabrication',
            'recl',
            'reclmech',
            'reclchem',
            'reclsolv',
            'use',
            'eol',
            'incineration',
            'landfill',
            'uncontrolled',
            'emission',
            'captured',
            'atmosphere'
        ]

        self.definition.flows = [
            dict(from_process='sysenv',       to_process='virginfoss',   dim_letters=('t','e','r','m')),
            dict(from_process='sysenv',       to_process='virginbio',    dim_letters=('t','e','r','m')),
            dict(from_process='sysenv',       to_process='virgindaccu',  dim_letters=('t','e','r','m')),
            dict(from_process='sysenv',       to_process='virginccu',    dim_letters=('t','e','r','m')),
            dict(from_process='atmosphere',   to_process='virginbio',    dim_letters=('t','e','r')),
            dict(from_process='atmosphere',   to_process='virgindaccu',  dim_letters=('t','e','r')),
            dict(from_process='virginfoss',   to_process='virgin',       dim_letters=('t','e','r','m')),
            dict(from_process='virginbio',    to_process='virgin',       dim_letters=('t','e','r','m')),
            dict(from_process='virgindaccu',  to_process='virgin',       dim_letters=('t','e','r','m')),
            dict(from_process='virginccu',    to_process='virgin',       dim_letters=('t','e','r','m')),
            dict(from_process='virgin',       to_process='fabrication',  dim_letters=('t','e','r','m')),
            dict(from_process='fabrication',  to_process='use',          dim_letters=('t','e','r','m','g')),
            dict(from_process='use',          to_process='eol',          dim_letters=('t','e','r','m','g')),
            dict(from_process='eol',          to_process='reclmech',     dim_letters=('t','e','r','m')),
            dict(from_process='eol',          to_process='reclchem',     dim_letters=('t','e','r','m')),
            dict(from_process='eol',          to_process='reclsolv',     dim_letters=('t','e','r','m')),
            dict(from_process='eol',          to_process='uncontrolled', dim_letters=('t','e','r','m')),
            dict(from_process='eol',          to_process='landfill',     dim_letters=('t','e','r','m')),
            dict(from_process='eol',          to_process='incineration', dim_letters=('t','e','r','m')),
            dict(from_process='reclmech',     to_process='recl',         dim_letters=('t','e','r','m')),
            dict(from_process='reclchem',     to_process='recl',         dim_letters=('t','e','r','m')),
            dict(from_process='reclsolv',     to_process='recl',         dim_letters=('t','e','r','m')),
            dict(from_process='recl',         to_process='fabrication',  dim_letters=('t','e','r','m')),
            dict(from_process='reclmech',     to_process='uncontrolled', dim_letters=('t','e','r','m')),
            dict(from_process='reclmech',     to_process='incineration', dim_letters=('t','e','r','m')),
            dict(from_process='incineration', to_process='emission',     dim_letters=('t','e','r')),
            dict(from_process='emission',     to_process='captured',     dim_letters=('t','e','r')),
            dict(from_process='emission',     to_process='atmosphere',   dim_letters=('t','e','r')),
            dict(from_process='captured',     to_process='virginccu',    dim_letters=('t','e','r'))
        ]

        self.definition.stocks = [
            dict(name='in_use_stock',              process='use',          stock_type=0, dim_letters=('t','e','r','m','g')),
            dict(name='in_use_stock_inflow',       process='use',          stock_type=1, dim_letters=('t','e','r','m','g')),
            dict(name='in_use_stock_outflow',      process='use',          stock_type=2, dim_letters=('t','e','r','m','g')),
            dict(name='atmospheric_stock',         process='atmosphere',   stock_type=0, dim_letters=('t','e','r')),
            dict(name='atmospheric_stock_inflow',  process='atmosphere',   stock_type=1, dim_letters=('t','e','r')),
            dict(name='atmospheric_stock_outflow', process='atmosphere',   stock_type=2, dim_letters=('t','e','r')),
            dict(name='landfill_stock',            process='landfill',     stock_type=0, dim_letters=('t','e','r','m')),
            dict(name='landfill_stock_inflow',     process='landfill',     stock_type=1, dim_letters=('t','e','r','m')),
            dict(name='uncontrolled_stock',        process='uncontrolled', stock_type=0, dim_letters=('t','e','r','m')),
            dict(name='uncontrolled_stock_inflow', process='uncontrolled', stock_type=1, dim_letters=('t','e','r','m'))
        ]

        self.definition.parameters = [
            # EOL rates
            dict(name='mechanical_recycling_rate',       dim_letters=('t','m')),
            dict(name='chemical_recycling_rate',         dim_letters=('t','m')),
            dict(name='solvent_recycling_rate',          dim_letters=('t','m')),
            dict(name='incineration_rate',               dim_letters=('t','m')),
            dict(name='uncontrolled_losses_rate',        dim_letters=('t','m')),
            # virgin production rates
            dict(name='bio_production_rate',             dim_letters=('t','m')),
            dict(name='daccu_production_rate',           dim_letters=('t','m')),
            # recycling losses
            dict(name='mechanical_recycling_yield',      dim_letters=('t','m')),
            dict(name='reclmech_loss_uncontrolled_rate', dim_letters=('t','m')),
            # other
            dict(name='material_shares_in_goods',        dim_letters=('m','g')),
            dict(name='emission_capture_rate',           dim_letters=('t',)),
            dict(name='carbon_content_materials',        dim_letters=('e','m')),
        ]

    def compute_flows(self, dsms):

        use_inflows = get_dsm_data(dsms, lambda dsm: dsm.inflow)
        use_outflows = get_dsm_data(dsms, lambda dsm: dsm.outflow)

        # MathOperationArrayDict objects enable a simple syntax, as demonstrated below.
        # For details, see the MathOperationArrayDict class documentation
        prm = MathOperationArrayDict(self.parameters)
        flw = MathOperationArrayDict(self.flows)

        # auxiliary arrays
        aux = MathOperationArrayDict([
            NamedDimArray('use_inflows',                  ('t','r','g'),     self.dims, use_inflows),
            NamedDimArray('use_outflows',                 ('t','r','g'),     self.dims, use_outflows),
            NamedDimArray('fabrication_2_use_all_el',     ('t','r','m','g'), self.dims),
            NamedDimArray('use_2_eol_all_el',             ('t','r','m','g'), self.dims),
            NamedDimArray('reclmech_loss',                ('t','e','r','m'), self.dims),
            NamedDimArray('virgin_2_fabr_all_mat',        ('t','e','r'),     self.dims),
            NamedDimArray('virgin_material_shares',       ('t','e','r','m'), self.dims),
            NamedDimArray('captured_2_virginccu_by_mat',  ('t','e','r','m'), self.dims),
            NamedDimArray('ratio_nonc_to_c',              ('m',),            self.dims),
        ])

        aux['fabrication_2_use_all_el']     = aux['use_inflows']              * prm['material_shares_in_goods']
        flw['fabrication => use']           = aux['fabrication_2_use_all_el'] * prm['carbon_content_materials']

        aux['use_2_eol_all_el']             = aux['use_outflows']             * prm['material_shares_in_goods']
        flw['use => eol']                   = aux['use_2_eol_all_el']         * prm['carbon_content_materials']

        flw['eol => reclmech']              = flw['use => eol']               * prm['mechanical_recycling_rate']
        flw['reclmech => recl']             = flw['eol => reclmech']          * prm['mechanical_recycling_yield']
        aux['reclmech_loss']                = flw['eol => reclmech']          - flw['reclmech => recl']
        flw['reclmech => uncontrolled']     = aux['reclmech_loss']            * prm['reclmech_loss_uncontrolled_rate']
        flw['reclmech => incineration']     = aux['reclmech_loss']            - flw['reclmech => uncontrolled']

        flw['eol => reclchem']              = flw['use => eol']               * prm['chemical_recycling_rate']
        flw['reclchem => recl']             = flw['eol => reclchem']

        flw['eol => reclsolv']              = flw['use => eol']               * prm['solvent_recycling_rate']
        flw['reclsolv => recl']             = flw['eol => reclsolv']

        flw['eol => incineration']          = flw['use => eol']               * prm['incineration_rate']
        flw['eol => uncontrolled']          = flw['use => eol']               * prm['uncontrolled_losses_rate']

        flw['eol => landfill']              = flw['use => eol']               - flw['eol => reclmech'] \
                                                                              - flw['eol => reclchem'] \
                                                                              - flw['eol => reclsolv'] \
                                                                              - flw['eol => incineration'] \
                                                                              - flw['eol => uncontrolled']

        flw['incineration => emission']     = flw['eol => incineration']      + flw['reclmech => incineration']

        flw['emission => captured']         = flw['incineration => emission'] * prm['emission_capture_rate']
        flw['emission => atmosphere']       = flw['incineration => emission'] - flw['emission => captured']
        flw['captured => virginccu']        = flw['emission => captured']

        flw['recl => fabrication']          = flw['reclmech => recl']         + flw['reclchem => recl'] \
                                                                              + flw['reclsolv => recl']
        flw['virgin => fabrication']        = flw['fabrication => use']       - flw['recl => fabrication']

        flw['virgindaccu => virgin']        = flw['virgin => fabrication']    * prm['daccu_production_rate']
        flw['virginbio => virgin']          = flw['virgin => fabrication']    * prm['bio_production_rate']

        aux['virgin_2_fabr_all_mat']        = flw['virgin => fabrication']
        aux['virgin_material_shares']       = flw['virgin => fabrication']    / aux['virgin_2_fabr_all_mat']
        aux['captured_2_virginccu_by_mat']  = flw['captured => virginccu']    * aux['virgin_material_shares']

        flw['virginccu => virgin', {'e': 'C'}]              = aux['captured_2_virginccu_by_mat', {'e': 'C'}]
        aux['ratio_nonc_to_c']                              = prm['carbon_content_materials', {'e': 'Other Elements'}] / prm['carbon_content_materials', {'e': 'C'}]
        flw['virginccu => virgin', {'e': 'Other Elements'}] = flw['virginccu => virgin', {'e': 'C'}]                   * aux['ratio_nonc_to_c']

        flw['virginfoss => virgin']         = flw['virgin => fabrication']    - flw['virgindaccu => virgin'] \
                                                                              - flw['virginbio => virgin'] \
                                                                              - flw['virginccu => virgin']

        flw['sysenv => virginfoss']         = flw['virginfoss => virgin']
        flw['atmosphere => virginbio']      = flw['virginbio => virgin']
        flw['atmosphere => virgindaccu']    = flw['virgindaccu => virgin']
        flw['sysenv => virginccu']          = flw['virginccu => virgin']      - aux['captured_2_virginccu_by_mat']

        # non-C atmosphere & captured has no meaning & is equivalent to sysenv

        return


    def compute_stocks(self, dsms):

        use_stock_values = get_dsm_data(dsms, lambda dsm: dsm.stock)

        # MathOperationArrayDict objects enable a simple syntax, as demonstrated below.
        # For details, see the MathOperationArrayDict class documentation
        prm = MathOperationArrayDict(self.parameters)
        stk = MathOperationArrayDict(self.stocks)
        flw = MathOperationArrayDict(self.flows)
        # auxiliary arrays
        aux = MathOperationArrayDict([
            NamedDimArray('use_stock_values',   ('t','r','g'), self.dims, use_stock_values),
            NamedDimArray('stocks_by_material', ('t','r','g'), self.dims),
        ])

        aux['stocks_by_material']        = aux['use_stock_values'] * prm['material_shares_in_goods']
        stk['in_use_stock']              = aux['stocks_by_material'] * prm['carbon_content_materials']
        stk['in_use_stock_inflow']       = flw['fabrication => use']
        stk['in_use_stock_outflow']      = flw['use => eol']
        stk['landfill_stock_inflow']     = flw['eol => landfill']
        stk['landfill_stock']            = stk['landfill_stock_inflow'].cumsum_time()
        stk['uncontrolled_stock_inflow'] = flw['eol => uncontrolled'] + flw['reclmech => uncontrolled']
        stk['uncontrolled_stock']        = stk['uncontrolled_stock_inflow'].cumsum_time()
        stk['atmospheric_stock_inflow']  = flw['emission => atmosphere']
        stk['atmospheric_stock_outflow'] = flw['atmosphere => virgindaccu'] + flw['atmosphere => virginbio']
        stk['atmospheric_stock']         = stk['atmospheric_stock_inflow'].cumsum_time() - stk['atmospheric_stock_outflow'].cumsum_time()
        return
