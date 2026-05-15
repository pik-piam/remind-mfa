import os
import glob
import pickle
import tarfile
import pandas as pd
import flodym as fd
from typing import Optional

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
        self.input_data_path = cfg.input.input_data_path
        self.input_data_revision = cfg.input.input_data_revision
        self.region_mapping = cfg.input.region_mapping
        self.madrat_output_path = self.resolve_madrat_output_path(cfg.input.madrat_output_path)
        self.force_extract = cfg.input.force_extract_tgz
        self.definition = definition
        self.allow_missing_values = allow_missing_values
        self.allow_extra_values = allow_extra_values
        self.transience_scenario = cfg.transience.transience_scenario
        self.prepare_input_readers()
        self.baseline_pickle_path = os.path.join(*(cfg.export.path, "pickle"), cfg.transience.baseline_pickle_path) if cfg.transience.baseline_pickle_path else None

    @property
    def shared_parameter_path(self) -> str:
        return os.path.join(self.input_data_path, "input_data")

    @property
    def rev_filename(self) -> str:
        return "rev.txt"

    @property
    def regions_filename(self) -> str:
        return "regions.txt"

    @staticmethod
    def resolve_madrat_output_path(configured_path: str | None) -> str:
        if configured_path is not None:
            return configured_path
        env_path = os.environ.get("MADRAT_OUTPUTFOLDER")
        if env_path is None:
            raise ValueError(
                "No madrat output path configured. Set input.madrat_output_path or "
                "environment variable MADRAT_OUTPUTFOLDER."
            )
        return env_path

    def get_material_dimension_path(self, material: str) -> str:
        return os.path.join(self.input_data_path, "dimensions", material)

    def prepare_input_readers(self):
        # prepare directory for extracted input data
        os.makedirs(self.shared_parameter_path, exist_ok=True)

        # extract tar file if needed
        if self.extraction_needed(self.shared_parameter_path):
            self.extract_tar_file(self.shared_parameter_path)

        # dimensions
        dimension_files = self.get_dimension_dict(self.shared_parameter_path)
        dimension_reader = CommonDimensionReader(dimension_files)

        # parameters
        parameter_files = self.get_parameter_dict(self.shared_parameter_path)
        self.validate_parameter_files(parameter_files)
        parameter_reader = MadratParameterReader(
            parameter_files,
            allow_extra_values=self.allow_extra_values,
            allow_missing_values=self.allow_missing_values,
        )

        super().__init__(dimension_reader=dimension_reader, parameter_reader=parameter_reader)

    @staticmethod
    def read_text_file(path: str) -> str | None:
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            return f.read().strip()

    @staticmethod
    def write_text_file(path: str, value: str):
        with open(path, "w") as f:
            f.write(value)

    @staticmethod
    def parse_archive_name(filename: str) -> tuple[str, str]:
        stem = os.path.basename(filename)
        if stem.endswith(".tgz"):
            stem = stem[: -len(".tgz")]

        if not stem.startswith("rev") or not stem.endswith("_mfa"):
            raise ValueError(
                f"Invalid archive name '{filename}'. Expected format rev<rev>_<regions>_<hash>_mfa.tgz"
            )

        payload = stem[len("rev") : -len("_mfa")]
        parts = payload.split("_")
        if len(parts) < 3:
            raise ValueError(
                f"Invalid archive name '{filename}'. Expected format rev<rev>_<regions>_<hash>_mfa.tgz"
            )

        rev = "_".join(parts[:-2]).strip()
        regions = parts[-2].strip()
        if not rev or not regions:
            raise ValueError(
                f"Invalid archive name '{filename}'. Could not determine rev and regions."
            )

        return rev, regions

    def extraction_needed(self, material_parameter_path: str) -> bool:
        if self.force_extract:
            return True
        rev_path = os.path.join(material_parameter_path, self.rev_filename)
        regions_path = os.path.join(material_parameter_path, self.regions_filename)
        current_rev = self.read_text_file(rev_path)
        current_regions = self.read_text_file(regions_path)
        return current_rev != self.input_data_revision or current_regions != self.region_mapping

    def get_target_tgz_path(self) -> str:
        search_pattern = (
            f"rev{glob.escape(self.input_data_revision)}_"
            f"{glob.escape(self.region_mapping)}_*_mfa.tgz"
        )
        matches = sorted(glob.glob(os.path.join(self.madrat_output_path, search_pattern)))
        if not matches:
            raise FileNotFoundError(
                "No matching tgz archive found in "
                f"{self.madrat_output_path} for revision={self.input_data_revision}, "
                f"region_mapping={self.region_mapping}."
            )
        if len(matches) > 1:
            raise ValueError(
                "Multiple matching tgz archives found for the selected revision/region mapping. "
                "Make the selector more specific or remove duplicate archives. Matches: "
                f"{[os.path.basename(match) for match in matches]}"
            )
        return matches[0]

    def extract_tar_file(self, material_parameter_path: str):
        """Extracts the matching tgz into the shared input_data folder and stores rev/regions metadata."""
        tgz_path = self.get_target_tgz_path()

        with tarfile.open(tgz_path, "r:gz") as tar:
            tar.extractall(path=material_parameter_path)

        rev, regions = self.parse_archive_name(os.path.basename(tgz_path))
        self.write_text_file(os.path.join(material_parameter_path, self.rev_filename), rev)
        self.write_text_file(os.path.join(material_parameter_path, self.regions_filename), regions)

    def validate_parameter_files(self, parameter_files: dict[str, str]):
        """Validate that all expected parameter files for the selected model exist."""
        missing = [name for name, path in parameter_files.items() if not os.path.exists(path)]
        if missing:
            raise FileNotFoundError(
                "Missing parameter files in shared input_data folder for model "
                f"'{self.model_class}': {missing}"
            )

        for filepath in parameter_files.values():
            filename = os.path.basename(filepath)
            if "_" not in filename:
                raise ValueError(
                    f"Unexpected filename format: {filename}. "
                    "Must have form of 'prefix_parametername.cs4r'"
                )
            prefix = filename.split("_")[0]
            try:
                material = module_from_prefix(prefix)
            except ValueError as e:
                raise ValueError(f"Unexpected prefix '{prefix}' in filename '{filename}'.") from e
            if material != self.model_class:
                raise ValueError(
                    f"Parameter file '{filename}' does not belong to selected model '{self.model_class}'."
                )

    def read_baseline_trade(self) -> dict:
        """Load trade set from a baseline pickle file."""
        with open(self.baseline_pickle_path, "rb") as fh:
            baseline_model = pickle.load(fh)
        baseline_trade = baseline_model.future_mfa.trade_set
        return baseline_trade
    
    def read_baseline_flows(self) -> dict:
        """Load flows dictionary from a baseline pickle file."""
        with open(self.baseline_pickle_path, "rb") as fh:
            baseline_model = pickle.load(fh)
        baseline_flows = baseline_model.future_mfa.flows
        return baseline_flows

    def get_dimension_dict(self, material_parameter_path: str) -> dict[str, str]:
        material_dimension_path = self.get_material_dimension_path(self.model_class)

        dimension_files = {}
        for dimension in self.definition.dimensions:
            dimension_filename = self.dimension_file_mapping[dimension.name]
            dimension_files[dimension.name] = os.path.join(
                material_dimension_path, f"{dimension_filename}.csv"
            )
        # Special case for Region dimensions
        if "Region" in dimension_files:
            regionmapping_path = os.path.join(material_parameter_path, "regionmapping.csv")
            if not os.path.exists(regionmapping_path):
                raise FileNotFoundError(
                    f"No regionmapping.csv found in shared input_data folder {material_parameter_path}"
                )
            dimension_files["Region"] = regionmapping_path

        return dimension_files

    def get_parameter_dict(self, material_parameter_path) -> dict[str, str]:
        material_prefix = prefix_from_module(self.model_class)
        parameter_files = {}
        for parameter in self.definition.parameters:
            if parameter.scenario_folder is not None:
                # scenario-specific parameter: read from input_data/<scenario_folder>/<scenario>/
                scenario_path = os.path.join(
                    self.input_data_path,
                    parameter.scenario_folder,
                    self.transience_scenario,
                )
                filepath = os.path.join(
                    scenario_path, f"{material_prefix}_{parameter.name}.cs4r"
                )
            else:
                filepath = os.path.join(
                    material_parameter_path, f"{material_prefix}_{parameter.name}.cs4r"
                )
            parameter_files[parameter.name] = filepath

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
