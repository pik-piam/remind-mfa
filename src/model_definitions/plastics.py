import numpy as np
from src.new_odym.mfa_system import EmptyModelDefinition, MFASystem
from src.new_odym.named_dim_arrays import ArrayValueOnlyDict
from src.tools.tools import get_dsm_data

class PlasticsModelDefinition(EmptyModelDefinition):

    def __init__(self):

        self.dimensions = [
            dict(name='Time',     dim_letter='t', dtype=int, filename='years'),
            dict(name='Element',  dim_letter='e', dtype=str, filename='elements'),
            dict(name='Region',   dim_letter='r', dtype=str, filename='regions'),
            dict(name='Material', dim_letter='m', dtype=str, filename='materials'),
            dict(name='Good',     dim_letter='g', dtype=str, filename='in_use_categories')]

        self.processes = ['sysenv',
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
                          'atmosphere']

        self.flows = [
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

        self.stocks = [
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

        self.parameters = [
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


class PlasticsMFASystem(MFASystem):

    definition = PlasticsModelDefinition()

    def compute_flows(self, dsms):

        use_inflows = get_dsm_data(dsms, lambda dsm: dsm.i)
        use_outflows = get_dsm_data(dsms, lambda dsm: dsm.o)

        prms = ArrayValueOnlyDict(self.parameters)
        f = ArrayValueOnlyDict(self.flows)
        loc = {}

        loc['fabrication => use'] = np.einsum('trg,mg->trmg', use_inflows, prms['material_shares_in_goods'])
        f['fabrication => use'] = np.einsum('trmg,em->termg', loc['fabrication => use'], prms['carbon_content_materials'])

        loc['use => eol'] = np.einsum('trg,mg->trmg', use_outflows, prms['material_shares_in_goods'])
        f['use => eol'] = np.einsum('trmg,em->termg', loc['use => eol'], prms['carbon_content_materials'])

        f['eol => reclmech'] = np.einsum('termg,tm->term', f['use => eol'], prms['mechanical_recycling_rate'])
        f['reclmech => recl'] = np.einsum('term,tm->term', f['eol => reclmech'], prms['mechanical_recycling_yield'])
        loc['reclmech_loss'] = f['eol => reclmech'] - f['reclmech => recl']
        f['reclmech => uncontrolled'] = np.einsum('term,tm->term', loc['reclmech_loss'], prms['reclmech_loss_uncontrolled_rate'])
        f['reclmech => incineration'] = loc['reclmech_loss'] - f['reclmech => uncontrolled']

        f['eol => reclchem'] = np.einsum('termg,tm->term', f['use => eol'], prms['chemical_recycling_rate'])
        f['reclchem => recl'] = f['eol => reclchem']

        f['eol => reclsolv'] = np.einsum('termg,tm->term', f['use => eol'], prms['solvent_recycling_rate'])
        f['reclsolv => recl'] = f['eol => reclsolv']

        f['eol => incineration'] = np.einsum('termg,tm->term', f['use => eol'], prms['incineration_rate'])
        f['eol => uncontrolled'] = np.einsum('termg,tm->term', f['use => eol'], prms['uncontrolled_losses_rate'])

        f['eol => landfill'] = np.einsum('termg->term', f['use => eol']) - f['eol => reclmech'] - f['eol => reclchem'] - f['eol => reclsolv'] - f['eol => incineration'] - f['eol => uncontrolled']

        f['incineration => emission'] = np.einsum('term->ter', f['eol => incineration'] + f['reclmech => incineration'])

        f['emission => captured'] = np.einsum('ter,t->ter', f['incineration => emission'], prms['emission_capture_rate'])
        f['emission => atmosphere'] = f['incineration => emission'] - f['emission => captured']
        f['captured => virginccu'] = f['emission => captured']

        f['recl => fabrication'] = f['reclmech => recl'] + f['reclchem => recl'] + f['reclsolv => recl']
        f['virgin => fabrication'] = np.einsum('termg->term', f['fabrication => use']) - f['recl => fabrication']

        f['virgindaccu => virgin'] = np.einsum('term,tm->term', f['virgin => fabrication'], prms['daccu_production_rate'])
        f['virginbio => virgin'] = np.einsum('term,tm->term', f['virgin => fabrication'], prms['bio_production_rate'])

        loc['virgin => fabrication_total'] = np.einsum('term->ter', f['virgin => fabrication'])
        loc['virgin_material_shares'] = np.einsum('term,ter->term', f['virgin => fabrication'], 1. / loc['virgin => fabrication_total'])
        loc['captured => virginccu_by_mat'] = np.einsum('ter,term->term', f['captured => virginccu'], loc['virgin_material_shares'])

        f.slice('virginccu => virgin', e='C')[...] = loc['captured => virginccu_by_mat'][:,0,:,:]
        loc['ratio_nonc_to_c'] = prms.slice('carbon_content_materials', e='Other Elements') / prms.slice('carbon_content_materials', e='C')
        f.slice('virginccu => virgin', e='Other Elements')[...] = np.einsum('trm,m->trm', f.slice('virginccu => virgin', e='C'), loc['ratio_nonc_to_c'])

        f['virginfoss => virgin'] = f['virgin => fabrication'] - f['virgindaccu => virgin'] - f['virginbio => virgin'] - f['virginccu => virgin']

        f['sysenv => virginfoss'] = f['virginfoss => virgin']
        f['atmosphere => virginbio'] = np.einsum('term->ter', f['virginbio => virgin'])
        f['atmosphere => virgindaccu'] = np.einsum('term->ter', f['virgindaccu => virgin'])
        f['sysenv => virginccu'] = f['virginccu => virgin'] - loc['captured => virginccu_by_mat']

        # non-C atmosphere & captured has no meaning & is equivalent to sysenv

        return


    def compute_stocks(self, dsms):

        use_stock_values = get_dsm_data(dsms, lambda dsm: dsm.s)

        prms = ArrayValueOnlyDict(self.parameters)
        stocks = ArrayValueOnlyDict(self.stocks)
        flows = ArrayValueOnlyDict(self.flows)
        loc = {}

        loc['stocks_by_material'] = np.einsum('trg,mg->trmg', use_stock_values, prms['material_shares_in_goods'])
        stocks['in_use_stock'] = np.einsum('trmg,em->termg', loc['stocks_by_material'], prms['carbon_content_materials'])
        stocks['in_use_stock_inflow'] = flows['fabrication => use']
        stocks['in_use_stock_outflow'] = flows['use => eol']
        stocks['landfill_stock_inflow'] = flows['eol => landfill']
        stocks['landfill_stock'] = stocks['landfill_stock_inflow'].cumsum(axis=0)
        stocks['uncontrolled_stock_inflow'] = flows['eol => uncontrolled'] + flows['reclmech => uncontrolled']
        stocks['uncontrolled_stock'] = stocks['uncontrolled_stock_inflow'].cumsum(axis=0)
        stocks['atmospheric_stock_inflow'] = flows['emission => atmosphere']
        stocks['atmospheric_stock_outflow'] = flows['atmosphere => virgindaccu'] + flows['atmosphere => virginbio']
        stocks['atmospheric_stock'] = stocks['atmospheric_stock_inflow'].cumsum(axis=0) - stocks['atmospheric_stock_outflow'].cumsum(axis=0)
        return
