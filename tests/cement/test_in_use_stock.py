"""Tests for the composition-resolved in-use stock of the future cement MFA.

`StockDrivenCementMFASystem.compute_in_use_stock` receives a product stock optionally without
the product material (m) and/or constituent (k) dimension. It derives the product inflow,
applies the missing splits to the inflow and recomputes the stock.
"""

import flodym as fd
import numpy as np

from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem

T = fd.Dimension(name="Time", letter="t", items=list(range(2000, 2011)))
R = fd.Dimension(name="Region", letter="r", items=["A", "B"])
U = fd.Dimension(name="End Use", letter="u", items=["X", "Y"])
M = fd.Dimension(name="Product Material", letter="m", items=["concrete", "mortar"])
K = fd.Dimension(name="Material Constituent", letter="k", items=["cement", "non-cement"])
DIMS = fd.DimensionSet(dim_list=[T, R, U, M, K])

STEP_YEAR = 2005


def make_mfa(cement_ratio: fd.Parameter) -> StockDrivenCementMFASystem:
    """Build a minimal future cement MFA holding only what compute_in_use_stock needs."""
    in_use_dims = DIMS[("t", "r", "u", "m", "k")]
    in_use = fd.InflowDrivenDSM(
        dims=in_use_dims,
        lifetime_model=fd.NormalLifetime(dims=in_use_dims, time_letter="t"),
        name="in_use",
    )
    parameters = {
        "lifetime_mean": fd.Parameter(dims=DIMS[("t", "r", "u")], values=np.full((11, 2, 2), 5.0)),
        "lifetime_std": fd.Parameter(dims=DIMS[("t", "r", "u")], values=np.full((11, 2, 2), 1.5)),
        "product_material_split": fd.Parameter(
            dims=DIMS[("r", "m")], values=np.array([[0.7, 0.3], [0.8, 0.2]])
        ),
        "cement_ratio": cement_ratio,
    }
    return StockDrivenCementMFASystem.model_construct(
        dims=DIMS, parameters=parameters, stocks={"in_use": in_use}
    )


def constant_cement_ratio() -> fd.Parameter:
    return fd.Parameter(dims=DIMS[("r", "m")], values=np.array([[0.15, 0.11], [0.14, 0.11]]))


def stepped_cement_ratio() -> fd.Parameter:
    """Cement ratio of constant_cement_ratio, reduced by 20% from STEP_YEAR on."""
    values = np.broadcast_to(constant_cement_ratio().values, (11, 2, 2)).copy()
    values[T.items.index(STEP_YEAR) :] *= 0.8
    return fd.Parameter(dims=DIMS[("t", "r", "m")], values=values)


def growing_stock(letters: tuple[str, ...]) -> fd.FlodymArray:
    dims = DIMS[letters]
    growth = np.linspace(100.0, 200.0, len(T.items)).reshape((-1,) + (1,) * (len(letters) - 1))
    return fd.FlodymArray(dims=dims, values=np.broadcast_to(growth, dims.shape).copy())


def test_adds_material_and_constituent_splits():
    mfa = make_mfa(constant_cement_ratio())
    product_stock = growing_stock(("t", "r", "u"))
    mfa.compute_in_use_stock(product_stock)

    in_use = mfa.stocks["in_use"]
    np.testing.assert_allclose(in_use.stock.sum_to(("t", "r", "u")).values, product_stock.values)

    # material shares of the inflow are product mass shares derived from the cement split
    prm = mfa.parameters
    expected_shares = (prm["product_material_split"] / prm["cement_ratio"]).get_shares_over("m")
    inflow_by_material = in_use.inflow.sum_to(("t", "r", "u", "m"))
    shares = inflow_by_material.get_shares_over("m")
    np.testing.assert_allclose(
        shares.values, expected_shares.cast_to(shares.dims).values, rtol=1e-10
    )


def test_adds_only_constituent_split_if_material_present():
    mfa = make_mfa(constant_cement_ratio())
    product_stock = growing_stock(("t", "r", "u", "m"))
    product_stock[{"m": "mortar"}] = product_stock[{"m": "mortar"}] * 0.25
    mfa.compute_in_use_stock(product_stock)

    in_use = mfa.stocks["in_use"]
    np.testing.assert_allclose(
        in_use.stock.sum_to(("t", "r", "u", "m")).values, product_stock.values, rtol=1e-10
    )
    cement_share = in_use.stock[{"k": "cement"}] / in_use.stock.sum_over("k")
    np.testing.assert_allclose(
        cement_share.values,
        mfa.parameters["cement_ratio"].cast_to(cement_share.dims).values,
        rtol=1e-10,
    )


def test_time_dependent_cement_ratio_only_affects_new_cohorts():
    product_stock = growing_stock(("t", "r", "u"))
    constant = make_mfa(constant_cement_ratio())
    constant.compute_in_use_stock(product_stock)
    stepped = make_mfa(stepped_cement_ratio())
    stepped.compute_in_use_stock(product_stock)

    def cement_stock(mfa: StockDrivenCementMFASystem) -> np.ndarray:
        return mfa.stocks["in_use"].stock[{"k": "cement"}].sum_to(("t", "r")).values

    step_index = T.items.index(STEP_YEAR)
    # before the step, the cement stock is identical
    np.testing.assert_allclose(
        cement_stock(stepped)[:step_index], cement_stock(constant)[:step_index]
    )
    # in the step year, old cohorts keep their cement content: the stock drops by less
    # than the 20% reduction applied to new cohorts
    ratio = cement_stock(stepped)[step_index] / cement_stock(constant)[step_index]
    assert np.all((ratio > 0.8) & (ratio < 1.0))
    # the total product stock is unaffected by the cement ratio
    np.testing.assert_allclose(
        stepped.stocks["in_use"].stock.sum_to(("t", "r", "u")).values, product_stock.values
    )


def test_keeps_fully_resolved_stock():
    mfa = make_mfa(constant_cement_ratio())
    product_stock = growing_stock(("t", "r", "u", "m", "k"))
    mfa.compute_in_use_stock(product_stock)

    np.testing.assert_allclose(
        mfa.stocks["in_use"].stock.values, product_stock.values, rtol=1e-10
    )
