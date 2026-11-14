import glob
import os
import tarfile
import logging
from os import PathLike
from pathlib import Path

import flodym as fd
import pandas as pd

from remind_mfa.common.common_config import (
    CommonCfg,
    InputHorizonError,
    ModelSwitches,
    TimeHorizon,
)
from remind_mfa.common.common_definition import RemindMFADefinition
from remind_mfa.common.helpers import prefix_from_module

TIME_LETTER = "t"
HISTORICAL_TIME_LETTER = "h"
TIME_LETTERS = (TIME_LETTER, HISTORICAL_TIME_LETTER)
"""Letters of the time dimensions, which follow from the configured time horizon."""


class CommonDataReader(fd.CompoundDataReader):

    # Suffixes (before the ".tgz") distinguishing the two archive kinds produced by madrat:
    # the main input-data archive and the (optional) validation-data archive.
    MFA_SUFFIX = "_mfa"
    VALIDATION_SUFFIX = "_validationmfa"

    parameter_reader: "MadratParameterReader"

    def __init__(
        self,
        cfg: CommonCfg,
        definition: RemindMFADefinition,
        allow_missing_values: bool = False,
        allow_extra_values: bool = False,
    ):
        self._input_cfg = cfg.input
        self.model_class = cfg.model
        self.input_data_path = Path(cfg.input.input_data_path)
        self.input_data_revision = cfg.input.input_data_revision
        self.region_mapping = cfg.input.region_mapping
        self.force_extract = cfg.input.force_extract_tgz
        self.model_switches: ModelSwitches = cfg.model_switches
        self.definition = definition
        self.allow_missing_values = allow_missing_values
        self.allow_extra_values = allow_extra_values
        self.prepare_input_readers()

    @property
    def parameters_path(self) -> Path:
        return self.input_data_path / "parameters"

    @property
    def legacy_parameters_path(self) -> Path:
        return self.input_data_path / "legacy" / "input_data"

    @property
    def region_mappings_path(self) -> Path:
        return self.input_data_path / "piam_mappings" / "regional"

    @property
    def validation_path(self) -> Path:
        return self.input_data_path / "validation"

    @property
    def dimensions_path(self) -> Path:
        return self.input_data_path / "dimensions" / self.model_class

    @property
    def rev_filename(self) -> str:
        return "rev.txt"

    @property
    def regions_filename(self) -> str:
        return "regions.txt"

    def prepare_input_readers(self):
        # prepare directory for extracted input data
        self.parameters_path.mkdir(parents=True, exist_ok=True)

        # extract tar file if needed
        if self.extraction_needed(self.parameters_path):
            self.extract_tar_file(self.parameters_path)

        # extract the matching validation archive (optional; warns if not found)
        if self.extraction_needed(self.validation_path):
            self.extract_validation_tar_file(self.validation_path)

        self.time_horizon = self.model_switches.resolve_time_horizon(self.read_input_time_horizon())

        # dimensions
        dimension_files = self.get_dimension_files()
        dimension_reader = CommonDimensionReader(dimension_files)

        # parameters
        parameter_files = self.get_parameter_files()
        input_label = f"revision {self.input_data_revision}, region mapping {self.region_mapping}"
        parameter_reader = MadratParameterReader(
            parameter_files,
            time_horizon=self.time_horizon,
            input_label=input_label,
            allow_extra_values=self.allow_extra_values,
            allow_missing_values=self.allow_missing_values,
        )

        super().__init__(dimension_reader=dimension_reader, parameter_reader=parameter_reader)

    @staticmethod
    def read_text_file(path: str | os.PathLike[str]) -> str | None:
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            return f.read().strip()

    @staticmethod
    def write_text_file(path: str | os.PathLike[str], value: str):
        with open(path, "w") as f:
            f.write(value)

    @classmethod
    def parse_archive_name(cls, filename: str, suffix: str = MFA_SUFFIX) -> tuple[str, str]:
        stem = os.path.basename(filename)
        stem = stem.removesuffix(".tgz")

        if not stem.startswith("rev") or not stem.endswith(suffix):
            raise ValueError(
                f"Invalid archive name '{filename}'. Expected format rev<rev>_<regions>_<hash>{suffix}.tgz"
            )

        payload = stem[len("rev") : -len(suffix)]
        parts = payload.split("_")
        if len(parts) < 3:
            raise ValueError(
                f"Invalid archive name '{filename}'. Expected format rev<rev>_<regions>_<hash>{suffix}.tgz"
            )

        rev = "_".join(parts[:-2]).strip()
        regions = parts[-2].strip()
        if not rev or not regions:
            raise ValueError(
                f"Invalid archive name '{filename}'. Could not determine rev and regions."
            )

        return rev, regions

    def extraction_needed(self, parameters_path: Path) -> bool:
        if self.force_extract:
            return True
        rev_path = parameters_path / self.rev_filename
        regions_path = parameters_path / self.regions_filename
        current_rev = self.read_text_file(rev_path)
        current_regions = self.read_text_file(regions_path)
        return current_rev != self.input_data_revision or current_regions != self.region_mapping

    @staticmethod
    def build_target_tgz_pattern(
        input_data_revision: str, region_mapping: str, suffix: str = MFA_SUFFIX
    ) -> str:
        return (
            f"rev{glob.escape(input_data_revision)}_" f"{glob.escape(region_mapping)}_*{suffix}.tgz"
        )

    def find_target_tgz_paths(self, suffix: str = MFA_SUFFIX) -> list[str]:
        """Return all madrat archives matching the configured revision/region and given suffix."""
        search_pattern = self.build_target_tgz_pattern(
            self.input_data_revision, self.region_mapping, suffix
        )
        return sorted(
            glob.glob(os.path.join(self._input_cfg.resolved_madrat_output_path, search_pattern))
        )

    def get_target_tgz_path(self, suffix: str = MFA_SUFFIX) -> str:
        matches = self.find_target_tgz_paths(suffix)
        if not matches:
            raise FileNotFoundError(
                "No matching tgz archive found in "
                f"{self._input_cfg.resolved_madrat_output_path} for revision={self.input_data_revision}, "
                f"region_mapping={self.region_mapping}, suffix={suffix}."
            )
        if len(matches) > 1:
            raise ValueError(
                "Multiple matching tgz archives found for the selected revision/region mapping. "
                "Make the selector more specific or remove duplicate archives. Matches: "
                f"{[os.path.basename(match) for match in matches]}"
            )
        return matches[0]

    def extract_tar_file(self, parameters_path: Path):
        """Extracts the matching tgz into the shared input_data folder and stores rev/regions metadata."""
        if not os.path.isdir(self._input_cfg.resolved_madrat_output_path):
            raise FileNotFoundError(
                f"MADRAT output path '{self._input_cfg.resolved_madrat_output_path}' does not exist. It is required to extract the "
                "input-data archive for the configured revision/region mapping. Set "
                "input.madrat_output_path or the MADRAT_OUTPUTFOLDER environment variable to an "
                "existing directory containing the rev*_mfa.tgz archive."
            )

        tgz_path = self.get_target_tgz_path(self.MFA_SUFFIX)
        self._extract_and_record(tgz_path, parameters_path)

    def extract_validation_tar_file(self, validation_path: Path):
        """Extracts the validation tgz matching the configured revision/region into ``validation_path``.

        The validation archive is optional: if no archive matching the current input-data
        revision and region mapping is found, a warning is issued and extraction is skipped
        (rather than raising, as the main input-data archive does).
        """
        try:
            madrat_output_path = self._input_cfg.resolved_madrat_output_path
        except ValueError:
            madrat_output_path = None
        if not madrat_output_path or not os.path.isdir(madrat_output_path):
            logging.warning(
                "No MADRAT output path available to extract the validation archive "
                f"(revision={self.input_data_revision}, region_mapping={self.region_mapping}). "
                "Validation data will not be available.",
                stacklevel=2,
            )
            return

        matches = self.find_target_tgz_paths(self.VALIDATION_SUFFIX)
        if not matches:
            logging.warning(
                "No validation tgz archive found in "
                f"'{self._input_cfg.resolved_madrat_output_path}' for revision="
                f"{self.input_data_revision}, region_mapping={self.region_mapping} "
                f"(expected a rev*{self.VALIDATION_SUFFIX}.tgz archive). "
                "Validation data will not be available.",
                stacklevel=2,
            )
            return
        if len(matches) > 1:
            raise ValueError(
                "Multiple matching validation tgz archives found for the selected revision/region "
                "mapping. Make the selector more specific or remove duplicate archives. Matches: "
                f"{[os.path.basename(match) for match in matches]}"
            )

        self._extract_and_record(matches[0], validation_path, suffix=self.VALIDATION_SUFFIX)

    def _extract_and_record(
        self,
        tgz_path: str,
        target_path: Path,
        suffix: str = MFA_SUFFIX,
    ):
        """Extract ``tgz_path`` into ``target_path`` and record its rev/regions metadata there."""
        logging.info(f"Extracting new input data from {tgz_path} into {target_path}...")
        target_path.mkdir(parents=True, exist_ok=True)

        with tarfile.open(tgz_path, "r:gz") as tar:
            tar.extractall(target_path)

        rev, regions = self.parse_archive_name(os.path.basename(tgz_path), suffix)
        self.write_text_file(os.path.join(target_path, self.rev_filename), rev)
        self.write_text_file(os.path.join(target_path, self.regions_filename), regions)

    def _validate_files(self, kind: str, files: dict[str, str | os.PathLike[str]]):
        missing = {name: path for name, path in files.items() if not Path(path).exists()}
        if missing:
            raise FileNotFoundError(
                f"Missing {kind} files for model "
                f"'{self.model_class.value}': { [f'{name} -> {path!r}' for name, path in missing.items()]}"
            )

    def read_dimension(self, definition: fd.DimensionDefinition) -> fd.Dimension:
        """Build the time dimensions from the configured time horizon, read the others from files."""
        if definition.letter == TIME_LETTER:
            years = self.time_horizon.years
        elif definition.letter == HISTORICAL_TIME_LETTER:
            years = self.time_horizon.historical_years
        else:
            return super().read_dimension(definition)
        return fd.Dimension(
            name=definition.name,
            letter=definition.letter,
            items=list(years),
            dtype=definition.dtype,
        )

    def read_parameters(
        self, parameter_definitions: list[fd.ParameterDefinition], dims: fd.DimensionSet
    ) -> dict[str, fd.Parameter]:
        parameters = super().read_parameters(parameter_definitions, dims)
        self.parameter_reader.check_start_of_time_horizon()
        return parameters

    def get_dimension_files(self) -> dict[str, str | os.PathLike[str]]:
        dimension_files: dict[str, str | os.PathLike[str]] = {}
        for dimension in self.definition.dimensions:
            if dimension.letter in TIME_LETTERS:
                # The time dimensions have no file, they follow from the configured time horizon
                continue
            elif dimension.name == "Region":
                # Special case for Region: it is read from the parameters folder, not the dimensions folder
                dimension_path = self.parameters_path / "regionmapping.csv"
            else:
                dimension_filename = dimension.name.lower().replace(" ", "_").replace("-", "_")
                dimension_path = self.dimensions_path / f"{dimension_filename}.csv"

            dimension_files[dimension.name] = dimension_path

        self._validate_files("dimension", dimension_files)
        return dimension_files

    def read_input_time_horizon(self) -> TimeHorizon | None:
        """Time horizon of the input data, from the time range file written by mrmfa.

        Returns:
            None if the input data has no time range file, as in archives of older mrmfa versions.

        Raises:
            InputHorizonError: If the time range file lacks one of the time horizon boundaries.
        """
        path = self.parameters_path / f"{prefix_from_module(self.model_class)}_time_range.cs4r"
        if not path.exists():
            return None
        header, skiprows = MadratParameterReader.extract_cs4r_info(path)
        data = pd.read_csv(path, names=header, skiprows=skiprows)
        years = dict(zip(data[header[0]], data[header[-1]].astype(int)))
        boundaries = ("start_historical", "end_historical", "end_future")
        missing = [name for name in boundaries if name not in years]
        if missing:
            raise InputHorizonError(f"Time range file {path} lacks {', '.join(missing)}.")
        return TimeHorizon(**{name: years[name] for name in boundaries})

    def get_parameter_files(self) -> dict[str, str | os.PathLike[str]]:
        model_prefix = prefix_from_module(self.model_class)
        parameter_files: dict[str, str | os.PathLike[str]] = {}
        legacy_files = ()
        for parameter in self.definition.parameters:
            model_specific_file = self.parameters_path / f"{model_prefix}_{parameter.name}.cs4r"
            legacy_file = self.legacy_parameters_path / f"{model_prefix}_{parameter.name}.cs4r"

            if not model_specific_file.exists() and legacy_file.exists():
                legacy_files += (parameter.name,)
                parameter_files[parameter.name] = legacy_file
            else:
                parameter_files[parameter.name] = model_specific_file
        if legacy_files:
            logging.warning(
                f"Parameter files for parameters {legacy_files} not found. Using legacy files instead.",
                stacklevel=2,
            )

        self._validate_files("parameter", parameter_files)
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

    Parameters with a time dimension are fitted to the configured time horizon: years outside of
    their time dimension are dropped, so that input data covering a longer period can be used.
    The data must however reach the end of the time dimension without gaps after the historical
    period, as the reader does not extrapolate.
    Everything else inherited from flodym.CSVParameterReader.

    Args:
        parameter_files: Mapping of parameter names to file paths.
        time_horizon: Configured time horizon.
        input_label: Description of the configured input data, used in error messages.
        allow_missing_values: Whether to allow missing values in the data.
        allow_extra_values: Whether to allow rows with items not present in the dimensions.
    """

    TIME_COLUMN = "Time"
    """Column of the years in .cs4r files, also of parameters on the historical time dimension."""

    def __init__(
        self,
        parameter_files: dict[str, str | os.PathLike[str]],
        time_horizon: TimeHorizon,
        input_label: str | None = None,
        allow_missing_values: bool = False,
        allow_extra_values: bool = False,
    ):
        super().__init__(
            parameter_files,
            allow_missing_values=allow_missing_values,
            allow_extra_values=allow_extra_values,
        )
        self.time_horizon = time_horizon
        self.input_label = input_label
        self.first_years: dict[str, int] = {}
        """First year of the data of each parameter with a time dimension read so far."""

    def read_parameter_values(self, parameter_name: str, dims: fd.DimensionSet) -> fd.Parameter:
        if self.parameter_filenames is None:
            raise ValueError("No parameter files specified.")
        path = self.parameter_filenames[parameter_name]
        header, skiprows = self.extract_cs4r_info(path)
        data = pd.read_csv(path, names=header, skiprows=skiprows)
        time = self.time_dimension(dims)
        if time is not None:
            data = self.fit_to_time_dimension(parameter_name, data, time)
        return fd.Parameter.from_df(
            dims=dims,
            name=parameter_name,
            df=data,
            allow_missing_values=self.allow_missing_values,
            allow_extra_values=self.allow_extra_values,
        )

    def time_dimension(self, dims: fd.DimensionSet) -> fd.Dimension | None:
        """Time dimension among the given dimensions, if any."""
        letters = [letter for letter in TIME_LETTERS if letter in dims.letters]
        return dims[letters[0]] if letters else None

    def fit_to_time_dimension(
        self, parameter_name: str, data: pd.DataFrame, time: fd.Dimension
    ) -> pd.DataFrame:
        """Check that the data reaches the end of its time dimension and drop the years outside.

        Args:
            parameter_name: Name of the parameter, used in error messages.
            data: Parameter data in long format, with one column per dimension.
            time: Time dimension of the parameter.

        Returns:
            The data of the years of the time dimension, with the year column named after it.

        Raises:
            InputHorizonError: If the data misses a year between the last historical year and the
                end of the time dimension.
        """
        year_column = next(
            (c for c in data.columns if c in (time.name, time.letter, self.TIME_COLUMN)), None
        )
        if year_column is None:
            # nothing to fit, flodym reports the missing dimension column
            return data
        data = data.rename(columns={year_column: time.name})
        years = data[time.name]
        required_years = {year for year in time.items if year >= self.time_horizon.end_historical}
        missing_years = sorted(required_years - set(years))
        if missing_years:
            raise InputHorizonError(
                self._end_error_message(parameter_name, int(years.max()), time, missing_years)
            )
        data = data[years.isin(time.items)]
        self.first_years[parameter_name] = int(data[time.name].min())
        return data

    def check_start_of_time_horizon(self):
        """Check that the input data read so far starts with the historical period.

        Single parameters may start later, but not all of them: the model would take the years
        without any data as years of zero production, population etc.

        Raises:
            InputHorizonError: If no parameter has data for the first year of the time horizon.
        """
        if not self.first_years:
            return
        first_year = min(self.first_years.values())
        if first_year > self.time_horizon.start_historical:
            raise InputHorizonError(
                "The historical period starts in model_switches.start_historical = "
                f"{self.time_horizon.start_historical}, but no input parameter has data before "
                f"{first_year}. Raise model_switches.start_historical to {first_year}, or use "
                f"input data that starts earlier{self._current_input}."
            )

    @property
    def _current_input(self) -> str:
        return f" (currently {self.input_label})" if self.input_label else ""

    def _end_error_message(
        self, parameter_name: str, last_year: int, time: fd.Dimension, missing_years: list[int]
    ) -> str:
        end_year = time.items[-1]
        if time.letter == HISTORICAL_TIME_LETTER:
            switch = "model_switches.end_historical"
            expectation = (
                f"the historical period ends in {switch} = {end_year}. The future is modelled "
                "from the last historical year on, so historical inputs must reach it"
            )
            remedy = "Use input data with a longer historical period"
        else:
            switch = "model_switches.end_future"
            expectation = (
                f"the model runs until {switch} = {end_year}. Inputs on the time dimension must "
                "cover the future, remind-mfa does not extrapolate them"
            )
            remedy = (
                f"Build the input archive with mrmfa fullMFA(end_future = {end_year}) and select "
                "it via input.input_data_revision"
            )
        if last_year < end_year:
            problem = f"ends in {last_year}"
            alternative = f", or lower {switch} to {last_year}"
        else:
            shown = ", ".join(str(year) for year in missing_years[:10])
            more = f" and {len(missing_years) - 10} more" if len(missing_years) > 10 else ""
            problem = f"misses the years {shown}{more}"
            alternative = ""
        return (
            f"Input parameter '{parameter_name}' {problem}, but {expectation}. "
            f"{remedy}{self._current_input}{alternative}. "
            f"File: {self.parameter_filenames[parameter_name]}"
        )

    @staticmethod
    def extract_cs4r_info(filepath: str | PathLike[str]) -> tuple[list[str], int]:
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
