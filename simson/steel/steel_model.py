from sodym import (
    MFADefinition, DimensionDefinition, FlowDefinition, ParameterDefinition, StockDefinition,
)
from sodym.stock_helper import create_dynamic_stock

from ..common.inflow_driven_mfa import InflowDrivenHistoricMFA
from simson.common.custom_data_reader import CustomDataReader
from simson.common.custom_visualization import CustomDataVisualizer
from simson.common.data_transformations import extrapolate_stock, prepare_stock_for_mfa
from simson.steel.stock_driven_steel import StockDrivenSteelMFASystem


class SteelModel():

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.definition = self.set_up_definition()
        self.data_reader = CustomDataReader(input_data_path=self.cfg['input_data_path'])
        self.data_writer = CustomDataVisualizer(**self.cfg)
        self.mfa = StockDrivenSteelMFASystem.from_data_reader(
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
            scalar_parameters=self.mfa.scalar_parameters,
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
        'bof_production': 'Production (BF/BOF)',
        'eaf_production': 'Production (EAF)',
        'forming': 'Forming',
        'fabrication_buffer': 'Fabrication Buffer',
        'ip_market': 'Intermediate product market',
        'ip_trade': 'Intermediate product trade',
        'fabrication': 'Fabrication',
        'indirect_trade': 'Indirect trade',
        'in_use': 'Use phase',
        'outflow_buffer': 'Outflow buffer',
        'obsolete': 'Obsolete stocks',
        'eol_market': 'End of life product market',
        'eol_trade': 'End of life trade',
        'recycling': 'Recycling',
        'scrap_market': 'Scrap market',
        'excess_scrap': 'Excess scrap'
    }

    def set_up_definition(self):
        dimensions = [
            DimensionDefinition(name='Time', dim_letter='t', dtype=int),
            DimensionDefinition(name='Element', dim_letter='e', dtype=str),
            DimensionDefinition(name='Region', dim_letter='r', dtype=str),
            DimensionDefinition(name='Intermediate', dim_letter='i', dtype=str),
            DimensionDefinition(name='Good', dim_letter='g', dtype=str),
            DimensionDefinition(name='Scenario', dim_letter='s', dtype=str),
            DimensionDefinition(name='Historic Time', dim_letter='h', dtype=int),
        ]

        processes = [
            'sysenv',
            'bof_production',
            'eaf_production',
            'forming',
            'fabrication_buffer',
            'ip_market',
            'ip_trade',
            'fabrication',
            'indirect_trade',
            'use',
            'outflow_buffer',
            'obsolete',
            'eol_market',
            'eol_trade',
            'recycling',
            'scrap_market',
            'excess_scrap'
        ]

        # names are auto-generated, see Flow class documetation
        flows = [
            FlowDefinition(from_process='sysenv', to_process='bof_production', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='scrap_market', to_process='bof_production', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='bof_production', to_process='forming', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='bof_production', to_process='sysenv', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='scrap_market', to_process='eaf_production', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='eaf_production', to_process='forming', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='eaf_production', to_process='sysenv', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='forming', to_process='ip_market', dim_letters=('t', 'e', 'r', 'i', 's')),
            FlowDefinition(from_process='forming', to_process='fabrication_buffer', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='forming', to_process='sysenv', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='ip_market', to_process='fabrication', dim_letters=('t', 'e', 'r', 'i', 's')),
            FlowDefinition(from_process='ip_market', to_process='ip_trade', dim_letters=('t', 'e', 'r', 'i', 's')),
            FlowDefinition(from_process='ip_trade', to_process='ip_market', dim_letters=('t', 'e', 'r', 'i', 's')),
            FlowDefinition(from_process='fabrication', to_process='use', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='fabrication', to_process='fabrication_buffer', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='fabrication_buffer', to_process='scrap_market', dim_letters=('t', 'e', 'r', 's')),
            FlowDefinition(from_process='use', to_process='outflow_buffer', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='use', to_process='indirect_trade', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='indirect_trade', to_process='use', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='outflow_buffer', to_process='obsolete', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='outflow_buffer', to_process='eol_market', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='eol_market', to_process='recycling', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='eol_market', to_process='eol_trade', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='eol_trade', to_process='eol_market', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='sysenv', to_process='recycling', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='recycling', to_process='scrap_market', dim_letters=('t', 'e', 'r', 'g', 's')),
            FlowDefinition(from_process='scrap_market', to_process='excess_scrap', dim_letters=('t', 'e', 'r', 's'))
        ]

        stocks = [
            StockDefinition(name='use', process='use', dim_letters=('t', 'e', 'r', 'g', 's')),
            StockDefinition(name='outflow_buffer', process='outflow_buffer', dim_letters=('t', 'e', 'r', 'g', 's')),
            StockDefinition(name='obsolete', process='obsolete', dim_letters=('t', 'e', 'r', 'g', 's')),
            StockDefinition(name='fabrication_buffer', process='fabrication_buffer', dim_letters=('t', 'e', 'r', 's')),
            StockDefinition(name='excess_scrap', process='excess_scrap', dim_letters=('t', 'e', 'r', 's'))
        ]

        parameters = [
            ParameterDefinition(name='forming_yield', dim_letters=('i',)),
            ParameterDefinition(name='fabrication_yield', dim_letters=('g',)),
            ParameterDefinition(name='recovery_rate', dim_letters=('g',)),
            ParameterDefinition(name='external_copper_rate', dim_letters=('g',)),
            ParameterDefinition(name='cu_tolerances', dim_letters=('i',)),
            ParameterDefinition(name='good_to_intermediate_distribution', dim_letters=('g', 'i')),

            ParameterDefinition(name='production', dim_letters=('h', 'r')),
            ParameterDefinition(name='population', dim_letters=('t', 'r', 's')),
            ParameterDefinition(name='gdppc', dim_letters=('t', 'r', 's')),

            # in use dynamic stock model
            #dict(name='dsms_steel/inflows_base', dim_letters=('t','r','g','s')),
            #dict(name='dsms_steel/stocks_base', dim_letters=('t', 'r', 'g', 's')),
            #dict(name='dsms_steel/outflows_base', dim_letters=('t', 'r', 'g', 's')),
        ]

        scalar_parameters = [
            dict(name='max_scrap_share_base_model'),
            dict(name='scrap_in_bof_rate'),
            dict(name='forming_losses'),
            dict(name='production_yield'),
        ]

        return MFADefinition(
            dimensions=dimensions,
            processes=processes,
            flows=flows,
            stocks=stocks,
            parameters=parameters,
            scalar_parameters=scalar_parameters,
        )
