"""Tests for reading the region mapping and .cs4r parameter files."""

from pathlib import Path

import flodym as fd
import numpy as np
import pytest

from remind_mfa.common.common_data_reader import CommonDimensionReader, MadratParameterReader

T = fd.Dimension(name="Time", letter="t", items=[2020, 2021])
R = fd.Dimension(name="Region", letter="r", items=["A", "B"])
DIMS = fd.DimensionSet(dim_list=[T, R])

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
    reader = MadratParameterReader(write_cs4r(tmp_path, CS4R_CONTENT))

    parameter = reader.read_parameter_values(PARAMETER_NAME, dims=DIMS)

    np.testing.assert_allclose(np.asarray(parameter.values, dtype=float), [[1.5, 2.5], [3.5, 4.5]])


def test_cs4r_without_dimension_header_is_rejected(tmp_path: Path):
    content = CS4R_CONTENT.replace("* note: dimensions: (Time,Region,value)\n", "")
    reader = MadratParameterReader(write_cs4r(tmp_path, content))

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
