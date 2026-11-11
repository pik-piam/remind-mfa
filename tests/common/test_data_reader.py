"""Tests for reading the region mapping and .cs4r parameter files."""

from collections.abc import Iterable
from pathlib import Path

import flodym as fd
import numpy as np
import pytest

from remind_mfa.common.common_config import TimeHorizon
from remind_mfa.common.common_data_reader import (
    CommonDimensionReader,
    InputHorizonError,
    MadratParameterReader,
)

T = fd.Dimension(name="Time", letter="t", items=[2020, 2021])
R = fd.Dimension(name="Region", letter="r", items=["A", "B"])
DIMS = fd.DimensionSet(dim_list=[T, R])
HORIZON = TimeHorizon(start_historical=2019, end_historical=2020, end_future=2021)

CS4R_CONTENT = """* description: Test data
* unit: Tonnes
* note: dimensions: (Time,Region,value)
2020,A,1.5
2020,B,2.5
2021,A,3.5
2021,B,4.5
"""
PARAMETER_NAME = "steel_test_data"


def write_cs4r(tmp_path: Path, content: str):
    path = tmp_path / "st_test_data.cs4r"
    path.write_text(content, encoding="utf-8")
    return {PARAMETER_NAME: str(path)}


def test_data_trade_parameter_is_read_from_cs4r(tmp_path: Path):
    reader = MadratParameterReader(write_cs4r(tmp_path, CS4R_CONTENT), HORIZON)

    parameter = reader.read_parameter_values(PARAMETER_NAME, dims=DIMS)

    np.testing.assert_allclose(np.asarray(parameter.values, dtype=float), [[1.5, 2.5], [3.5, 4.5]])


def test_cs4r_without_dimension_header_is_rejected(tmp_path: Path):
    content = CS4R_CONTENT.replace("* note: dimensions: (Time,Region,value)\n", "")
    reader = MadratParameterReader(write_cs4r(tmp_path, content), HORIZON)

    with pytest.raises(ValueError, match="No header line found"):
        reader.read_parameter_values(PARAMETER_NAME, dims=DIMS)


REGIONMAPPING_CONTENT = """X;CountryCode;RegionCode
Germany;DEU;EUR
China;CHN;CHA
France;FRA;EUR
United States;USA;USA
Hong Kong;HKG;CHA
"""


def test_region_items_are_plain_strings_in_order_of_first_appearance(tmp_path: Path):
    path = tmp_path / "regionmapping.csv"
    path.write_text(REGIONMAPPING_CONTENT, encoding="utf-8")
    reader = CommonDimensionReader({"Region": str(path)})

    region = reader.read_dimension(fd.DimensionDefinition(name="Region", letter="r", dtype=str))

    assert region.items == ["EUR", "CHA", "USA"]
    assert all(type(item) is str for item in region.items)


@pytest.mark.parametrize(
    ("start_historical", "end_historical", "end_future"),
    [(2022, 2022, 2100), (1900, 2100, 2100), (1900, 2022, 2000), (2030, 2022, 2100)],
)
def test_time_horizon_must_be_ordered(start_historical: int, end_historical: int, end_future: int):
    with pytest.raises(ValueError, match="start_historical < end_historical < end_future"):
        TimeHorizon(start_historical, end_historical, end_future)


def write_time_cs4r(
    tmp_path: Path, name: str, years: Iterable[int], time_column: str = "Time"
) -> dict[str, str]:
    """Parameter on (time, Region), with a thousand times the year as value.

    The values differ from the years, so that flodym does not take the value column for time.
    """
    lines = ["* description: synthetic", f"* note: dimensions: ({time_column},Region,value)"]
    lines += [f"{year},{region},{year * 1000.0}" for year in years for region in ("A", "B")]
    path = tmp_path / f"st_{name}.cs4r"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {name: str(path)}


def time_dims(horizon: TimeHorizon, letter: str = "t") -> fd.DimensionSet:
    if letter == "t":
        time = fd.Dimension(name="Time", letter="t", items=list(horizon.years))
    else:
        time = fd.Dimension(name="Historical Time", letter="h", items=list(horizon.historical_years))
    return fd.DimensionSet(dim_list=[time, R])


def test_parameter_with_future_years_must_reach_end_future(tmp_path: Path):
    horizon = TimeHorizon(start_historical=2020, end_historical=2022, end_future=2150)
    files = write_time_cs4r(tmp_path, "population", range(2020, 2101))
    reader = MadratParameterReader(files, horizon, input_label="revision 1.0")

    with pytest.raises(InputHorizonError) as error:
        reader.read_parameter_values("population", dims=time_dims(horizon))

    message = str(error.value)
    assert "'population' ends in 2100" in message
    assert "model_switches.end_future = 2150" in message
    assert "fullMFA(end_future = 2150)" in message
    assert "currently revision 1.0" in message
    assert "lower model_switches.end_future to 2100" in message


