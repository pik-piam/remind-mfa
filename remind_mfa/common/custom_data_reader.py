import os
import flodym as fd
from remind_mfa.common.helper import RemindMFADefinition


class CustomDataReader(fd.CompoundDataReader):
    dimension_map = {
    }

    def __init__(
        self,
        input_data_path,
        definition: RemindMFADefinition,
        allow_missing_values: bool = False,
        allow_extra_values: bool = False,
    ):
        self.input_data_path = input_data_path

        dimension_files = {}
        for dimension in definition.dimensions:
            dimension_filename = self.dimension_map[dimension.name]
            dimension_files[dimension.name] = os.path.join(
                self.input_data_path, "dimensions", f"{dimension_filename}.csv"
            )
        dimension_reader = fd.CSVDimensionReader(dimension_files)

        parameter_files = {}
        for parameter in definition.parameters:
            parameter_files[parameter.name] = os.path.join(
                self.input_data_path, "datasets", f"{parameter.name}.csv"
            )
        parameter_reader = fd.CSVParameterReader(
            parameter_files,
            allow_missing_values=allow_missing_values,
            allow_extra_values=allow_extra_values,
        )

        super().__init__(dimension_reader=dimension_reader, parameter_reader=parameter_reader)
