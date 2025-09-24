import os
import flodym as fd


class REMINDMFAReader(fd.CompoundDataReader):
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
                self.input_data_path, "datasets", f"{parameter.name}.cs4r"
            )
        parameter_reader = CS4RParameterReader(parameter_files, allow_extra_values=True)

        super().__init__(dimension_reader=dimension_reader, parameter_reader=parameter_reader)
        print("test")


class CS4RParameterReader(fd.CSVParameterReader):
    """
    Custom parameter reader for .cs4r files that extracts header and skiprows information from the file.
    Everything else inherited from flodym.CSVParameterReader.
    """

    def read_parameter_values(self, parameter_name: str, dims):
        self.pre_read_parameter_values(parameter_name)
        super().read_parameter_values(parameter_name, dims)
        
    def pre_read_parameter_values(self, parameter_name: str):
        """Extract header and skiprows from .cs4r file and set read_csv_kwargs accordingly."""
        if self.parameter_filenames is None:
            raise ValueError("No parameter files specified.")
        datasets_path = self.parameter_filenames[parameter_name]
        header, skiprows = self.extract_cs4r_info(datasets_path)
        self.read_csv_kwargs = {"names": header, "skiprows": skiprows}

    @staticmethod
    def extract_cs4r_info(filepath: str):
        """Extract header and skiprows from .cs4r file."""
        pre_str = "(dimensions: "
        post_str = ")"
        with open(filepath, 'r') as file:
            for idx, line in enumerate(file):
                if line.startswith('*'):
                    if pre_str in line:
                        # extract header between pre_str and post_str
                        header_str = line.split(pre_str)[1].split(post_str)[0]
                        header = [dim.strip() for dim in header_str.split(',')]
                else:
                    if header is None:
                        raise ValueError(f"No header line found in {filepath}")
                    break
        header_line_count = idx + 1
        return header, header_line_count

