import csv
import logging
from pathlib import Path

import flodym as fd
import numpy as np
import pytest

from remind_mfa.cement.cement_bottom_up_definition import bottom_up_scenario_parameters
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.common_definition import scenario_parameters as common_scn_prm_def
from remind_mfa.common.helpers import ModelNames, get_model_class
from remind_mfa.common.region_aggregation import RegionAggregations
from remind_mfa.common.scenarios import ExtrapolationScenarioParameter, ScenarioReader

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


# --- Scenario files in config/scenarios ---

REPO_PATH = Path(__file__).parents[2]
SCENARIOS_PATH = REPO_PATH / "config" / "scenarios"
H12_REGIONS = ["CAZ", "CHA", "EUR", "IND", "JPN", "LAM", "MEA", "NEU", "OAS", "REF", "SSA", "USA"]
EU21_REGIONS_ALL = [
    *["CAZ", "CHA", "DEU", "ECE", "ECS", "ENC", "ESC", "ESW", "EWN", "FRA", "IND"],
    *["JPN", "LAM", "MEA", "NEN", "NES", "OAS", "REF", "SSA", "UKI", "USA"],
]
# names of the dimensions that scenario parameters use besides Region
SCENARIO_DIMENSION_NAMES = {"u": "End Use", "m": "Construction Material"}
SSP2_VARIANTS = ["SSP2_lowEn", "SSP2_highDemDEU", "SSP2IndiaHigh", "SSP2IndiaMedium"]
# regions with an own row in mrindustry's specific_material_alpha.csv, besides the default row
LOW_EN_REGIONS = {
    ModelNames.STEEL: {"CHA", "SSA", "LAM", "IND"},
    ModelNames.CEMENT: {"CHA", "SSA"},
    ModelNames.PLASTICS: {"CHA", "SSA", "IND", "OAS"},
}


def config_scenario_names() -> list[str]:
    """Scenarios of config/scenarios/inheritance.csv, except the base scenario that is not run."""
    with open(SCENARIOS_PATH / "inheritance.csv", newline="", encoding="utf-8") as f:
        return [row["scenario"] for row in csv.DictReader(f) if row["scenario"] != "BASE"]


def read_config_scenario(name: str, model: ModelNames, regions: list[str]) -> dict:
    """Read a scenario of config/scenarios with the scenario parameters of the model.

    Dimensions other than Region are read from data_in/dimensions/<model>/.
    """
    definitions = common_scn_prm_def + get_model_class(model).custom_scn_prm_def
    inactive = set()
    if model == ModelNames.CEMENT:
        # the bottom-up module is inactive by default
        inactive = {definition.name for definition in bottom_up_scenario_parameters}
    letters = {
        letter
        for definition in definitions
        for letter in getattr(definition, "dim_letters", ())
        if letter != "r"
    }
    dim_list = [fd.Dimension(name="Region", letter="r", items=regions)]
    for letter in sorted(letters):
        dim_name = SCENARIO_DIMENSION_NAMES[letter]
        path = (
            REPO_PATH
            / "data_in"
            / "dimensions"
            / model.value
            / f"{dim_name.lower().replace(' ', '_')}.csv"
        )
        items = path.read_text(encoding="utf-8").split()
        dim_list.append(fd.Dimension(name=dim_name, letter=letter, items=items))
    reader = ScenarioReader(
        name=name,
        base_path=str(SCENARIOS_PATH),
        model=model,
        dims=fd.DimensionSet(dim_list=dim_list),
        parameter_definitions=definitions,
        inactive_parameters=inactive,
    )
    return reader.get_parameters()


def comparable_values(parameter) -> object:
    """Values of a scenario parameter in a form that can be compared with ==."""
    if isinstance(parameter, ExtrapolationScenarioParameter):
        extras = {name: extra.values.tolist() for name, extra in parameter.extras.items()}
        return parameter.value.values.tolist(), extras
    if isinstance(parameter, fd.Parameter):
        return parameter.values.tolist()
    return parameter


def differing_parameters(parameters: dict, reference: dict) -> set[str]:
    """Names of the scenario parameters whose values differ from the reference."""
    return {
        name
        for name in parameters
        if comparable_values(parameters[name]) != comparable_values(reference[name])
    }


@pytest.mark.parametrize("regions", [H12_REGIONS, EU21_REGIONS_ALL], ids=["h12", "eu21"])
@pytest.mark.parametrize("model", list(ModelNames))
@pytest.mark.parametrize("name", config_scenario_names())
def test_config_scenarios_are_readable(name, model, regions):
    parameters = read_config_scenario(name, model, regions)
    assert parameters["driver_scen"] is not None


@pytest.mark.parametrize("model", list(ModelNames))
@pytest.mark.parametrize("name", SSP2_VARIANTS)
def test_ssp2_variants_inherit_from_ssp2(name, model):
    with open(SCENARIOS_PATH / "inheritance.csv", newline="", encoding="utf-8") as f:
        parents = {row["scenario"]: row["parent"] for row in csv.DictReader(f)}
    assert parents[name] == "SSP2"

    parameters = read_config_scenario(name, model, H12_REGIONS)
    reference = read_config_scenario("SSP2", model, H12_REGIONS)
    expected_differences = {
        "SSP2_lowEn": {"inflow_factor"},
        "SSP2_highDemDEU": set(),
        "SSP2IndiaHigh": {"driver_scen"},
        "SSP2IndiaMedium": {"driver_scen"},
    }[name]
    assert differing_parameters(parameters, reference) == expected_differences
    if "driver_scen" in expected_differences:
        assert parameters["driver_scen"] == name


@pytest.mark.parametrize("regions", [H12_REGIONS, EU21_REGIONS_ALL], ids=["h12", "eu21"])
@pytest.mark.parametrize("model", list(ModelNames))
def test_low_energy_demand_lowers_inflow_in_all_regions(model, regions):
    inflow_factor = read_config_scenario("SSP2_lowEn", model, regions)["inflow_factor"]
    years = inflow_factor.extras["year"].values

    assert np.all((inflow_factor.value.values > 0) & (inflow_factor.value.values < 1))
    assert np.all(years == years[0]) and years[0] > 2025


@pytest.mark.parametrize("model", list(ModelNames))
def test_low_energy_demand_has_rows_for_the_regions_of_mrindustry(model):
    reader = ScenarioReader(
        name="SSP2_lowEn",
        base_path=str(SCENARIOS_PATH),
        model=model,
        dims=fd.DimensionSet(dim_list=[]),
        parameter_definitions=[],
    )
    scenario = reader.read_single("SSP2_lowEn")
    scenario.filter_data_by_model(model)
    rows = [point for point in scenario.data if point.parameter == "inflow_factor"]

    # one default row for all regions, followed by one row per region of the alpha table
    assert rows[0].index == {}
    regions = [point.index["Region"] for point in rows[1:]]
    assert len(regions) == len(set(regions))
    assert set(regions) == LOW_EN_REGIONS[model]
