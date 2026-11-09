import pytest

from remind_mfa.common.common_config import ModelSwitches


def make_switches(scenarios: list[str]) -> ModelSwitches:
    return ModelSwitches(
        scenarios=scenarios,
        stock_extrapolation_class_name="LogisticExtrapolation",
        lifetime_model_name="LogNormalLifetime",
    )


def test_single_selected_scenario_is_the_run_scenario():
    assert make_switches(["SSP1"]).scenario == "SSP1"


def test_several_selected_scenarios_have_no_run_scenario():
    with pytest.raises(ValueError, match="exactly one scenario"):
        make_switches(["SSP1", "SSP2"]).scenario


def test_scenarios_must_not_be_empty():
    with pytest.raises(ValueError, match="scenarios"):
        make_switches([])
