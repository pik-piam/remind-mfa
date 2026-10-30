import logging

import flodym as fd
import pytest

from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.helpers import ModelNames
from remind_mfa.common.region_aggregation import RegionAggregations
from remind_mfa.common.scenarios import ScenarioReader

# (iso249, eu21, h12) rows of the region mapping test files
REGION_MAPPING = [
    ("DEU", "DEU", "EUR"),
    ("FRA", "FRA", "EUR"),
    ("ITA", "ECS", "EUR"),
    ("NOR", "NEN", "NEU"),
    ("CHN", "CHA", "CHA"),
    ("USA", "USA", "USA"),
]
EU21_REGIONS = ["CHA", "DEU", "FRA", "NEN"]


@pytest.mark.parametrize(
    "value, expected",
    [
        (
            "{year: 2030, type: target}",
            {"year": 2030, "type": "target"},
        ),
        (
            "{Region: [IND, LAM, OAS, SSA], Stock Type: Res, Function: RS}",
            {"Region": ["IND", "LAM", "OAS", "SSA"], "Stock Type": "Res", "Function": "RS"},
        ),
        (
            "{Region: SSA, Function: [RS, RM, Com], Structure: M}",
            {"Region": "SSA", "Function": ["RS", "RM", "Com"], "Structure": "M"},
        ),
    ],
)
def test_parse_dict_column_uses_yaml(value, expected):
    assert ScenarioReader._parse_dict_column(value) == expected


def test_parse_dict_column_rejects_non_mappings():
    with pytest.raises(ValueError, match="Could not parse YAML dict column"):
        ScenarioReader._parse_dict_column("{[1, 2, 3]}")


@pytest.fixture
def mappings_path(tmp_path):
    path = tmp_path / "regional"
    path.mkdir()
    eu21 = [f"Name;{iso};{eu21};rest" for iso, eu21, _ in REGION_MAPPING]
    h12 = [f"{i};Name;{iso};{h12}" for i, (iso, _, h12) in enumerate(REGION_MAPPING)]
    (path / "regionmapping_21_EU11.csv").write_text(
        "\n".join(["X;CountryCode;RegionCode;missingH12", *eu21]) + "\n", encoding="utf-8"
    )
    (path / "regionmappingH12.csv").write_text(
        "\n".join(["X;CountryCode;RegionCode", *h12]) + "\n", encoding="utf-8"
    )
    return path


@pytest.mark.parametrize(
    "regions, region, expected",
    [
        (EU21_REGIONS, "EUR", ["DEU", "FRA"]),
        (EU21_REGIONS, "NEU", ["NEN"]),
        (EU21_REGIONS, "USA", None),
        (EU21_REGIONS, "XYZ", None),
        (["DEU", "FRA", "ITA", "NOR"], "EUR", ["DEU", "FRA", "ITA"]),
        (["DEU", "FRA", "ITA", "NOR"], "ECS", ["ITA"]),
        (["EUR", "NEU", "CHA"], "DEU", None),
    ],
)
def test_region_aggregation_members(mappings_path, regions, region, expected):
    assert RegionAggregations(mappings_path, regions).members(region) == expected


def test_region_aggregation_reads_files_only_when_needed(tmp_path):
    aggregations = RegionAggregations(tmp_path / "missing", EU21_REGIONS)
    with pytest.raises(FileNotFoundError, match="piam_mappings"):
        aggregations.members("EUR")


def test_scenario_reader_resolves_aggregate_regions(mappings_path, tmp_path, caplog):
    scenarios_path = tmp_path / "scenarios"
    scenarios_path.mkdir()
    (scenarios_path / "inheritance.csv").write_text("scenario,parent,\nBASE,\n", encoding="utf-8")
    (scenarios_path / "BASE.csv").write_text(
        "parameter,models,value,extra,index,description\n"
        "share,all,1.0,,,\n"
        "share,all,2.0,,{Region: EUR},\n"
        'share,all,3.0,,"{Region: [CHA, XYZ]}",\n',
        encoding="utf-8",
    )
    dims = fd.DimensionSet(dim_list=[fd.Dimension(name="Region", letter="r", items=EU21_REGIONS)])
    reader = ScenarioReader(
        name="BASE",
        base_path=str(scenarios_path),
        model=ModelNames.STEEL,
        dims=dims,
        parameter_definitions=[RemindMFAParameterDefinition(name="share", dim_letters=("r",))],
        region_mappings_path=str(mappings_path),
    )
    with caplog.at_level(logging.INFO):
        parameters = reader.get_parameters()
    assert parameters["share"].values.tolist() == [3.0, 2.0, 2.0, 1.0]
    assert "aggregate region 'EUR'" in caplog.text
    assert any(r.levelno == logging.WARNING and "'XYZ'" in r.message for r in caplog.records)


def test_scenario_reader_skips_inactive_parameters(tmp_path):
    scenarios_path = tmp_path / "scenarios"
    scenarios_path.mkdir()
    (scenarios_path / "inheritance.csv").write_text("scenario,parent,\nBASE,\n", encoding="utf-8")
    (scenarios_path / "BASE.csv").write_text(
        "parameter,models,value,extra,index,description\n"
        "share,all,1.0,,,\n"
        "module_share,all,2.0,,{Structure: Timber},\n",
        encoding="utf-8",
    )
    dims = fd.DimensionSet(dim_list=[fd.Dimension(name="Region", letter="r", items=EU21_REGIONS)])

    def make_reader(inactive_parameters: set[str]) -> ScenarioReader:
        return ScenarioReader(
            name="BASE",
            base_path=str(scenarios_path),
            model=ModelNames.CEMENT,
            dims=dims,
            parameter_definitions=[RemindMFAParameterDefinition(name="share", dim_letters=("r",))],
            inactive_parameters=inactive_parameters,
        )

    parameters = make_reader({"module_share"}).get_parameters()
    assert parameters["share"].values.tolist() == [1.0] * len(EU21_REGIONS)
    assert "module_share" not in parameters

    with pytest.raises(ValueError, match="undefined scenario parameter 'module_share'"):
        make_reader(set()).get_parameters()
