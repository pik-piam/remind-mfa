import os
import flodym as fd


class CustomDataReader(fd.CompoundDataReader):
    dimension_map = {
        "Time": "time_in_years",
        "Historic Time": "historic_years",
        "Element": "elements",
        "Region": "regions",
        "Material": "materials",
        "Good": "goods_in_use",
        "Intermediate": "intermediate_products",
        "Scenario": "scenarios",
    }

    def __init__(self, input_data_path, definition: fd.MFADefinition):
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
        parameter_reader = fd.CSVParameterReader(parameter_files)

        super().__init__(dimension_reader=dimension_reader, parameter_reader=parameter_reader)
