"""Tests for the time horizon, given by the input data and shortened by `model_switches`."""

import tarfile
from pathlib import Path

import flodym as fd
import numpy as np
import pytest

from remind_mfa.common.common_config import IamcExportCfg, TimeHorizon
from remind_mfa.common.common_data_reader import CommonDataReader, InputHorizonError
from remind_mfa.common.common_definition import (
    RemindMFADefinition,
    RemindMFAParameterDefinition,
)
from remind_mfa.common.config_loader import CONFIG_DIR, load_config
from remind_mfa.common.helpers import ModelNames, get_model_class

ARCHIVE_START = 2000
ARCHIVE_END_HISTORICAL = 2022
REGIONS = ["EUR", "USA"]

DEFINITION = RemindMFADefinition(
    dimensions=[
        fd.DimensionDefinition(name="Time", letter="t", dtype=int),
        fd.DimensionDefinition(name="Historical Time", letter="h", dtype=int),
        fd.DimensionDefinition(name="Region", letter="r", dtype=str),
    ],
    processes=[],
    flows=[],
    stocks=[],
    parameters=[
        RemindMFAParameterDefinition(name="population", dim_letters=("t", "r")),
        RemindMFAParameterDefinition(name="steel_production", dim_letters=("h", "r")),
    ],
)


def cs4r(header: str, years: range) -> str:
    """Content of a parameter file on (time, Region), with a thousand times the year as value.

    The values differ from the years, so that flodym does not take the value column for time.
    """
    rows = [f"{year},{region},{year * 1000.0}" for year in years for region in REGIONS]
    return f"* description: synthetic\n* note: dimensions: ({header},value)\n" + "\n".join(rows)


def write_archive(madrat_output: Path, end_future: int, with_time_range: bool = True) -> None:
    """Write a minimal input archive, as built by mrmfa `fullMFA(end_future = end_future)`.

    Without time range file, it is an archive of an mrmfa version that did not write it yet.
    """
    content = madrat_output / f"content_{end_future}"
    content.mkdir(parents=True)
    if with_time_range:
        (content / "st_time_range.cs4r").write_text(
            "* description: synthetic\n* unit: year\n* note: dimensions: (scalar,value)\n"
            f"start_historical,{ARCHIVE_START}\nend_historical,{ARCHIVE_END_HISTORICAL}\n"
            f"end_future,{end_future}\n"
        )
    (content / "regionmapping.csv").write_text(
        "X;CountryCode;RegionCode\nGermany;DEU;EUR\nUnited States;USA;USA\n"
    )
    population = cs4r("Time,Region", range(ARCHIVE_START, end_future + 1))
    (content / "st_population.cs4r").write_text(population)
    production = cs4r("Historical Time,Region", range(ARCHIVE_START, ARCHIVE_END_HISTORICAL + 1))
    (content / "st_steel_production.cs4r").write_text(production)
    archive = madrat_output / f"rev0.1-to{end_future}_test_abcdef12_mfa.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in content.iterdir():
            tar.add(path, arcname=path.name)


def make_data_reader(
    tmp_path: Path,
    archive_end: int,
    end_future: int | None,
    start_historical: int | None = None,
    end_historical: int | None = None,
    with_time_range: bool = True,
) -> CommonDataReader:
    """Data reader of a steel model with the given time switches on a synthetic input archive."""
    madrat_output = tmp_path / "madrat_output"
    write_archive(madrat_output, archive_end, with_time_range)

    config = load_config([CONFIG_DIR / "default.toml"], ModelNames.STEEL)
    config["input"] |= {
        "input_data_path": str(tmp_path / "data_in"),
        "madrat_output_path": str(madrat_output),
        "input_data_revision": f"0.1-to{archive_end}",
        "region_mapping": "test",
    }
    config["model_switches"] |= {
        "start_historical": start_historical,
        "end_historical": end_historical,
        "end_future": end_future,
    }
    cfg = get_model_class(ModelNames.STEEL).ConfigCls(**config)
    return CommonDataReader(cfg=cfg, definition=DEFINITION, allow_missing_values=True)


def read(reader: CommonDataReader) -> tuple[fd.DimensionSet, dict[str, fd.Parameter]]:
    dims = reader.read_dimensions(DEFINITION.dimensions)
    return dims, reader.read_parameters(DEFINITION.parameters, dims=dims)


@pytest.mark.parametrize(("archive_end", "end_future"), [(2100, 2100), (2150, 2100), (2150, 2150)])
def test_inputs_are_read_until_the_configured_end_future(
    tmp_path: Path, archive_end: int, end_future: int
):
    dims, parameters = read(make_data_reader(tmp_path, archive_end, end_future))

    assert dims["t"].items == list(range(ARCHIVE_START, end_future + 1))
    assert dims["h"].items == list(range(ARCHIVE_START, ARCHIVE_END_HISTORICAL + 1))
    assert all(type(year) is int for year in dims["t"].items + dims["h"].items)
    population = parameters["population"]
    np.testing.assert_allclose(population[{"r": "EUR"}].values, 1000.0 * np.array(dims["t"].items))


def test_time_horizon_defaults_to_the_one_of_the_input_data(tmp_path: Path):
    dims, _ = read(make_data_reader(tmp_path, archive_end=2150, end_future=None))

    assert dims["h"].items == list(range(ARCHIVE_START, ARCHIVE_END_HISTORICAL + 1))
    assert dims["t"].items == list(range(ARCHIVE_START, 2151))


