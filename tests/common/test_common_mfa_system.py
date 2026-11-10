"""Tests for the adjustment of the in-use stock inflow in `CommonMFASystem`."""

import flodym as fd
import numpy as np

from remind_mfa.common.common_mfa_system import CommonMFASystem

H = fd.Dimension(name="Historical Time", letter="h", items=list(range(2000, 2011)))
T = fd.Dimension(name="Time", letter="t", items=list(range(2000, 2101)))
R = fd.Dimension(name="Region", letter="r", items=["A", "B"])
DIMS = fd.DimensionSet(dim_list=[T, H, R])


def make_system(inflow_factor: fd.Parameter) -> CommonMFASystem:
    """Minimal system with the parameters of the inflow adjustment."""
    n_trend_years = fd.Parameter(dims=DIMS[("r",)], values=np.full(R.len, 5.0))
    approaching_time = fd.Parameter(dims=DIMS[("r",)], values=np.full(R.len, 10.0))
    return CommonMFASystem.model_construct(
        dims=DIMS,
        parameters={
            "inflow_factor": inflow_factor,
            "n_trend_years": n_trend_years,
            "flow_approaching_time": approaching_time,
        },
        processes={},
        flows={},
        stocks={},
    )


def test_adjust_inflow_scales_future_inflow_by_inflow_factor():
    # region A: factor falls from 1 in the last historical year to 0.5 in 2050, B keeps 1
    years = np.array(T.items)
    factor_a = np.interp(years, [H.items[-1], 2050], [1.0, 0.5])
    inflow_factor = fd.Parameter(
        dims=DIMS[("t", "r")], values=np.stack([factor_a, np.ones(T.len)], axis=1)
    )
    inflow = fd.FlodymArray(dims=DIMS[("t", "r")], values=np.full((T.len, R.len), 10.0))

    adjusted = make_system(inflow_factor).adjust_inflow(inflow)

    np.testing.assert_allclose(adjusted[{"t": H}].values, 10.0)
    np.testing.assert_allclose(adjusted["B"].values, 10.0)
    np.testing.assert_allclose(adjusted["A"][2100].values, 5.0, rtol=1e-3)
    # the blend approaches the scaled inflow smoothly, without falling below it
    future_a = adjusted["A"].values[H.len :]
    assert np.all(np.diff(future_a) <= 1e-6)
    assert np.all(future_a >= 5.0 - 1e-6)
