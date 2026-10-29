"""Tests for capping and redistributing net trade in `CommonMFASystem`.

Three regions trade in two years; values are small enough to compute the expected results by
hand. Region A is the capped one, B and C are its trade partners.
"""

import numpy as np
import flodym as fd
import pytest

from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.common.trade import Trade

T = fd.Dimension(name="Time", letter="t", items=[2030, 2040])
R = fd.Dimension(name="Region", letter="r", items=["A", "B", "C"])
DIMS = fd.DimensionSet(dim_list=[T, R])


def make_system() -> CommonMFASystem:
    """Minimal system; its only flow sets the magnitude for the numerical tolerance."""
    processes = fd.make_processes(["sysenv", "market"])
    flows = fd.make_empty_flows(
        processes=processes,
        flow_definitions=[
            fd.FlowDefinition(from_process="sysenv", to_process="market", dim_letters=("t", "r"))
        ],
        dims=DIMS,
    )
    flows["sysenv => market"][...] = 10.0
    return CommonMFASystem.model_construct(
        dims=DIMS, parameters={}, processes=processes, flows=flows, stocks={}
    )


def make_trade(imports: list[float], exports: list[float]) -> Trade:
    """Trade with the same per-region values in both years."""
    return Trade(
        name="test",
        imports=fd.FlodymArray(dims=DIMS, values=np.tile(imports, (T.len, 1))),
        exports=fd.FlodymArray(dims=DIMS, values=np.tile(exports, (T.len, 1))),
    )


def make_limit(values_2030: list[float], values_2040: list[float]) -> fd.FlodymArray:
    return fd.FlodymArray(dims=DIMS, values=np.array([values_2030, values_2040]))


def test_cap_net_imports_reduces_imports_and_partner_exports():
    trade = make_trade(imports=[10.0, 0.0, 0.0], exports=[0.0, 8.0, 2.0])
    capacity = make_limit([4.0, np.inf, np.inf], [np.inf, np.inf, np.inf])

    make_system().cap_net_imports_to_capacity(trade, capacity=capacity)

    # 2030: A only takes 4 of 10, so partners export 40 % of their original amounts
    np.testing.assert_allclose(trade.imports[2030].values, [4.0, 0.0, 0.0])
    np.testing.assert_allclose(trade.exports[2030].values, [0.0, 3.2, 0.8])
    # 2040 has infinite capacity and stays unchanged
    np.testing.assert_allclose(trade.imports[2040].values, [10.0, 0.0, 0.0])
    np.testing.assert_allclose(trade.exports[2040].values, [0.0, 8.0, 2.0])


def test_cap_net_imports_keeps_stopover_trade():
    trade = make_trade(imports=[10.0, 0.0, 0.0], exports=[5.0, 5.0, 0.0])
    capacity = make_limit([2.0, np.inf, np.inf], [np.inf, np.inf, np.inf])

    make_system().cap_net_imports_to_capacity(trade, capacity=capacity)

    # A keeps re-exporting 5, its net imports drop from 5 to the capacity of 2
    np.testing.assert_allclose(trade.imports[2030].values, [7.0, 0.0, 0.0])
    np.testing.assert_allclose(trade.exports[2030].values, [5.0, 2.0, 0.0])
    np.testing.assert_allclose(trade.net_imports[2030]["A"].values, 2.0)


@pytest.mark.parametrize("capacity_a", [10.0, np.inf])
def test_cap_net_imports_within_capacity_is_noop(capacity_a: float):
    trade = make_trade(imports=[10.0, 0.0, 0.0], exports=[0.0, 8.0, 2.0])
    capacity = make_limit([capacity_a, 0.0, 0.0], [capacity_a, 0.0, 0.0])

    make_system().cap_net_imports_to_capacity(trade, capacity=capacity)

    np.testing.assert_allclose(trade.imports.values, np.tile([10.0, 0.0, 0.0], (2, 1)))
    np.testing.assert_allclose(trade.exports.values, np.tile([0.0, 8.0, 2.0], (2, 1)))


