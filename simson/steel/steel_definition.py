from flodym import MFADefinition, DimensionDefinition, FlowDefinition, ParameterDefinition, StockDefinition, SimpleFlowDrivenStock


def get_definition():
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
        'ip_market',
        # 'ip_trade',
        'fabrication',
        # 'indirect_trade',
        'use',
        'obsolete',
        'eol_market',
        # 'eol_trade',
        'recycling',
        'scrap_market',
        'excess_scrap'
    ]

    # names are auto-generated, see Flow class documetation
    flows = [
        # Historic Flows

        FlowDefinition(from_process='sysenv', to_process='forming', dim_letters=('h', 'r', 'i')),
        FlowDefinition(from_process='forming', to_process='ip_market', dim_letters=('h', 'r', 'i')),
        FlowDefinition(from_process='forming', to_process='sysenv', dim_letters=('h', 'r')),
        FlowDefinition(from_process='ip_market', to_process='fabrication', dim_letters=('h', 'r', 'i')),
        FlowDefinition(from_process='ip_market', to_process='sysenv', dim_letters=('h', 'r', 'i')),
        FlowDefinition(from_process='sysenv', to_process='ip_market', dim_letters=('h', 'r', 'i')),
        FlowDefinition(from_process='fabrication', to_process='use', dim_letters=(('h', 'r', 'g'))),
        FlowDefinition(from_process='fabrication', to_process='sysenv', dim_letters=('h', 'r')),
        FlowDefinition(from_process='use', to_process='sysenv', dim_letters=('h', 'r', 'g')),
        FlowDefinition(from_process='sysenv', to_process='use', dim_letters=('h', 'r', 'g')),

        # Future Flows

        FlowDefinition(from_process='sysenv', to_process='bof_production', dim_letters=('t', 'e', 'r')),
        FlowDefinition(from_process='scrap_market', to_process='bof_production', dim_letters=('t', 'e', 'r')),
        FlowDefinition(from_process='bof_production', to_process='forming', dim_letters=('t', 'e', 'r')),
        FlowDefinition(from_process='bof_production', to_process='sysenv', dim_letters=('t', 'e', 'r',)),
        FlowDefinition(from_process='scrap_market', to_process='eaf_production', dim_letters=('t', 'e', 'r')),
        FlowDefinition(from_process='eaf_production', to_process='forming', dim_letters=('t', 'e', 'r')),
        FlowDefinition(from_process='eaf_production', to_process='sysenv', dim_letters=('t', 'e', 'r')),
        FlowDefinition(from_process='forming', to_process='ip_market', dim_letters=('t', 'e', 'r', 'i')),
        FlowDefinition(from_process='forming', to_process='scrap_market', dim_letters=('t', 'e', 'r')),
        FlowDefinition(from_process='forming', to_process='sysenv', dim_letters=('t', 'e', 'r')),
        FlowDefinition(from_process='ip_market', to_process='fabrication', dim_letters=('t', 'e', 'r', 'i')),
        FlowDefinition(from_process='ip_market', to_process='sysenv', dim_letters=('t', 'e', 'r', 'i')),
        FlowDefinition(from_process='sysenv', to_process='ip_market', dim_letters=('t', 'e', 'r', 'i')),
        FlowDefinition(from_process='fabrication', to_process='use', dim_letters=('t', 'e', 'r', 'g')),
        FlowDefinition(from_process='fabrication', to_process='scrap_market', dim_letters=('t', 'e', 'r')),
        FlowDefinition(from_process='use', to_process='sysenv', dim_letters=('t', 'e', 'r', 'g')),
        FlowDefinition(from_process='sysenv', to_process='use', dim_letters=('t', 'e', 'r', 'g')),
        FlowDefinition(from_process='use', to_process='obsolete', dim_letters=('t', 'e', 'r', 'g')),
        FlowDefinition(from_process='use', to_process='eol_market', dim_letters=('t', 'e', 'r', 'g')),
        FlowDefinition(from_process='eol_market', to_process='recycling', dim_letters=('t', 'e', 'r', 'g')),
        FlowDefinition(from_process='eol_market', to_process='sysenv', dim_letters=('t', 'e', 'r', 'g')),
        FlowDefinition(from_process='sysenv', to_process='eol_market', dim_letters=('t', 'e', 'r', 'g')),
        FlowDefinition(from_process='sysenv', to_process='recycling', dim_letters=('t', 'e', 'r', 'g')),
        FlowDefinition(from_process='recycling', to_process='scrap_market', dim_letters=('t', 'e', 'r', 'g')),
        FlowDefinition(from_process='scrap_market', to_process='excess_scrap', dim_letters=('t', 'e', 'r'))
    ]

    stocks = [
        StockDefinition(
            name='in_use',
            process='use',
            dim_letters=('h', 'r', 'g'),
            subclass=SimpleFlowDrivenStock,
            time_letter='h'),
        StockDefinition(name='use', process='use', dim_letters=('t', 'e', 'r', 'g'),
                        subclass=SimpleFlowDrivenStock),
        StockDefinition(name='obsolete', process='obsolete', dim_letters=('t', 'e', 'r', 'g'),
                        subclass=SimpleFlowDrivenStock),
        StockDefinition(name='excess_scrap', process='excess_scrap', dim_letters=('t', 'e', 'r'),
                        subclass=SimpleFlowDrivenStock),
    ]

    parameters = [
        ParameterDefinition(name='forming_yield', dim_letters=('i',)),
        ParameterDefinition(name='fabrication_yield', dim_letters=('g',)),
        ParameterDefinition(name='recovery_rate', dim_letters=('g',)),
        ParameterDefinition(name='external_copper_rate', dim_letters=('g',)),
        ParameterDefinition(name='cu_tolerances', dim_letters=('i',)),
        ParameterDefinition(name='good_to_intermediate_distribution', dim_letters=('g', 'i')),

        ParameterDefinition(name='production', dim_letters=('h', 'r')),
        ParameterDefinition(name='production_by_intermediate', dim_letters=('h', 'r', 'i')),
        ParameterDefinition(name='direct_imports', dim_letters=('h', 'r', 'i')),
        ParameterDefinition(name='direct_exports', dim_letters=('h', 'r', 'i')),
        ParameterDefinition(name='indirect_imports', dim_letters=('h', 'r', 'g')),
        ParameterDefinition(name='indirect_exports', dim_letters=('h', 'r', 'g')),
        ParameterDefinition(name='scrap_imports', dim_letters=('h', 'r')),
        ParameterDefinition(name='scrap_exports', dim_letters=('h', 'r')),

        ParameterDefinition(name='population', dim_letters=('t', 'r')),
        ParameterDefinition(name='gdppc', dim_letters=('t', 'r')),
        ParameterDefinition(name=f'lifetime_mean', dim_letters=('r', 'g')),
        ParameterDefinition(name=f'lifetime_std', dim_letters=('r', 'g')),

        ParameterDefinition(name='pigiron_production', dim_letters=('h', 'r')),
        ParameterDefinition(name='pigiron_imports', dim_letters=('h', 'r')),
        ParameterDefinition(name='pigiron_exports', dim_letters=('h', 'r')),
        ParameterDefinition(name='pigiron_to_cast', dim_letters=('h', 'r')),
        ParameterDefinition(name='dri_production', dim_letters=('h', 'r')),
        ParameterDefinition(name='dri_imports', dim_letters=('h', 'r')),
        ParameterDefinition(name='dri_exports', dim_letters=('h', 'r')),

        ParameterDefinition(name='lifetime_mean', dim_letters=('r', 'g')),
        ParameterDefinition(name='lifetime_std', dim_letters=('r', 'g')),

        ParameterDefinition(name='max_scrap_share_base_model', dim_letters=()),
        ParameterDefinition(name='scrap_in_bof_rate', dim_letters=()),
        ParameterDefinition(name='forming_losses', dim_letters=()),
        ParameterDefinition(name='production_yield', dim_letters=()),
    ]

    return MFADefinition(
        dimensions=dimensions,
        processes=processes,
        flows=flows,
        stocks=stocks,
        parameters=parameters,
    )