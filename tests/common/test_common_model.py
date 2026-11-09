"""Tests for the selection of the driver scenario in `CommonModel`."""

import flodym as fd
import numpy as np
import pytest

from remind_mfa.common.common_config import CommonCfg, ModelSwitches
from remind_mfa.common.common_model import CommonModel
from remind_mfa.common.helpers import ModelNames

R = fd.Dimension(name="Region", letter="r", items=["A", "B"])
S = fd.Dimension(name="Driver Scenario", letter="S", items=["SSP1", "SSP2", "SSP3"])
DIMS = fd.DimensionSet(dim_list=[R, S])


def make_model(driver_scen: str | None, population: list[list[float]]) -> CommonModel:
    """Model with only the attributes needed to select the driver scenario."""
    model = CommonModel.__new__(CommonModel)
    model.cfg = CommonCfg.model_construct(
        model=ModelNames.STEEL,
        model_switches=ModelSwitches.model_construct(scenario="SSP2_variant"),
    )
    model.dims = DIMS
    model.parameters = {
        "population": fd.Parameter(dims=DIMS, values=np.array(population)),
        "lifetime": fd.Parameter(dims=DIMS[("r",)], values=np.array([20.0, 30.0])),
    }
    model.scenario_parameters = {"driver_scen": driver_scen}
    return model


def test_select_driver_scen_slices_parameters_with_driver_dimension():
    model = make_model("SSP2", population=[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    model.select_driver_scen()

    assert model.parameters["population"].dims.letters == ("r",)
    assert model.parameters["population"].values.tolist() == [2.0, 5.0]
    assert model.parameters["lifetime"].values.tolist() == [20.0, 30.0]


def test_select_driver_scen_fails_for_missing_driver_scenario():
    model = make_model("SSP2IndiaHigh", population=[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    with pytest.raises(ValueError, match=r"Driver scenario 'SSP2IndiaHigh'.*not available"):
        model.select_driver_scen()


def test_select_driver_scen_fails_without_input_values():
    # missing input values are read as zero
    model = make_model("SSP3", population=[[1.0, 2.0, 0.0], [4.0, 5.0, 0.0]])

    with pytest.raises(ValueError, match=r"no values of parameter 'population'.*'SSP3'"):
        model.select_driver_scen()


def test_select_driver_scen_fails_without_driver_scenario():
    model = make_model(None, population=[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    with pytest.raises(ValueError, match="sets no 'driver_scen'"):
        model.select_driver_scen()
