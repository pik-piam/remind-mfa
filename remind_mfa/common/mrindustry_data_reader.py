import os
import tarfile
import flodym as fd


class MrindustryDataReader(fd.CompoundDataReader):
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

    def __init__(self, input_data_path, tgz_filename, definition: fd.MFADefinition):
        self.input_data_path = input_data_path

        # prepare directory for extracted input data
        self.extracted_input_data_path = os.path.join(self.input_data_path, "input_data")
        os.makedirs(self.extracted_input_data_path, exist_ok=True)
        version = tgz_filename.replace(".tgz", "")
        version_file_path = os.path.join(self.extracted_input_data_path, "version.txt")

        # check if extraction is needed
        should_extract = True
        if os.path.exists(version_file_path):
            with open(version_file_path, "r") as f:
                current_version = f.read()
                if current_version == version:
                    should_extract = False

        # dimensions
        dimension_files = {}
        for dimension in definition.dimensions:
            dimension_filename = self.dimension_map[dimension.name]
            dimension_files[dimension.name] = os.path.join(
                self.input_data_path, "dimensions", f"{dimension_filename}.csv"
            )
        dimension_reader = fd.CSVDimensionReader(dimension_files)

        if should_extract:
            # extract files from tgz and save in directory
            tgz_path = os.path.join(self.input_data_path, tgz_filename)
            if not os.path.exists(tgz_path):
                raise FileNotFoundError(f"TGZ file not found: {tgz_path}")

            with tarfile.open(tgz_path, "r:gz") as tar:
                tar.extractall(path=self.extracted_input_data_path)

            with open(version_file_path, "w") as f:
                f.write(version)
        
        # parameters
        parameter_files = {}
        for parameter in definition.parameters:
            parameter_files[parameter.name] = os.path.join(
                self.temp_dir, "datasets", f"{parameter.name}.cs4r"
            )
        parameter_reader = CS4RParameterReader(parameter_files, allow_extra_values=True)

        super().__init__(dimension_reader=dimension_reader, parameter_reader=parameter_reader)


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

