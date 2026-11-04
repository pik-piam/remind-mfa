"""Tests for `remind_mfa.common.trade_extrapolation.OpenGemTradeAligner`."""

import numpy as np
import flodym as fd
import pytest

from remind_mfa.common.trade import Trade
from remind_mfa.common.trade_extrapolation import OpenGemTradeAligner

T = fd.Dimension(name="Time", letter="t", items=list(range(2020, 2031)))
R = fd.Dimension(name="Region", letter="r", items=["A", "EUR", "C"])
U = fd.Dimension(name="End Use", letter="u", items=["x", "y"])
DIMS = fd.DimensionSet(dim_list=[T, R, U])
BASE_YEAR = 2025
T_0 = T.index(BASE_YEAR)
EUR = R.index("EUR")


def make_trade() -> Trade:
    """Globally balanced trade with dims (t, r, u)."""
    imports = fd.FlodymArray(dims=DIMS["t", "r", "u"])
    exports = fd.FlodymArray(dims=DIMS["t", "r", "u"])
    growth = np.linspace(1.0, 1.3, T.len)[:, None, None]
    imports.values[...] = growth * np.array([[10.0, 4.0], [20.0, 6.0], [5.0, 2.0]])
    exports.values[...] = growth * np.array([[15.0, 3.0], [8.0, 5.0], [12.0, 4.0]])
    return Trade(name="test", imports=imports, exports=exports)


def make_driver() -> fd.FlodymArray:
    driver = fd.FlodymArray(dims=DIMS["t", "r", "u"])
    growth = np.linspace(1.0, 1.5, T.len)[:, None, None]
    driver.values[...] = growth * np.array([[100.0, 40.0], [80.0, 30.0], [60.0, 20.0]])
    return driver


def make_ratio(end_value: float) -> fd.FlodymArray:
    """Ratio given for EUR only (as read from the cs4r file), rising linearly to `end_value`."""
    ratio = fd.FlodymArray(dims=DIMS["t", "r", "u"])
    ratio.values[:, EUR] = np.linspace(0.1, end_value, T.len)[:, None]
    return ratio


def align(trade: Trade, demand_driven: bool = True, imports_end=0.3, exports_end=0.05):
    driver = make_driver()
    kwargs = {"dom_demand": driver} if demand_driven else {"dom_supply": driver}
    OpenGemTradeAligner(
        trade=trade,
        imports_ratio=make_ratio(imports_end),
        exports_ratio=make_ratio(exports_end),
        base_year=BASE_YEAR,
        **kwargs,
    ).run()
    return driver


@pytest.mark.parametrize("demand_driven", [True, False])
def test_eur_ratio_follows_open_gem_index(demand_driven):
    trade = make_trade()
    original = make_trade()
    driver = align(trade, demand_driven=demand_driven)

    d = driver.values[:, EUR]
    ratio_i = make_ratio(0.3).values[:, EUR]
    ratio_e = make_ratio(0.05).values[:, EUR]
    a_0 = original.imports.values[T_0, EUR] / d[T_0]
    b_0 = original.exports.values[T_0, EUR] / d[T_0]
    future = slice(T_0, None)
    np.testing.assert_allclose(
        trade.imports.values[future, EUR] / d[future],
        a_0 * ratio_i[future] / ratio_i[T_0],
    )
    np.testing.assert_allclose(
        trade.exports.values[future, EUR] / d[future],
        b_0 * ratio_e[future] / ratio_e[T_0],
    )


def test_years_before_base_year_unchanged():
    trade = make_trade()
    original = make_trade()
    align(trade)
    for flow in ("imports", "exports"):
        np.testing.assert_allclose(
            getattr(trade, flow).values[:T_0], getattr(original, flow).values[:T_0]
        )
        # the base year itself is only re-expressed by its own ratio, so it is unchanged as well
        np.testing.assert_allclose(
            getattr(trade, flow).values[T_0], getattr(original, flow).values[T_0]
        )


def test_global_balance_and_non_negativity():
    trade = make_trade()
    align(trade)
    np.testing.assert_allclose(
        trade.imports.values.sum(axis=1), trade.exports.values.sum(axis=1), rtol=1e-12
    )
    assert np.all(trade.imports.values >= 0.0)
    assert np.all(trade.exports.values >= 0.0)


