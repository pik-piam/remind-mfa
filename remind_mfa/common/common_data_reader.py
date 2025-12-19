import os
import glob
import tarfile
import shutil
import pandas as pd
import flodym as fd

from remind_mfa.common.common_config import CommonCfg
from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.common.common_mappings import CommonDimensionFiles
from remind_mfa.common.helpers import prefix_from_module, module_from_prefix


class CommonDataReader(fd.CompoundDataReader):

    def __init__(
        self,
        cfg: CommonCfg,
        definition: RemindMFADefinition,
        dimension_file_mapping: CommonDimensionFiles,
        allow_missing_values: bool = False,
        allow_extra_values: bool = False,
    ):
        self.dimension_file_mapping = dimension_file_mapping
        self.model_class = cfg.model
        self.madrat_output_path = cfg.input.madrat_output_path
        self.input_data_path = cfg.input.input_data_path
        self.input_data_version = cfg.input.input_data_version
        self.force_extract = cfg.input.force_extract_tgz
        self.definition = definition
        self.allow_missing_values = allow_missing_values
        self.allow_extra_values = allow_extra_values
        self.prepare_input_readers()

    @property
    def tmp_extraction_path(self) -> str:
        return os.path.join(self.input_data_path, "tmp")

    @property
    def version_filename(self) -> str:
        return "version.txt"

    def get_material_path(self, material: str) -> str:
        return os.path.join(self.input_data_path, material)

    def get_material_parameter_path(self, material: str) -> str:
        # TODO rename this folder to "paramters" instead of input_data
        parameter_foldername = "input_data"
        return os.path.join(self.get_material_path(material), parameter_foldername)

    def get_material_dimension_path(self, material: str) -> str:
        dimensions_foldername = "dimensions"
        return os.path.join(self.get_material_path(material), dimensions_foldername)

    def prepare_input_readers(self):
        # prepare directory for extracted input data
        material_parameter_path = self.get_material_parameter_path(self.model_class)
        os.makedirs(material_parameter_path, exist_ok=True)
        version_file_path = os.path.join(material_parameter_path, self.version_filename)

        # extract tar file if needed
        if self.extraction_needed(version_file_path):
            self.extract_tar_file()

        # dimensions
        dimension_files = self.get_dimension_dict(material_parameter_path)
        dimension_reader = CommonDimensionReader(dimension_files)

        # parameters
        parameter_files = self.get_parameter_dict(material_parameter_path)
        parameter_reader = MadratParameterReader(
            parameter_files,
            allow_extra_values=self.allow_extra_values,
            allow_missing_values=self.allow_missing_values,
        )

        super().__init__(dimension_reader=dimension_reader, parameter_reader=parameter_reader)

    def extraction_needed(self, version_file_path: str) -> bool:
        should_extract = True
        if not self.force_extract:
            if os.path.exists(version_file_path):
                with open(version_file_path, "r") as f:
                    current_version = f.read()
                    if current_version == self.input_data_version:
                        should_extract = False
        return should_extract

    def extract_tar_file(self):
        """Extracts the tgz file from madrat output path to the input data path."""
        tgz_path = os.path.join(self.madrat_output_path, self.input_data_version + ".tgz")
        if not os.path.exists(tgz_path):
            raise FileNotFoundError(f"TGZ file not found: {tgz_path}")

        self.prepare_tmp_extraction_path()

        with tarfile.open(tgz_path, "r:gz") as tar:
            tar.extractall(path=self.tmp_extraction_path)

        version_file_path = os.path.join(self.tmp_extraction_path, self.version_filename)
        with open(version_file_path, "w") as f:
            f.write(self.input_data_version)

        available_materials = self.check_available_materials()
        self.delete_old_extracted_files(available_materials)
        self.move_extracted_files(available_materials)

    def prepare_tmp_extraction_path(self):
        """Makes sure the path exists and is empty."""
        if os.path.exists(self.tmp_extraction_path):
            all_files = glob.glob(os.path.join(self.tmp_extraction_path, "*"))
            for file in all_files:
                if os.path.isfile(file):
                    os.remove(file)
                else:
                    shutil.rmtree(file)
        os.makedirs(self.tmp_extraction_path, exist_ok=True)

    def check_available_materials(self):
        """Check which material parameter files are available in the extracted path."""
        parameter_files = glob.glob(os.path.join(self.tmp_extraction_path, "*.cs4r"))
        self.validate_parameter_files(parameter_files)

        available_materials = set()
        for filepath in parameter_files:
            filename = os.path.basename(filepath)
            prefix = filename.split("_")[0]
            material = module_from_prefix(prefix)
            available_materials.add(material)
        if self.model_class not in available_materials:
            raise ValueError(
                f"Selected tar version '{self.input_data_version}' "
                f"does not contain parameter files for the selected model '{self.model_class}'. "
                f"Only parameters of the following materials are available: {available_materials}."
            )
        return available_materials

    def validate_parameter_files(self, parameter_files: list[str]):
        """Validate that parameter files exist, have expected format, and prefixes."""

        if not parameter_files:
            raise ValueError(
                f"No parameter files found in extracted tgz at {self.tmp_extraction_path}"
            )

        for filepath in parameter_files:
            filename = os.path.basename(filepath)
            if "_" not in filename:
                raise ValueError(
                    f"Unexpected filename format: {filename}. "
                    "Must have form of 'prefix_parametername.cs4r'"
                )
            prefix = filename.split("_")[0]
            try:
                _ = module_from_prefix(prefix)
            except ValueError as e:
                raise ValueError(f"Unexpected prefix '{prefix}' in filename '{filename}'.") from e

    def delete_old_extracted_files(self, available_materials: set[str]):
        """Delete old extracted files (parameters, version, regionmapping) for each newly available material."""
        for material in available_materials:
            material_parameter_path = self.get_material_parameter_path(material)
            old_files = glob.glob(os.path.join(material_parameter_path, "*"))
            for old_file in old_files:
                if os.path.isfile(old_file):
                    os.remove(old_file)
                else:
                    raise ValueError(
                        f"Expected only files in {material_parameter_path}, found directory: {old_file}"
                    )

    def move_file_to_material(self, oldpath: str, material: str, copy: bool = False):
        """Move a single file to material parameter path."""
        filename = os.path.basename(oldpath)
        material_parameter_path = self.get_material_parameter_path(material)
        os.makedirs(material_parameter_path, exist_ok=True)
        destination = os.path.join(material_parameter_path, filename)
        if copy:
            shutil.copy2(oldpath, destination)
        else:
            shutil.move(oldpath, destination)

    def move_extracted_files(self, available_materials: set[str]):
        """Move extracted files from temporary extraction path to material parameter path."""
        parameter_files = glob.glob(os.path.join(self.tmp_extraction_path, "*.cs4r"))
        # Find other files like regionmapping and version file.
        # Does not include hidden files like .gitignore.
        all_files = glob.glob(os.path.join(self.tmp_extraction_path, "*"))
        other_files = set(all_files) - set(parameter_files)

        for parameter_file in parameter_files:
            filename = os.path.basename(parameter_file)
            prefix = filename.split("_")[0]
            material = module_from_prefix(prefix)
            self.move_file_to_material(parameter_file, material)

        # copy regionmapping and version file to all available materials
        for other_file in other_files:
            for material in available_materials:
                self.move_file_to_material(other_file, material, copy=True)
            os.remove(other_file)

    def get_dimension_dict(self, material_parameter_path: str) -> dict[str, str]:
        material_path = self.get_material_path(self.model_class)
        material_dimension_path = self.get_material_dimension_path(self.model_class)

        dimension_files = {}
        for dimension in self.definition.dimensions:
            dimension_filename = self.dimension_file_mapping[dimension.name]
            dimension_files[dimension.name] = os.path.join(
                material_dimension_path, f"{dimension_filename}.csv"
            )
        # Special case for Region dimensions
        if "Region" in dimension_files:
            regionfiles = sorted(
                glob.glob(os.path.join(material_parameter_path, "regionmapping*.csv"))
            )
            if not regionfiles:
                raise FileNotFoundError(f"No regionmapping*.csv found in {material_path}")
            if len(regionfiles) > 1:
                raise ValueError(
                    f"Expected exactly one regionmapping*.csv in {material_path}, found: "
                    f"{[os.path.basename(m) for m in regionfiles]}"
                )
            dimension_files["Region"] = regionfiles[0]

        return dimension_files

    def get_parameter_dict(self, material_parameter_path) -> dict[str, str]:
        material_prefix = prefix_from_module(self.model_class)
        parameter_files = {}
        for parameter in self.definition.parameters:
            material_specific_file = os.path.join(
                material_parameter_path, f"{material_prefix}_{parameter.name}.cs4r"
            )
            parameter_files[parameter.name] = material_specific_file

        return parameter_files


class CommonDimensionReader(fd.CSVDimensionReader):
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


class MadratParameterReader(fd.CSVParameterReader):
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
        header = None
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
