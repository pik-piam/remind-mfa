"""Tests for the regional adaptation of the in-use stock regression in
`remind_mfa.common.fit_stocks`.

`StockFitter.fit_single` minimizes a penalty that trades the fit to the last historical level
and slope of a region against the deviation from the common regression parameters. The result
must be the minimum of that penalty within the bounds of the regional parameters.
"""

import logging

import flodym as fd
import numpy as np
import pytest
from scipy.optimize import minimize

from remind_mfa.common.data_extrapolations import LogisticExtrapolation
from remind_mfa.common.data_transformations import Bound, BoundList
from remind_mfa.common.fit_stocks import StockFitter

H = fd.Dimension(name="Historical Time", letter="h", items=list(range(1990, 2025)))
T = fd.Dimension(name="Time", letter="t", items=list(range(1990, 2071)))
R = fd.Dimension(name="Region", letter="r", items=["A", "B"])
U = fd.Dimension(name="End use", letter="u", items=["X"])
N_HIST = len(H.items)

COMMON_PRMS = np.array([1.0, -0.3, 2.0])
# the normalized weights of StockExtrapolation.regional_adaptation
PENALTY_WEIGHTS = {
    "data_0th_order": 20.0,
    "rel_data_0th_order": 1.0,
    "data_1st_order": 4000.0,
    "prms": np.array([10.0, 7.5, 0.025]),
}
# as in StockExtrapolation.regional_adaptation
GROWTH_RATE_BOUND = BoundList(
    target_dims=fd.DimensionSet(dim_list=[R, U]),
    bound_list=[Bound(var_name="growth_rate", lower_bound=0, upper_bound=np.inf)],
)


def _predictor() -> np.ndarray:
    """A predictor growing in time, as the normalized log GDP per capita does."""
    predictor = np.linspace(-1.0, 1.0, len(T.items))
    return np.broadcast_to(predictor[:, np.newaxis, np.newaxis], (len(T.items), 2, 1)).copy()


def _logistic(prms: np.ndarray) -> np.ndarray:
    return LogisticExtrapolation.func(LogisticExtrapolation, _predictor()[:, 0, 0], prms)


def _fitter(historical: np.ndarray, bound_list: BoundList | None = None) -> StockFitter:
    """A fitter for two regions with the given historical per-capita stocks (same for both)."""
    historical_values = np.broadcast_to(historical[:, np.newaxis, np.newaxis], (N_HIST, 2, 1))
    extrapolation = LogisticExtrapolation(
        data_to_extrapolate=historical_values.copy(),
        predictor_values=_predictor(),
        independent_dims=(2,),
    )
    extrapolation._fit_prms = COMMON_PRMS[np.newaxis, :].copy()
    return StockFitter(
        historical_stocks_pc=fd.FlodymArray(
            dims=fd.DimensionSet(dim_list=[H, R, U]), values=historical_values.copy()
        ),
        extrapolation=extrapolation,
        dims_out=fd.DimensionSet(dim_list=[T, R, U]),
        penalty_weights=PENALTY_WEIGHTS,
        predictor=_predictor(),
        current_population=fd.FlodymArray(dims=fd.DimensionSet(dim_list=[R]), values=np.ones(2)),
        bound_list=bound_list or BoundList(),
    )


def _fit_single(fitter: StockFitter, historical: np.ndarray, **kwargs) -> np.ndarray:
    return fitter.fit_single(historical, _predictor()[:, 0, 0], COMMON_PRMS, **kwargs)


def _gradient(fitter: StockFitter, historical: np.ndarray, prms: np.ndarray) -> np.ndarray:
    return fitter.jacobian(historical, _predictor()[:, 0, 0], prms, COMMON_PRMS)


def _continuing(prms: np.ndarray) -> np.ndarray:
    """Historical data that the curve with `prms` continues exactly: its last level, and its
    first future slope (over the 10 years after the history) equals the data's last slope (over
    the last 10 historical years)."""
    curve = _logistic(prms)
    historical = curve[:N_HIST].copy()
    historical[N_HIST - 11] = curve[N_HIST - 1] - (curve[N_HIST + 10] - curve[N_HIST])
    return historical


