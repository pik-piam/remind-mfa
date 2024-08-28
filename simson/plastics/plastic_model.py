from sodym import (
    MFADefinition, DimensionDefinition, FlowDefinition, StockDefinition, ParameterDefinition,
)
from sodym.stock_helper import create_dynamic_stock

from ..common.inflow_driven_mfa import InflowDrivenHistoricMFA
from ..common.data_transformations import (
    extrapolate_stock, prepare_stock_for_mfa,
)
from ..common.custom_data_reader import CustomDataReader
from ..common.custom_visualization import CustomDataVisualizer
from simson.plastics.stock_driven_plastics import PlasticsMFASystem


class PlasticModel():

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.definition = self.set_up_definition()
        self.data_reader = CustomDataReader(input_data_path=self.cfg['input_data_path'])
        self.data_writer = CustomDataVisualizer(**self.cfg)
        self.mfa = PlasticsMFASystem.from_data_reader(
            definition=self.definition,
            data_reader=self.data_reader,
            mfa_cfg=self.cfg['model_customization'],
        )
        self.historic_mfa = InflowDrivenHistoricMFA(
            parameters=self.mfa.parameters,
            processes={'use': self.mfa.processes['use']},
            dims=self.mfa.dims.get_subset(('h', 'r', 'g')),
            flows=self.mfa.flows,
            stocks={'in_use': self.mfa.stocks['in_use']},
            mfa_cfg=self.mfa.mfa_cfg,
        )

    def run(self):
        self.historic_mfa.compute()
        historic_in_use_stock = self.historic_mfa.stocks['in_use'].stock
        in_use_stock = extrapolate_stock(
            historic_in_use_stock, dims=self.mfa.dims, parameters=self.mfa.parameters,
            curve_strategy=self.mfa.mfa_cfg['curve_strategy']
        )
        stk = create_dynamic_stock(
            name='in_use', process=self.mfa.processes['use'], ldf_type=self.mfa.mfa_cfg['ldf_type'],
            stock=in_use_stock, lifetime_mean=self.mfa.parameters['lifetime_mean'],
            lifetime_std=self.mfa.parameters['lifetime_std'],
        )
        stk.compute()  # gives inflows and outflows corresponding to in-use stock
        self.mfa.stocks['in_use'] = prepare_stock_for_mfa(
            stk=stk, dims=self.mfa.dims, prm=self.mfa.parameters, use=self.mfa.processes['use']
        )
        self.mfa.compute()
        self.data_writer.export_mfa(mfa=self.mfa)
        self.data_writer.visualize_results(mfa=self.mfa)

    # Dictionary of variable names vs names displayed in figures. Used by visualization routines.
    display_names = {
        'sysenv': 'System environment',
        'virginfoss': 'Virgin production (fossil)',
        'virginbio': 'Virgin production (biomass)',
        'virgindaccu': 'Virgin production (daccu)',
        'virginccu': 'Virgin production (ccu)',
        'virgin': 'Virgin production (total)',
        'fabrication': 'Fabrication',
        'recl': 'Recycling (total)',
        'reclmech': 'Mechanical recycling',
        'reclchem': 'Chemical recycling',
        'reclsolv': 'Solvent-based recycling',
        'use': 'Use Phase',
        'eol': 'End of Life',
        'incineration': 'Incineration',
        'landfill': 'Disposal',
        'uncontrolled': 'Uncontrolled release',
        'emission': 'Emissions',
        'captured': 'Captured',
        'atmosphere': 'Atmosphere'
    }

    def set_up_definition(self):

        dimensions = [
            DimensionDefinition(name='Time',          dim_letter='t', dtype=int),
            DimensionDefinition(name='Historic Time', dim_letter='h', dtype=int),
            DimensionDefinition(name='Element',       dim_letter='e', dtype=str),
            DimensionDefinition(name='Region',        dim_letter='r', dtype=str),
            DimensionDefinition(name='Material',      dim_letter='m', dtype=str),
            DimensionDefinition(name='Good',          dim_letter='g', dtype=str),
        ]

        processes = [
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
            'atmosphere',
        ]

        # names are auto-generated, see Flow class documetation
        flows = [
            FlowDefinition(from_process='sysenv',       to_process='virginfoss',   dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='sysenv',       to_process='virginbio',    dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='sysenv',       to_process='virgindaccu',  dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='sysenv',       to_process='virginccu',    dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='atmosphere',   to_process='virginbio',    dim_letters=('t','e','r')),
            FlowDefinition(from_process='atmosphere',   to_process='virgindaccu',  dim_letters=('t','e','r')),
            FlowDefinition(from_process='virginfoss',   to_process='virgin',       dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='virginbio',    to_process='virgin',       dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='virgindaccu',  to_process='virgin',       dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='virginccu',    to_process='virgin',       dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='virgin',       to_process='fabrication',  dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='fabrication',  to_process='use',          dim_letters=('t','e','r','m','g')),
            FlowDefinition(from_process='use',          to_process='eol',          dim_letters=('t','e','r','m','g')),
            FlowDefinition(from_process='eol',          to_process='reclmech',     dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='eol',          to_process='reclchem',     dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='eol',          to_process='reclsolv',     dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='eol',          to_process='uncontrolled', dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='eol',          to_process='landfill',     dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='eol',          to_process='incineration', dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='reclmech',     to_process='recl',         dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='reclchem',     to_process='recl',         dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='reclsolv',     to_process='recl',         dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='recl',         to_process='fabrication',  dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='reclmech',     to_process='uncontrolled', dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='reclmech',     to_process='incineration', dim_letters=('t','e','r','m')),
            FlowDefinition(from_process='incineration', to_process='emission',     dim_letters=('t','e','r')),
            FlowDefinition(from_process='emission',     to_process='captured',     dim_letters=('t','e','r')),
            FlowDefinition(from_process='emission',     to_process='atmosphere',   dim_letters=('t','e','r')),
            FlowDefinition(from_process='captured',     to_process='virginccu',    dim_letters=('t','e','r')),
        ]

        stocks = [
            StockDefinition(name='in_use',       process='use',          dim_letters=('t','e','r','m','g')),
            StockDefinition(name='atmospheric',  process='atmosphere',   dim_letters=('t','e','r')),
            StockDefinition(name='landfill',     process='landfill',     dim_letters=('t','e','r','m')),
            StockDefinition(name='uncontrolled', process='uncontrolled', dim_letters=('t','e','r','m')),
        ]

        parameters = [
            # EOL rates
            ParameterDefinition(name='mechanical_recycling_rate',       dim_letters=('t','m')),
            ParameterDefinition(name='chemical_recycling_rate',         dim_letters=('t','m')),
            ParameterDefinition(name='solvent_recycling_rate',          dim_letters=('t','m')),
            ParameterDefinition(name='incineration_rate',               dim_letters=('t','m')),
            ParameterDefinition(name='uncontrolled_losses_rate',        dim_letters=('t','m')),
            # virgin production rates
            ParameterDefinition(name='bio_production_rate',             dim_letters=('t','m')),
            ParameterDefinition(name='daccu_production_rate',           dim_letters=('t','m')),
            # recycling losses
            ParameterDefinition(name='mechanical_recycling_yield',      dim_letters=('t','m')),
            ParameterDefinition(name='reclmech_loss_uncontrolled_rate', dim_letters=('t','m')),
            # other
            ParameterDefinition(name='material_shares_in_goods',        dim_letters=('m','g')),
            ParameterDefinition(name='emission_capture_rate',           dim_letters=('t',)),
            ParameterDefinition(name='carbon_content_materials',        dim_letters=('e','m')),
            # for in-use stock
            ParameterDefinition(name='production',                      dim_letters=('h','r','g')),
            ParameterDefinition(name='lifetime_mean',                   dim_letters=('g',)),
            ParameterDefinition(name='lifetime_std',                    dim_letters=('g',)),
            ParameterDefinition(name='population',                      dim_letters=('t','r')),
            ParameterDefinition(name='gdppc',                           dim_letters=('t','r')),
        ]

        return MFADefinition(
            dimensions=dimensions,
            processes=processes,
            flows=flows,
            stocks=stocks,
            parameters=parameters,
        )