def test_other_regions_absorb_change_proportionally():
    trade = make_trade()
    original = make_trade()
    align(trade)
    others = [R.index("A"), R.index("C")]
    # all other regions' exports are scaled by the same factor per (t, u)
    factors = trade.exports.values[:, others] / original.exports.values[:, others]
    np.testing.assert_allclose(factors[:, 0], factors[:, 1])
    factors = trade.imports.values[:, others] / original.imports.values[:, others]
    np.testing.assert_allclose(factors[:, 0], factors[:, 1])


def test_supply_driven_net_exports_do_not_exceed_supply():
    trade = make_trade()
    supply = make_driver()
    # export ratio jumps 50-fold after the base year, so unclipped net exports would exceed supply
    exports_ratio = fd.FlodymArray(dims=DIMS["t", "r", "u"])
    exports_ratio.values[:, EUR] = np.where(np.array(T.items) > BASE_YEAR, 50.0, 1.0)[:, None]
    OpenGemTradeAligner(
        trade=trade,
        imports_ratio=make_ratio(0.3),
        exports_ratio=exports_ratio,
        dom_supply=supply,
        base_year=BASE_YEAR,
    ).run()
    driver = supply
    net_exports = trade.exports.values[:, EUR] - trade.imports.values[:, EUR]
    assert np.all(net_exports <= driver.values[:, EUR] * (1 + 1e-12))
    # the bound binds: net exports equal the supply in the final year
    np.testing.assert_allclose(net_exports[-1], driver.values[-1, EUR])


def test_demand_driven_net_imports_do_not_exceed_demand():
    trade = make_trade()
    driver = align(trade, demand_driven=True, imports_end=10.0)
    net_imports = trade.imports.values[:, EUR] - trade.exports.values[:, EUR]
    assert np.all(net_imports <= driver.values[:, EUR] * (1 + 1e-12))


def test_constant_ratio_keeps_trade_ratio():
    """An unchanged OPEN-GEM ratio keeps the base-year trade ratio of the region."""
    trade = make_trade()
    original = make_trade()
    driver = make_driver()
    ratio = fd.FlodymArray(dims=DIMS["t", "r", "u"])
    ratio.values[:, EUR] = 0.2
    OpenGemTradeAligner(
        trade=trade,
        imports_ratio=ratio,
        exports_ratio=ratio,
        dom_demand=driver,
        base_year=BASE_YEAR,
    ).run()
    d = driver.values[:, EUR]
    np.testing.assert_allclose(
        trade.imports.values[T_0:, EUR] / d[T_0:],
        np.broadcast_to(original.imports.values[T_0, EUR] / d[T_0], d[T_0:].shape),
    )


def test_other_regions_production_stays_non_negative():
    """Region C's net imports are close to its demand. When it absorbs the rising EUR exports
    by importing more, its domestic production would become negative without clipping."""
    imports = fd.FlodymArray(dims=DIMS["t", "r", "u"])
    exports = fd.FlodymArray(dims=DIMS["t", "r", "u"])
    imports.values[...] = np.array([10.0, 20.0, 30.0])[None, :, None]
    exports.values[...] = np.array([40.0, 15.0, 5.0])[None, :, None]
    trade = Trade(name="test", imports=imports, exports=exports)
    demand = fd.FlodymArray(dims=DIMS["t", "r", "u"])
    demand.values[...] = np.array([100.0, 80.0, 25.5])[None, :, None]
    OpenGemTradeAligner(
        trade=trade,
        imports_ratio=make_ratio(0.1),
        exports_ratio=make_ratio(1.0),
        dom_demand=demand,
        base_year=BASE_YEAR,
    ).run()
    production = demand.values - trade.imports.values + trade.exports.values
    assert np.all(production >= -1e-9)
    np.testing.assert_allclose(
        trade.imports.values.sum(axis=1), trade.exports.values.sum(axis=1), rtol=1e-12
    )
    # EUR exports still follow the OPEN-GEM index (ten-fold ratio increase from 2020 to 2030)
    ratio_e = make_ratio(1.0).values[:, EUR, 0]
    np.testing.assert_allclose(
        trade.exports.values[T_0:, EUR, 0], 15.0 * ratio_e[T_0:] / ratio_e[T_0]
    )


def test_exactly_one_driver_required():
    with pytest.raises(ValueError):
        OpenGemTradeAligner(
            trade=make_trade(),
            imports_ratio=make_ratio(0.3),
            exports_ratio=make_ratio(0.05),
            base_year=BASE_YEAR,
        )
