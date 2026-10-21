"""Tests for the hibernating stock shared by steel and cement."""

import numpy as np
import flodym as fd

from remind_mfa.common.common_mfa_system import CommonMFASystem

T = fd.Dimension(name="Time", letter="t", items=[2030, 2031, 2032])
U = fd.Dimension(name="End Use", letter="u", items=["Construction", "Products"])
DIMS = fd.DimensionSet(dim_list=[T, U])


def make_system(hibernation_share: fd.Parameter) -> CommonMFASystem:
    processes = fd.make_processes(["sysenv", "use", "hibernating"])
    flows = fd.make_empty_flows(
        processes=processes,
        flow_definitions=[
            fd.FlowDefinition(from_process="use", to_process="hibernating", dim_letters=("t", "u"))
        ],
        dims=DIMS,
    )
    stocks = fd.make_empty_stocks(
        processes=processes,
        stock_definitions=[
            fd.StockDefinition(
                name="hibernating",
                process="hibernating",
                dim_letters=("t", "u"),
                subclass=fd.SimpleFlowDrivenStock,
            )
        ],
        dims=DIMS,
    )
    return CommonMFASystem.model_construct(
        dims=DIMS,
        parameters={"hibernation_share": hibernation_share},
        processes=processes,
        flows=flows,
        stocks=stocks,
    )


def test_compute_hibernating_stock_splits_outflow_and_accumulates_stock():
    hibernation_share = fd.Parameter(dims=DIMS["u",], values=np.array([0.3, 0.0]))
    mfa = make_system(hibernation_share)
    outflow = fd.FlodymArray(dims=DIMS, values=np.array([[10.0, 4.0], [20.0, 4.0], [10.0, 4.0]]))

    remaining = mfa.compute_hibernating_stock(outflow)

    # values are written into the existing flow, which must stay a Flow for the mass balance
    assert isinstance(mfa.flows["use => hibernating"], fd.Flow)
    np.testing.assert_allclose(
        mfa.flows["use => hibernating"].values, [[3.0, 0.0], [6.0, 0.0], [3.0, 0.0]]
    )
    np.testing.assert_allclose(remaining.values, [[7.0, 4.0], [14.0, 4.0], [7.0, 4.0]])
    # no outflow: the stock is the cumulative inflow
    np.testing.assert_allclose(
        mfa.stocks["hibernating"].stock.values, [[3.0, 0.0], [9.0, 0.0], [12.0, 0.0]]
    )
