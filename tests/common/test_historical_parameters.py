"""Tests that historical MFA systems get the parameters restricted to historical time."""

import flodym as fd
import numpy as np

from remind_mfa.common.common_model import CommonModel

H = fd.Dimension(name="Historical Time", letter="h", items=[2021, 2022])
T = fd.Dimension(name="Time", letter="t", items=[2021, 2022, 2023])
R = fd.Dimension(name="Region", letter="r", items=["A", "B"])
DIMS = fd.DimensionSet(dim_list=[H, T, R])


def make_model(parameters: dict[str, fd.Parameter]) -> CommonModel:
    """Model with the given dimensions and parameters, without reading any data."""
    model = CommonModel.__new__(CommonModel)
    model.dims = DIMS
    model.parameters = parameters
    return model


def test_parameters_over_time_are_restricted_to_historical_time():
    over_time = fd.Parameter(dims=DIMS["r", "t"], name="over_time")
    over_time.values[...] = np.arange(6).reshape(2, 3)
    regional = fd.Parameter(dims=DIMS["r",], name="regional")
    model = make_model({"over_time": over_time, "regional": regional})

    parameters = model._restrict_parameters_to_historical_time()

    sliced = parameters["over_time"]
    assert isinstance(sliced, fd.Parameter)
    assert sliced.name == "over_time"
    assert sliced.dims.letters == ("r", "h")
    np.testing.assert_array_equal(sliced.values, [[0, 1], [3, 4]])
    assert parameters["regional"] is regional
    # the model keeps its parameters over the full time
    assert model.parameters["over_time"] is over_time
