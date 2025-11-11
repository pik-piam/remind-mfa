import os
import glob
import tarfile
import pandas as pd
import flodym as fd

from remind_mfa.common.common_cfg import GeneralCfg


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

    def __init__(
        self,
        cfg: GeneralCfg,
        definition: fd.MFADefinition,
        allow_missing_values: bool = False,
        allow_extra_values: bool = False,
    ):
        self.model_class = cfg.model_class
        self.madrat_output_path = cfg.madrat_output_path
        self.input_data_path = cfg.input_data_path
        self.input_data_version = cfg.input_data_version
        self.definition = definition
        self.allow_missing_values = allow_missing_values
        self.allow_extra_values = allow_extra_values
        self.prepare_input_readers()

    def prepare_input_readers(self):

        # prepare directory for extracted input data
        self.extracted_input_data_path = os.path.join(self.input_data_path, "input_data")
        os.makedirs(self.extracted_input_data_path, exist_ok=True)
        version_file_path = os.path.join(self.extracted_input_data_path, "version.txt")

        # check if extraction is needed
        should_extract = True
        if os.path.exists(version_file_path):
            with open(version_file_path, "r") as f:
                current_version = f.read()
                if current_version == self.input_data_version:
                    should_extract = False

        if should_extract:
            # extract files from tgz and save in directory
            tgz_path = os.path.join(self.madrat_output_path, self.input_data_version + ".tgz")
            if not os.path.exists(tgz_path):
                raise FileNotFoundError(f"TGZ file not found: {tgz_path}")

            with tarfile.open(tgz_path, "r:gz") as tar:
                tar.extractall(path=self.extracted_input_data_path)

            with open(version_file_path, "w") as f:
                f.write(self.input_data_version)

        # dimensions
        dimension_files = {}
        for dimension in self.definition.dimensions:
            dimension_filename = self.dimension_map[dimension.name]
            dimension_files[dimension.name] = os.path.join(
                self.input_data_path, "dimensions", f"{dimension_filename}.csv"
            )
        # Special case for Region dimensions
        if "Region" in dimension_files:
            regionfiles = sorted(
                glob.glob(os.path.join(self.extracted_input_data_path, "regionmapping*.csv"))
            )
            if not regionfiles:
                raise FileNotFoundError(f"No regionmapping*.csv found in {self.input_data_path}")
            if len(regionfiles) > 1:
                raise ValueError(
                    f"Expected exactly one regionmapping*.csv in {self.input_data_path}, found: "
                    f"{[os.path.basename(m) for m in regionfiles]}"
                )
            dimension_files["Region"] = regionfiles[0]
        dimension_reader = MrindustryDimensionReader(dimension_files)

        # parameters
        parameter_prefix = self.model_class[:2]
        parameter_files = {}
        for parameter in self.definition.parameters:
            material_specific_file = os.path.join(
                self.extracted_input_data_path, f"{parameter_prefix}_{parameter.name}.cs4r"
            )
            parameter_files[parameter.name] = (
                material_specific_file
                if os.path.exists(material_specific_file)
                # fall back to common parameters
                else os.path.join(self.extracted_input_data_path, f"co_{parameter.name}.cs4r")
            )
        parameter_reader = MrindustryParameterReader(parameter_files,
                                                     allow_extra_values=self.allow_extra_values,
                                                     allow_missing_values=self.allow_missing_values)

        super().__init__(dimension_reader=dimension_reader, parameter_reader=parameter_reader)


class MrindustryDimensionReader(fd.CSVDimensionReader):
    """
    Custom dimension reader that reads Region dimensions from mrindustry regionmapping .csv.
    Everything else works as in flodym.CSVDimensionReader.
    """

    def read_dimension(self, definition: fd.DimensionDefinition):
        if definition.name == "Region":
            path = self.dimension_files[definition.name]
            df = pd.read_csv(path, delimiter=";")
            unique_regions = df["RegionCode"].unique()
            return fd.Dimension.from_np(unique_regions, definition)
        else:
            return super().read_dimension(definition)


class MrindustryParameterReader(fd.CSVParameterReader):
    """
    Custom parameter reader for .cs4r files that extracts header and skiprows information from the file.
    Everything else inherited from flodym.CSVParameterReader.
    """

    def read_parameter_values(self, parameter_name: str, dims):
        self.pre_read_parameter_values(parameter_name)
        return super().read_parameter_values(parameter_name, dims)

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
        pre_str = "dimensions: ("
        post_str = ")"
        with open(filepath, "r") as file:
            for idx, line in enumerate(file):
                if line.startswith("*"):
                    if pre_str in line:
                        # extract header between pre_str and post_str
                        header_str = line.split(pre_str)[1].split(post_str)[0]
                        header = [dim.strip() for dim in header_str.split(",")]
                else:
                    if header is None:
                        raise ValueError(f"No header line found in {filepath}")
                    break
        return header, idx
