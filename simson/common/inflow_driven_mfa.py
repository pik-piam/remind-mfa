import numpy as np
from pydantic import field_validator
from flodym import MFASystem, DimensionSet


class InflowDrivenHistoricMFA(MFASystem):
    """Calculate in-use stock based on historic production data."""

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

    def compute(self):
        self.stocks['in_use'].compute()