# a region above the common curve that grows faster: the fit is a compromise
DEVIATING = _continuing(np.array([1.2, -0.4, 3.0]))
# a region whose stocks decline: matching the slope needs a negative growth rate
DECLINING = _logistic(COMMON_PRMS)[:N_HIST].copy()
DECLINING[N_HIST - 10 :] = DECLINING[N_HIST - 11] * (1 - 0.005 * np.arange(1, 11))


def test_fit_single_finds_the_common_parameters_if_the_common_curve_continues_the_data():
    """The penalty is zero at the common parameters only. The offset scan starts the minimizer
    0.02 or more away from them; BFGS stopping at a gradient of 1e-3 ends 3e-3 away here, and
    L-BFGS-B with scipy's default ftol 1e-3."""
    historical = _continuing(COMMON_PRMS)
    fitter = _fitter(historical)
    assert fitter.penalty(historical, _predictor()[:, 0, 0], COMMON_PRMS, COMMON_PRMS) == 0
    prms = _fit_single(fitter, historical)
    np.testing.assert_allclose(prms, COMMON_PRMS, rtol=0, atol=1e-5)


def test_fit_single_returns_a_minimum_of_the_penalty():
    fitter = _fitter(DEVIATING)
    prms = _fit_single(fitter, DEVIATING)
    assert np.abs(_gradient(fitter, DEVIATING, prms)).max() < 1e-5
    assert np.abs(prms - COMMON_PRMS).max() > 0.05  # a compromise, not the common curve
    penalty = fitter.penalty(DEVIATING, _predictor()[:, 0, 0], prms, COMMON_PRMS)
    for direction in np.vstack([np.eye(3), -np.eye(3)]):
        moved = prms + 1e-4 * direction
        assert fitter.penalty(DEVIATING, _predictor()[:, 0, 0], moved, COMMON_PRMS) > penalty
    # the same minimum as a minimizer started elsewhere and run to a tight tolerance
    reference = minimize(
        lambda x: fitter.penalty(DEVIATING, _predictor()[:, 0, 0], x, COMMON_PRMS),
        x0=COMMON_PRMS,
        jac=lambda x: _gradient(fitter, DEVIATING, x),
        method="BFGS",
        options={"gtol": 1e-7},
    )
    np.testing.assert_allclose(prms, reference.x, rtol=0, atol=1e-5)


def test_fit_keeps_the_growth_rate_non_negative():
    assert _fit_single(_fitter(DECLINING), DECLINING)[2] < 0
    fitter = _fitter(DECLINING, GROWTH_RATE_BOUND)
    # a growth rate of 0 makes the regional curve flat
    regression = fitter.fit().values
    np.testing.assert_array_equal(regression, np.broadcast_to(regression[0], regression.shape))
    bounds = fitter.bound_list.to_np_array(fitter.extrapolation.prm_names)[0, 0]
    prms = _fit_single(fitter, DECLINING, bounds=bounds)
    assert prms[2] == 0
    # minimum over the free parameters; at the bound, the penalty increases inwards
    gradient = _gradient(fitter, DECLINING, prms)
    assert np.abs(gradient[:2]).max() < 1e-5
    assert gradient[2] > 0


def test_fitter_needs_bounds_with_the_region_and_end_use_dims():
    bound_list = BoundList(
        target_dims=fd.DimensionSet(dim_list=[U]),
        bound_list=[Bound(var_name="growth_rate", lower_bound=0, upper_bound=np.inf)],
    )
    with pytest.raises(ValueError, match="bounds must have"):
        _fitter(DEVIATING, bound_list)


def test_fit_falls_back_to_the_common_parameters_if_the_optimization_fails(caplog):
    historical = np.stack([DEVIATING, np.full(N_HIST, np.nan)], axis=1)[..., np.newaxis]
    fitter = _fitter(DEVIATING)
    fitter.historical_stocks_pc.values[...] = historical
    with caplog.at_level(logging.WARNING):
        regression = fitter.fit()
    assert "Optimization failed for 1 end use-region combinations" in caplog.text
    np.testing.assert_allclose(regression.values[:, 1, 0], _logistic(COMMON_PRMS))
    expected = _logistic(_fit_single(fitter, DEVIATING))
    np.testing.assert_allclose(regression.values[:, 0, 0], expected)