def test_cap_net_exports_reduces_exports_and_partner_imports():
    trade = make_trade(imports=[0.0, 8.0, 2.0], exports=[10.0, 0.0, 0.0])
    supply = make_limit([4.0, 20.0, 20.0], [20.0, 20.0, 20.0])

    make_system().cap_historical_net_exports_to_supply(trade, supply=supply)

    np.testing.assert_allclose(trade.exports[2030].values, [4.0, 0.0, 0.0])
    np.testing.assert_allclose(trade.imports[2030].values, [0.0, 3.2, 0.8])
    np.testing.assert_allclose(trade.exports[2040].values, [10.0, 0.0, 0.0])
    np.testing.assert_allclose(trade.imports[2040].values, [0.0, 8.0, 2.0])


def test_redistribute_surplus_fills_headroom_proportionally():
    trade = make_trade(imports=[0.0, 0.0, 0.0], exports=[0.0, 0.0, 0.0])
    # 2030: A has a surplus of 6, B and C have headroom 9 and 3
    # 2040: A has a surplus of 6, but B and C only have a total headroom of 4
    supply = make_limit([16.0, 1.0, 2.0], [16.0, 7.0, 3.0])
    demand = make_limit([10.0, 10.0, 5.0], [10.0, 10.0, 4.0])

    make_system().redistribute_surplus(trade, supply=supply, demand=demand)

    np.testing.assert_allclose(trade.exports[2030].values, [6.0, 0.0, 0.0])
    np.testing.assert_allclose(trade.imports[2030].values, [0.0, 4.5, 1.5])
    # headroom is filled completely, A keeps the remaining surplus of 2
    np.testing.assert_allclose(trade.exports[2040].values, [4.0, 0.0, 0.0])
    np.testing.assert_allclose(trade.imports[2040].values, [0.0, 3.0, 1.0])


def test_redistribute_surplus_without_surplus_is_empty():
    trade = make_trade(imports=[0.0, 0.0, 0.0], exports=[0.0, 0.0, 0.0])
    supply = make_limit([1.0, 1.0, 1.0], [1.0, 1.0, 1.0])
    demand = make_limit([2.0, 2.0, 1.0], [1.0, 1.0, 1.0])

    make_system().redistribute_surplus(trade, supply=supply, demand=demand)

    np.testing.assert_allclose(trade.imports.values, 0.0)
    np.testing.assert_allclose(trade.exports.values, 0.0)


def test_cap_net_keeps_capped_regions_fixed():
    """A is capped first; re-balancing then pushes B above its cap. A's re-exports stay
    untouched while B is capped, only the uncapped exporters C and D are scaled down."""
    regions = fd.Dimension(name="Region", letter="r", items=["A", "B", "C", "D"])
    dims = fd.DimensionSet(dim_list=[regions])
    trade = Trade(
        name="test",
        imports=fd.FlodymArray(dims=dims, values=np.array([10.0, 3.0, 0.0, 0.0])),
        exports=fd.FlodymArray(dims=dims, values=np.array([2.0, 2.0, 6.0, 3.0])),
    )
    limit = fd.FlodymArray(dims=dims, values=np.array([4.0, 1.5, np.inf, np.inf]))

    trade.cap_net(limit, direction="imports", tolerance=1e-12)

    # first round: A imports 6, the exports of B, C, D are scaled by 7/11 to balance
    # second round: B's net imports exceed 1.5 and are capped, C and D are scaled down again
    np.testing.assert_allclose(trade.imports.values, [6.0, 1.5 + 14 / 11, 0.0, 0.0])
    np.testing.assert_allclose(trade.exports.values, [2.0, 14 / 11, 11 / 3, 11 / 6])
    np.testing.assert_allclose(trade.imports.values.sum(), trade.exports.values.sum())


def test_cap_historical_net_imports_to_demand_rebalances():
    trade = make_trade(imports=[10.0, 0.0, 0.0], exports=[0.0, 8.0, 2.0])
    demand = make_limit([4.0, 20.0, 20.0], [20.0, 20.0, 20.0])

    make_system().cap_historical_net_imports_to_demand(trade, demand=demand)

    np.testing.assert_allclose(trade.imports[2030].values, [4.0, 0.0, 0.0])
    np.testing.assert_allclose(trade.exports[2030].values, [0.0, 3.2, 0.8])
    np.testing.assert_allclose(trade.imports[2040].values, [10.0, 0.0, 0.0])
    np.testing.assert_allclose(trade.exports[2040].values, [0.0, 8.0, 2.0])
