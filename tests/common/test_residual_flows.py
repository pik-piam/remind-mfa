"""Tests for removing negative round-off errors from residual flows in `CommonMFASystem`."""

import flodym as fd
import numpy as np

from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.common.trade import Trade, TradeSet

R = fd.Dimension(name="Region", letter="r", items=["CHN", "HKG", "LUX"])
DIMS = fd.DimensionSet(dim_list=[R])


def make_system(
    largest_flow: float, dims: fd.DimensionSet = DIMS, trade_set: TradeSet | None = None
) -> CommonMFASystem:
    """Minimal system; its only flow sets the magnitude for the numerical tolerance."""
    processes = fd.make_processes(["sysenv", "market"])
    flows = fd.make_empty_flows(
        processes=processes,
        flow_definitions=[
            fd.FlowDefinition(from_process="sysenv", to_process="market", dim_letters=("r",))
        ],
        dims=dims,
    )
    flows["sysenv => market"][...] = largest_flow
    return CommonMFASystem.model_construct(
        dims=dims,
        parameters={},
        processes=processes,
        flows=flows,
        stocks={},
        trade_set=trade_set,
    )


def test_negative_round_off_of_vanishing_residual_is_removed():
    # HKG has no production: its net imports cover its demand, up to floating-point round-off
    demand = fd.FlodymArray(dims=DIMS, values=np.array([1e9, 0.3, 5.0]))
    net_imports = fd.FlodymArray(dims=DIMS, values=np.array([1e8, 0.1 + 0.2, 1.0]))
    assert (demand - net_imports).values[1] < 0

    production = make_system(largest_flow=1e9)._remove_negative_round_off(demand - net_imports)

    np.testing.assert_array_equal(production.values, [9e8, 0.0, 4.0])


def test_negative_round_off_is_set_to_zero_and_larger_negatives_are_kept():
    residual = fd.FlodymArray(dims=DIMS, values=np.array([3.0, -1e-10, -1.0]))

    result = make_system(largest_flow=1e6)._remove_negative_round_off(residual)

    # tolerance is 100 * eps * 1e6 = 2.2e-8: -1e-10 is round-off, -1 is a real negative value
    np.testing.assert_array_equal(result.values, [3.0, 0.0, -1.0])
    np.testing.assert_array_equal(residual.values, [3.0, -1e-10, -1.0])


def test_trade_adjusted_split_has_no_negative_round_off_where_all_supply_is_exported():
    # LUX exports its whole supply as end uses A and B and imports C, so it manufactures nothing
    # for domestic use; the split would otherwise give A and B a negative round-off inflow
    dims = fd.DimensionSet(
        dim_list=[
            fd.Dimension(name="Region", letter="r", items=["LUX"]),
            fd.Dimension(name="End use", letter="u", items=["A", "B", "C"]),
        ]
    )
    trade = Trade(
        name="manufactured_products",
        imports=fd.FlodymArray(dims=dims, values=np.array([[0.0, 0.0, 3.0]])),
        exports=fd.FlodymArray(dims=dims, values=np.array([[0.1, 0.2, 0.0]])),
    )
    supply = fd.FlodymArray(dims=dims["r",], values=np.array([0.1 + 0.2]))
    split = fd.FlodymArray(dims=dims, values=np.array([[0.1, 0.2, 0.7]]))
    system = make_system(
        largest_flow=3.0,
        dims=dims,
        trade_set=TradeSet(markets={"manufactured_products": trade}),
    )

    use_inflow = system.get_historical_use_inflow_by_trade_adjusted_split(
        "manufactured_products", supply, split, ("u",)
    )

    np.testing.assert_array_equal(use_inflow.values, [[0.0, 0.0, 3.0]])