def test_parameter_with_gaps_in_future_years_is_rejected(tmp_path: Path):
    horizon = TimeHorizon(start_historical=2020, end_historical=2022, end_future=2150)
    years = [*range(2020, 2031), *range(2035, 2151, 5)]
    files = write_time_cs4r(tmp_path, "population", years)
    reader = MadratParameterReader(files, horizon, allow_missing_values=True)

    with pytest.raises(InputHorizonError, match="misses the years 2031, 2032"):
        reader.read_parameter_values("population", dims=time_dims(horizon))


def test_parameter_on_time_without_future_years_is_rejected(tmp_path: Path):
    horizon = TimeHorizon(start_historical=2020, end_historical=2022, end_future=2150)
    files = write_time_cs4r(tmp_path, "population", range(2020, 2023))
    reader = MadratParameterReader(files, horizon, allow_missing_values=True)

    with pytest.raises(InputHorizonError, match="'population' ends in 2022"):
        reader.read_parameter_values("population", dims=time_dims(horizon))


def test_years_outside_of_the_time_dimension_are_dropped(tmp_path: Path):
    horizon = TimeHorizon(start_historical=2020, end_historical=2022, end_future=2100)
    files = write_time_cs4r(tmp_path, "population", range(2000, 2151))
    reader = MadratParameterReader(files, horizon)

    parameter = reader.read_parameter_values("population", dims=time_dims(horizon))

    assert parameter.dims["t"].items == list(range(2020, 2101))
    np.testing.assert_allclose(parameter[{"r": "A"}].values, 1000.0 * np.arange(2020, 2101))


@pytest.mark.parametrize("time_column", ["Time", "Historical Time"])
def test_historical_parameter_is_cut_to_the_historical_period(tmp_path: Path, time_column: str):
    horizon = TimeHorizon(start_historical=2000, end_historical=2015, end_future=2100)
    files = write_time_cs4r(tmp_path, "production", range(1990, 2023), time_column)
    reader = MadratParameterReader(files, horizon)

    parameter = reader.read_parameter_values("production", dims=time_dims(horizon, "h"))

    np.testing.assert_allclose(parameter[{"r": "A"}].values, 1000.0 * np.arange(2000, 2016))


def test_historical_parameter_must_reach_the_last_historical_year(tmp_path: Path):
    horizon = TimeHorizon(start_historical=2000, end_historical=2022, end_future=2100)
    files = write_time_cs4r(tmp_path, "production", range(2000, 2021))
    reader = MadratParameterReader(files, horizon, allow_missing_values=True)

    with pytest.raises(InputHorizonError) as error:
        reader.read_parameter_values("production", dims=time_dims(horizon, "h"))

    message = str(error.value)
    assert "'production' ends in 2020" in message
    assert "model_switches.end_historical = 2022" in message
    assert "lower model_switches.end_historical to 2020" in message


def test_single_parameters_may_start_after_the_historical_period_starts(tmp_path: Path):
    horizon = TimeHorizon(start_historical=2000, end_historical=2022, end_future=2100)
    files = write_time_cs4r(tmp_path, "production", range(2000, 2023))
    files |= write_time_cs4r(tmp_path, "scrap", range(2010, 2023))
    reader = MadratParameterReader(files, horizon, allow_missing_values=True)

    reader.read_parameter_values("production", dims=time_dims(horizon, "h"))
    scrap = reader.read_parameter_values("scrap", dims=time_dims(horizon, "h"))
    reader.check_start_of_time_horizon()

    np.testing.assert_allclose(scrap[{"h": 2009, "r": "A"}].values, 0.0)
    np.testing.assert_allclose(scrap[{"h": 2010, "r": "A"}].values, 2010000.0)


def test_input_data_must_start_with_the_historical_period(tmp_path: Path):
    horizon = TimeHorizon(start_historical=1990, end_historical=2022, end_future=2100)
    files = write_time_cs4r(tmp_path, "production", range(2000, 2023))
    reader = MadratParameterReader(files, horizon, allow_missing_values=True)
    reader.read_parameter_values("production", dims=time_dims(horizon, "h"))

    with pytest.raises(InputHorizonError) as error:
        reader.check_start_of_time_horizon()

    message = str(error.value)
    assert "model_switches.start_historical = 1990" in message
    assert "no input parameter has data before 2000" in message