@pytest.mark.parametrize(
    ("switch", "year", "expected_error"),
    [
        ("start_historical", 1990, "start_historical = 1990 is before 2000"),
        ("end_historical", 2030, "end_historical = 2030 is after 2022"),
        ("end_future", 2200, "end_future = 2200 is after 2150"),
    ],
)
def test_switches_extending_the_time_horizon_of_the_input_data_are_rejected(
    tmp_path: Path, switch: str, year: int, expected_error: str
):
    switches: dict[str, int | None] = {"end_future": None} | {switch: year}

    with pytest.raises(InputHorizonError, match=expected_error):
        make_data_reader(tmp_path, archive_end=2150, **switches)


def test_input_without_time_range_needs_all_time_switches(tmp_path: Path):
    with pytest.raises(InputHorizonError, match="start_historical, end_historical must be set"):
        make_data_reader(tmp_path, archive_end=2100, end_future=2100, with_time_range=False)


def test_input_ending_before_end_future_fails_before_any_computation(tmp_path: Path):
    reader = make_data_reader(
        tmp_path,
        archive_end=2100,
        end_future=2150,
        start_historical=ARCHIVE_START,
        end_historical=ARCHIVE_END_HISTORICAL,
        with_time_range=False,
    )

    with pytest.raises(InputHorizonError) as error:
        read(reader)

    message = str(error.value)
    assert "'population' ends in 2100" in message
    assert "model_switches.end_future = 2150" in message
    assert "fullMFA(end_future = 2150)" in message
    assert "revision 0.1-to2100, region mapping test" in message


def test_historical_period_can_be_shorter_than_the_input_data(tmp_path: Path):
    reader = make_data_reader(
        tmp_path, archive_end=2100, end_future=2100, start_historical=2005, end_historical=2015
    )

    dims, parameters = read(reader)

    assert dims["h"].items == list(range(2005, 2016))
    assert dims["t"].items == list(range(2005, 2101))
    production = parameters["steel_production"]
    np.testing.assert_allclose(production[{"r": "EUR"}].values, 1000.0 * np.arange(2005, 2016))


def test_historical_period_ending_after_the_input_data_fails(tmp_path: Path):
    reader = make_data_reader(
        tmp_path,
        archive_end=2100,
        end_future=2100,
        start_historical=ARCHIVE_START,
        end_historical=2030,
        with_time_range=False,
    )

    with pytest.raises(InputHorizonError) as error:
        read(reader)

    message = str(error.value)
    assert "'steel_production' ends in 2022" in message
    assert "model_switches.end_historical = 2030" in message


def test_historical_period_starting_before_the_input_data_fails(tmp_path: Path):
    reader = make_data_reader(
        tmp_path,
        archive_end=2100,
        end_future=2100,
        start_historical=1990,
        end_historical=ARCHIVE_END_HISTORICAL,
        with_time_range=False,
    )

    with pytest.raises(InputHorizonError) as error:
        read(reader)

    message = str(error.value)
    assert "model_switches.start_historical = 1990" in message
    assert "no input parameter has data before 2000" in message


@pytest.mark.parametrize("model", list(ModelNames))
@pytest.mark.parametrize(
    ("configs", "end_future"), [(["default"], 2100), (["default", "mrindustry"], 2150)]
)
def test_time_horizon_of_shipped_configs(model: ModelNames, configs: list[str], end_future: int):
    config = load_config(configs, model)
    input_horizon = TimeHorizon(start_historical=1900, end_historical=2022, end_future=2150)

    model_switches = get_model_class(model).ConfigCls(**config).model_switches
    time_horizon = model_switches.resolve_time_horizon(input_horizon)

    assert time_horizon == TimeHorizon(1900, 2022, end_future)


@pytest.mark.parametrize(
    ("start_historical", "end_historical", "end_future"),
    [(1900, 2022, 2020), (None, 2022, 2022), (2100, None, 2100), (2030, 2022, None)],
)
def test_unordered_time_switches_are_rejected(
    start_historical: int | None, end_historical: int | None, end_future: int | None
):
    config = load_config(["default"], ModelNames.STEEL)
    config["model_switches"] |= {
        "start_historical": start_historical,
        "end_historical": end_historical,
        "end_future": end_future,
    }
    model_switches = get_model_class(ModelNames.STEEL).ConfigCls(**config).model_switches
    input_horizon = TimeHorizon(start_historical=1900, end_historical=2022, end_future=2150)

    with pytest.raises(ValueError, match="start_historical < end_historical < end_future"):
        model_switches.resolve_time_horizon(input_horizon)


@pytest.mark.parametrize(
    ("end_year", "end_future", "expected"),
    [
        (None, 2100, range(1950, 2101)),
        (None, 2150, range(1950, 2151)),
        (2100, 2150, range(1950, 2101)),
    ],
)
def test_iamc_export_years_follow_end_future_without_end_year(
    end_year: int | None, end_future: int, expected: range
):
    years = IamcExportCfg(start_year=1950, end_year=end_year).years(end_future)

    assert years == expected


def test_iamc_export_years_beyond_end_future_are_rejected():
    with pytest.raises(ValueError, match="after the last model year 2100"):
        IamcExportCfg(start_year=1950, end_year=2150).years(end_future=2100)


def test_iamc_export_start_year_after_end_year_is_rejected():
    with pytest.raises(ValueError, match="start_year 2100 is after end_year 2050"):
        IamcExportCfg(start_year=2100, end_year=2050)
