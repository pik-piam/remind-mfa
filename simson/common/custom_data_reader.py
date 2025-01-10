import logging
import os
from typing import List

from sodym.data_reader import CompoundDataReader, CSVDimensionReader, CSVParameterReader
from sodym.mfa_definition import MFADefinition


class CustomDataReader(CompoundDataReader):
    dimension_map = {
        'Time': 'time_in_years',
        'Historic Time': 'historic_years',
        'Element': 'elements',
        'Region': 'regions',
        'Material': 'materials',
        'Good': 'goods_in_use',
        'Intermediate': 'intermediate_products',
        'Scenario': 'scenarios',
    }
    def __init__(self, input_data_path, definition: MFADefinition):
        self.input_data_path = input_data_path

        dimension_files = {}
        for dimension in definition.dimensions:
            dimension_filename = self.dimension_map[dimension.name]
            dimension_files[dimension.name] = os.path.join(
                self.input_data_path, 'dimensions', f'{dimension_filename}.csv'
            )
        dimension_reader = CSVDimensionReader(dimension_files)

        parameter_files = {}
        for parameter in definition.parameters:
            parameter_files[parameter.name] = os.path.join(
                self.input_data_path, 'datasets', f'{parameter.name}.csv'
            )
        parameter_reader = CSVParameterReader(parameter_files)

        super().__init__(dimension_reader=dimension_reader, parameter_reader=parameter_reader)
