import logging
import os
from typing import List

from sodym.data_reader import CompoundDataReader, CSVDimensionReader, CSVParameterReader, YamlScalarDataReader, EmptyScalarDataReader
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
    def __init__(self, input_data_path, definition: MFADefinition, has_scalar_parameters: bool):
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

        if has_scalar_parameters:
            scalar_data_yaml = os.path.join(input_data_path, 'scalar_parameters.yml')
        else:
            scalar_data_yaml = None
        scalar_data_reader = YamlScalarDataReader(scalar_data_yaml)

        super().__init__(dimension_reader=dimension_reader, parameter_reader=parameter_reader, scalar_data_reader=scalar_data_reader)
