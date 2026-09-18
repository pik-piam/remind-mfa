"""Tests for setting future trade from data instead of extrapolating it.

Covers `remind_mfa.common.trade.set_trade_from_data`, which is used when
`cfg.trade.source == "data"` to prescribe future trade from input data (e.g. the output of the
ATLAS trade model), and the resolution of the configured trade markets in `TradeCfg`.

Dimensions are kept tiny: history 2000-2002, full time 2000-2004, two regions.
"""

import logging

import flodym as fd
import numpy as np
import pytest

from remind_mfa.common.trade import Trade, set_trade_from_data

H = fd.Dimension(name="Historic Time", letter="h", items=[2000, 2001, 2002])
T = fd.Dimension(name="Time", letter="t", items=[2000, 2001, 2002, 2003, 2004])
R = fd.Dimension(name="Region", letter="r", items=["A", "B"])

HISTORIC_DIMS = fd.DimensionSet(dim_list=[H, R])
FUTURE_DIMS = fd.DimensionSet(dim_list=[T, R])


def make_trade(dims: fd.DimensionSet, imports: list, exports: list) -> Trade:
    return Trade(
        imports=fd.FlodymArray(dims=dims, values=np.array(imports, dtype=float)),
        exports=fd.FlodymArray(dims=dims, values=np.array(exports, dtype=float)),
    )


def make_historic_trade() -> Trade:
    # globally balanced: region A imports what region B exports
    return make_trade(
        HISTORIC_DIMS,
        imports=[[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]],
        exports=[[0.0, 1.0], [0.0, 2.0], [0.0, 3.0]],
    )


def make_data(imports: list, exports: list) -> tuple[fd.FlodymArray, fd.FlodymArray]:
    return (
        fd.FlodymArray(dims=FUTURE_DIMS, values=np.array(imports, dtype=float)),
        fd.FlodymArray(dims=FUTURE_DIMS, values=np.array(exports, dtype=float)),
    )


def values(array: fd.FlodymArray) -> np.ndarray:
    return np.asarray(array.values, dtype=float)


def global_values(array: fd.FlodymArray) -> np.ndarray:
    """Values of the given array summed over all dimensions but time."""
    return values(array.sum_to(("t",)))


def test_data_is_used_for_future_and_historic_trade_for_historic_years():
    future_trade = Trade(
        imports=fd.FlodymArray(dims=FUTURE_DIMS), exports=fd.FlodymArray(dims=FUTURE_DIMS)
    )
    # the data deviates from the historic trade also in the historic years, and is balanced throughout
    imports, exports = make_data(
        imports=[[9.0, 0.0], [9.0, 0.0], [9.0, 0.0], [4.0, 0.0], [5.0, 0.0]],
        exports=[[0.0, 9.0], [0.0, 9.0], [0.0, 9.0], [0.0, 4.0], [0.0, 5.0]],
    )

    set_trade_from_data(future_trade, imports, exports, make_historic_trade())

    # historic years come from the historic trade, future years from the data
    np.testing.assert_allclose(values(future_trade.imports[{"r": "A"}]), [1.0, 2.0, 3.0, 4.0, 5.0])
    np.testing.assert_allclose(values(future_trade.exports[{"r": "B"}]), [1.0, 2.0, 3.0, 4.0, 5.0])
    # the other region trades nothing in this market
    np.testing.assert_allclose(values(future_trade.imports[{"r": "B"}]), 0.0)
    np.testing.assert_allclose(values(future_trade.exports[{"r": "A"}]), 0.0)


def test_unbalanced_data_is_balanced_and_warned_about(caplog):
    future_trade = Trade(
        imports=fd.FlodymArray(dims=FUTURE_DIMS), exports=fd.FlodymArray(dims=FUTURE_DIMS)
    )
    # in 2004, global imports (6) and exports (2) differ by a factor of three
    imports, exports = make_data(
        imports=[[1.0, 0.0], [2.0, 0.0], [3.0, 0.0], [4.0, 0.0], [6.0, 0.0]],
        exports=[[0.0, 1.0], [0.0, 2.0], [0.0, 3.0], [0.0, 4.0], [0.0, 2.0]],
    )

    with caplog.at_level(logging.WARNING):
        set_trade_from_data(future_trade, imports, exports, make_historic_trade())

    assert any("differ by up to" in record.message for record in caplog.records)
    global_imports = global_values(future_trade.imports)
    global_exports = global_values(future_trade.exports)
    np.testing.assert_allclose(global_imports, global_exports)
    # balanced to the harmonic mean of 6 and 2
    assert global_imports[-1] == pytest.approx(3.0)


def test_balancing_can_be_disabled():
    future_trade = Trade(
        imports=fd.FlodymArray(dims=FUTURE_DIMS), exports=fd.FlodymArray(dims=FUTURE_DIMS)
    )
    imports, exports = make_data(
        imports=[[1.0, 0.0], [2.0, 0.0], [3.0, 0.0], [4.0, 0.0], [6.0, 0.0]],
        exports=[[0.0, 1.0], [0.0, 2.0], [0.0, 3.0], [0.0, 4.0], [0.0, 2.0]],
    )

    set_trade_from_data(future_trade, imports, exports, make_historic_trade(), balance_to=None)

    assert values(future_trade.imports[{"r": "A"}])[-1] == pytest.approx(6.0)
    assert values(future_trade.exports[{"r": "B"}])[-1] == pytest.approx(2.0)


def test_years_not_covered_by_the_data_are_warned_about(caplog):
    future_trade = Trade(
        imports=fd.FlodymArray(dims=FUTURE_DIMS), exports=fd.FlodymArray(dims=FUTURE_DIMS)
    )
    # missing rows in the input files are read as zeros: here, 2004 is not covered
    imports, exports = make_data(
        imports=[[1.0, 0.0], [2.0, 0.0], [3.0, 0.0], [4.0, 0.0], [0.0, 0.0]],
        exports=[[0.0, 1.0], [0.0, 2.0], [0.0, 3.0], [0.0, 4.0], [0.0, 0.0]],
    )

    with caplog.at_level(logging.WARNING):
        set_trade_from_data(future_trade, imports, exports, make_historic_trade())

    assert any("2004" in record.message for record in caplog.records)


def test_historic_years_without_data_are_not_warned_about(caplog):
    future_trade = Trade(
        imports=fd.FlodymArray(dims=FUTURE_DIMS), exports=fd.FlodymArray(dims=FUTURE_DIMS)
    )
    # data covers future years only, historic years are taken from the historic trade anyway
    imports, exports = make_data(
        imports=[[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [4.0, 0.0], [5.0, 0.0]],
        exports=[[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 4.0], [0.0, 5.0]],
    )

    with caplog.at_level(logging.WARNING):
        set_trade_from_data(future_trade, imports, exports, make_historic_trade())

    assert not caplog.records
