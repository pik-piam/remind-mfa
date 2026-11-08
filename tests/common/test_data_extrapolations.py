"""Tests for the regression in `remind_mfa.common.data_extrapolations`.

The in-use stock projection fits saturation curves to the historical stocks per capita with
scipy's least squares. The fit must be a smooth function of the data: with finite-difference
derivatives, the fitted parameters carry a noise of about 1e-9 relative that does not depend on
the size of the perturbation, which the CI run comparison picks up as a change of results.
"""

import warnings

import numpy as np
import pytest

from remind_mfa.common.data_extrapolations import (
    ArctanExtrapolation,
    Extrapolation,
    GompertzExtrapolation,
    LogisticExtrapolation,
    ProportionalExtrapolation,
)
from remind_mfa.common.data_transformations import Bound, BoundList

CURVES = [LogisticExtrapolation, ArctanExtrapolation, GompertzExtrapolation]
X = np.linspace(-1.5, 1.5, 31)
PRMS = np.array([2.0, 0.3, 1.2])
PREDICTOR = np.linspace(-1.0, 2.0, 40)
N_HISTORICAL = 25


class _FiniteDifferences(LogisticExtrapolation):
    """The logistic curve fitted with scipy's finite-difference derivatives."""

    jacobian = Extrapolation.jacobian


def _curve(cls: type[Extrapolation]) -> Extrapolation:
    """An instance to call the curve methods on; its data is irrelevant here."""
    return cls(data_to_extrapolate=np.zeros(X.size), predictor_values=X)


def _noisy_logistic_data() -> np.ndarray:
    """A logistic curve with 5 % noise, so that the fit has residuals as real data has."""
    truth = _curve(LogisticExtrapolation).func(PREDICTOR[:N_HISTORICAL], np.array([1.0, 0.4, 0.9]))
    return truth * (1 + 0.05 * np.random.default_rng(0).standard_normal(N_HISTORICAL))


def _fit(cls: type[Extrapolation], data: np.ndarray, bounds: BoundList | None = None) -> np.ndarray:
    kwargs = {"bound_list": bounds} if bounds is not None else {}
    extrapolation = cls(data_to_extrapolate=data, predictor_values=PREDICTOR, **kwargs)
    extrapolation.regress()
    return extrapolation.fit_prms


def test_has_jacobian():
    assert all(cls.has_jacobian() for cls in CURVES)
    assert not ProportionalExtrapolation.has_jacobian()
    assert not _FiniteDifferences.has_jacobian()
    with pytest.raises(NotImplementedError):
        _curve(ProportionalExtrapolation).jacobian(X, PRMS)


@pytest.mark.parametrize("cls", CURVES)
def test_jacobian_matches_finite_differences(cls):
    curve = _curve(cls)
    jacobian = curve.jacobian(X, PRMS)
    assert jacobian.shape == (X.size, 3)
    for index in range(3):
        step = np.zeros(3)
        step[index] = 1e-6
        numeric = (curve.func(X, PRMS + step) - curve.func(X, PRMS - step)) / 2e-6
        np.testing.assert_allclose(jacobian[:, index], numeric, rtol=1e-6, atol=1e-9)


@pytest.mark.parametrize("cls", CURVES)
def test_jacobian_of_a_scalar_is_one_derivative_per_parameter(cls):
    curve = _curve(cls)
    jacobian = curve.jacobian(0.5, PRMS)
    assert jacobian.shape == (3,)
    np.testing.assert_allclose(jacobian, curve.jacobian(np.array([0.5]), PRMS)[0])


@pytest.mark.parametrize("cls", [LogisticExtrapolation, GompertzExtrapolation])
def test_jacobian_is_zero_where_the_curve_underflows(cls):
    """The derivatives are the curve times a factor, so they are zero where the curve
    underflows; the factor must stay finite there (Gompertz: not ``log(f / a)``)."""
    curve = _curve(cls)
    x = np.array([-1e3, 0.0])  # the curve is 0 far below the offset
    assert curve.func(x, PRMS)[0] == 0.0
    with warnings.catch_warnings():
        # func itself may warn about the overflow of exp that makes the curve underflow
        warnings.filterwarnings("error", message="invalid value")
        warnings.filterwarnings("error", message="divide by zero")
        jacobian = curve.jacobian(x, PRMS)
    assert np.all(np.isfinite(jacobian))
    np.testing.assert_array_equal(jacobian[0], 0.0)
    assert np.all(jacobian[1] != 0.0)


FIXED_SATURATION = BoundList(bound_list=[Bound.fixed("saturation_level", 1.0)])


@pytest.mark.parametrize("bounds", [None, FIXED_SATURATION])
def test_regression_with_the_jacobian_finds_the_same_optimum(bounds):
    data = _noisy_logistic_data()
    analytic = _fit(LogisticExtrapolation, data, bounds)
    numeric = _fit(_FiniteDifferences, data, bounds)
    if bounds is not None:
        assert analytic[0] == 1.0
    np.testing.assert_allclose(analytic, numeric, rtol=1e-6)


def test_regression_with_the_jacobian_is_smooth_in_the_data():
    """A relative perturbation of 1e-12 of the data moves the fitted parameters by about as
    much; finite differences leave a floor of ~1e-9 whatever the perturbation."""
    data = _noisy_logistic_data()
    responses = {}
    for cls in (LogisticExtrapolation, _FiniteDifferences):
        reference = _fit(cls, data, FIXED_SATURATION)
        responses[cls] = 0.0
        for seed in range(3):
            noise = 1e-12 * np.random.default_rng(seed).standard_normal(data.shape)
            perturbed = _fit(cls, data * (1 + noise), FIXED_SATURATION)
            response = np.abs(perturbed - reference).max() / np.abs(reference).max()
            responses[cls] = max(responses[cls], response)
    assert responses[LogisticExtrapolation] < 1e-10
    assert responses[_FiniteDifferences] > 1e-10
