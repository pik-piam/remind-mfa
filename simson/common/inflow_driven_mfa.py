import numpy as np
from pydantic import field_validator
from sodym import MFASystem, StockArray, DimensionSet
from sodym.stock_helper import create_dynamic_stock


class InflowDrivenHistoricMFA(MFASystem):
    """Calculate in-use stock based on historic production data."""

    @field_validator('mfa_cfg')
    def dynamic_stock_info_exists(cls, d: dict):
        if 'ldf_type' not in d:
            raise ValueError(f'Missing ldf_type in {cls.__name__}')
        return d

    @field_validator('parameters')
    def dynamic_stock_parameters_exist(cls, d: dict):
        if 'lifetime_mean' not in d or 'lifetime_std' not in d:
            raise ValueError(
                f'lifetime_mean and lifetime_std must be specified in the parameters of an '
                f'{cls.__name__} instance.'
            )
        if 'production' not in d:
            raise ValueError(
                f'production data needs to be in the parameters of an {cls.__name__} instance.'
            )
        return d

    @field_validator('dims', mode='after')
    def required_dimensions_exist(cls, dimension_set: DimensionSet):
        required = ['h', 'r', 'g']
        exists = [True if letter in dimension_set.letters else False for letter in required]
        if not np.all(exists):
            raise ValueError(f'{cls.__name__} requires the dimensions {required}.')
        return dimension_set

    @property
    def use(self):
        return self.processes['use']

    def compute(self):
        inflow = StockArray(
            dims=self.dims.get_subset(('h', 'r', 'g')),
            values=self.parameters['production'].values,
            name='in_use_inflow'
        )
        hist_stk = create_dynamic_stock(
            name='in_use', process=self.use, ldf_type=self.mfa_cfg['ldf_type'],
            inflow=inflow, lifetime_mean=self.parameters['lifetime_mean'],
            lifetime_std=self.parameters['lifetime_std'], time_letter='h',
        )
        hist_stk.compute()
        self.stocks['in_use'] = hist_stk
