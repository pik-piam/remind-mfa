from abc import abstractmethod
from typing import Optional, Tuple, ClassVar, Type
import numpy as np
import sys
from pydantic import model_validator
from scipy.optimize import least_squares
from pydantic import PrivateAttr

from remind_mfa.common.helpers import RemindMFABaseModel
from remind_mfa.common.data_transformations import BoundList


class Extrapolation(RemindMFABaseModel):
    """
    Base class for extrapolation methods.
    This class provides a framework for extrapolating (historical) data to predictor values using regression techniques.
    The functional form of the extrapolation is defined by the `func` method, which should be implemented in subclasses.
    """

    data_to_extrapolate: np.ndarray
    """historical data"""
    predictor_values: np.ndarray
    """predictor variable(s) covering range of data_to_extrapolate and beyond."""
    weights: Optional[np.ndarray] = None
    """Weights for the data to extrapolate. Defaults None, i.e., equal weights for all data points."""
    bound_list: BoundList = BoundList()
    """Bounds for the parameters to be fitted. Defaults to no bounds."""
    independent_dims: Tuple[int, ...] = ()
    """Indizes for dimensions across which to regress independently. Other dimensions are regressed commonly."""
    prm_names: ClassVar[list[str]] = []
    """Names of the parameters to be fitted. Set in subclasses."""
    _fit_prms: np.ndarray = PrivateAttr(default=None)
    """Optimized parameters after regression (set by calling regress())."""

    @model_validator(mode="after")
    def validate_data(self):
        assert (
            self.data_to_extrapolate.shape[0] <= self.predictor_values.shape[0]
        ), "data_to_extrapolate cannot be longer than predictor_values"
        assert (
            self.data_to_extrapolate.shape[1:] == self.predictor_values.shape[1:]
        ), "Data to extrapolate and predictor_values must have the same shape except for the first dimension."
        if self.weights is None:
            self.weights = np.ones_like(self.data_to_extrapolate)
        else:
            assert (
                self.weights.shape == self.data_to_extrapolate.shape
            ), "Weights must have the same shape as data_to_extrapolate."
        return self

    @property
    def n_prms(self):
        """Number of parameters to be fitted."""
        return len(self.prm_names)

    @property
    def n_historic(self):
        """Number of historic data points to use for regression."""
        return self.data_to_extrapolate.shape[0]

    @property
    def fit_prms(self) -> np.ndarray:
        """Optimized parameters after regression (read-only)."""
        return self._fit_prms

    def extrapolate(self, historic_from_regression: bool = False):
        """
        Calls the regression method and returns extrapolated values.
        Per default, historic values are kept, but this can be changed by setting `historic_from_regression` to True.
        """

        regression = self.regress()
        if not historic_from_regression:
            regression[: self.n_historic, ...] = self.data_to_extrapolate
        return regression

    @abstractmethod
    def func(x: np.ndarray, prms: np.ndarray, **kwargs) -> np.ndarray:
        """
        Function to fit the data to the predictor values.
        Should be implemented in subclasses.

        Args:
            x (np.ndarray): Predictor values.
            prms (np.ndarray): Parameters to fit.
            **kwargs: Additional keyword arguments.
        Returns:
            np.ndarray: Fitted values based on the predictor values and parameters.
        """
        pass

    @abstractmethod
    def initial_guess(
        self, predictor_values: np.ndarray, data_to_extrapolate: np.ndarray
    ) -> np.ndarray:
        """gets either one-dimensional or multi-dimensional data, but always returns one scalar value per prm"""
        pass

    def get_fitting_function(
        self,
        predictor_values: np.ndarray,
        data_to_extrapolate: np.ndarray,
        weights: np.ndarray,
    ) -> callable:

        def fitting_function(prms: np.ndarray) -> np.ndarray:
            f = self.func(predictor_values, prms)
            loss = weights * (f - data_to_extrapolate)
            return loss.flatten()

        return fitting_function

    def regress(self):
        """
        Fits the data to the predictor values using regression and returns the extrapolated values.
        The regression is performed independently for each dimension specified in `independent_dims`.
        """
        # extract dimensions that are regressed independently
        predictor_shape = tuple(
            [self.predictor_values.shape[i] for i in sorted(self.independent_dims)]
        )
        regression = np.zeros(self.predictor_values.shape, dtype=float)
        self._fit_prms = np.zeros(predictor_shape + (self.n_prms,))
        bounds_array = self.bound_list.to_np_array(self.prm_names)

        # loop over dimensions that are regressed independently
        for slice_indep in np.ndindex(predictor_shape):

            slice_all = [slice(None)] * len(self.predictor_values.shape)
            for i, j in enumerate(self.independent_dims):
                slice_all[j] = slice_indep[i]
            slice_all = tuple(slice_all)

            self._fit_prms[slice_indep], regression[slice_all] = self.regress_common(
                self.predictor_values[slice_all],
                self.data_to_extrapolate[slice_all],
                self.weights[slice_all],
                bounds_array[slice_indep] if bounds_array is not None else (-np.inf, np.inf),
            )

        return regression

    def regress_common(self, predictor, data, weights, bounds):
        """
        Finds optimal fit of data through least squares. Weights and bounds are applied.
        """
        fitting_function = self.get_fitting_function(
            predictor[: self.n_historic, ...],
            data,
            weights,
        )
        initial_guess = self.initial_guess(predictor, data)
        # correct initial guess
        initial_guess = self.correct_initial_guess_with_bounds(initial_guess, bounds)
        fit_prms = least_squares(fitting_function, x0=initial_guess, gtol=1.0e-12, bounds=bounds).x
        regression = self.func(predictor, fit_prms)
        return fit_prms, regression

    @staticmethod
    def correct_initial_guess_with_bounds(
        initial_guess: np.ndarray, bounds: Tuple[np.ndarray, np.ndarray]
    ):
        """Ensure that the initial guess is within the provided bounds."""

        outside_bounds = (initial_guess < bounds[0]) + (initial_guess > bounds[1])
        if np.any(outside_bounds):
            idx = np.where(outside_bounds)[0]
            lower = bounds[0][idx]
            upper = bounds[1][idx]
            # If lower is -inf, use upper; if upper is inf, use lower; else use mean
            use_upper = np.isinf(lower) & ~np.isinf(upper)
            use_lower = np.isinf(upper) & ~np.isinf(lower)
            use_mean = ~(use_upper | use_lower)
            initial_guess[idx[use_upper]] = upper[use_upper]
            initial_guess[idx[use_lower]] = lower[use_lower]
            initial_guess[idx[use_mean]] = (lower[use_mean] + upper[use_mean]) / 2
        return initial_guess


class ProportionalExtrapolation(Extrapolation):

    prm_names: ClassVar[list[str]] = ["proportionality_factor"]

    @staticmethod
    def func(x, prms):
        return prms[0] * x

    def initial_guess(self, predictor_values, data_to_extrapolate):
        return np.array([1.0])


class PehlExtrapolation(Extrapolation):

    prm_names: ClassVar[list[str]] = ["saturation_level", "stretch_factor"]

    @staticmethod
    def func(x, prms):
        return prms[0] / (1.0 + np.exp(prms[1] / x))

    def initial_guess(self, predictor_values, data_to_extrapolate):
        return np.array(
            [
                2.0 * np.max(predictor_values[self.n_historic - 1, ...]),
                np.max(data_to_extrapolate[-1, ...]),
            ]
        )


class ExponentialSaturationExtrapolation(Extrapolation):

    prm_names: ClassVar[list[str]] = ["saturation_level", "stretch_factor"]

    @staticmethod
    def func(x, prms):
        return prms[0] * (1 - np.exp(-prms[1] * x))

    def initial_guess(self, predictor_values, data_to_extrapolate):
        current_level = np.max(data_to_extrapolate[-1, ...])
        current_extrapolator = np.max(predictor_values[self.n_historic - 1, ...])
        initial_saturation_level = 2.0 * current_level
        initial_stretch_factor = (
            -np.log(1 - current_level / initial_saturation_level) / current_extrapolator
        )
        return np.array([initial_saturation_level, initial_stretch_factor])


class LogisticExtrapolation(Extrapolation):

    prm_names: ClassVar[list[str]] = ["saturation_level", "stretch_factor", "x_offset"]

    @staticmethod
    def func(x, prms):
        return prms[0] / (1.0 + np.exp(-prms[1] * (x - prms[2])))

    def initial_guess(self, predictor_values, data_to_extrapolate):
        max_level = np.max(data_to_extrapolate)
        sat_level_guess = 2 * max_level

        mean_predictor = np.mean(predictor_values)
        max_predictor = np.max(predictor_values)
        stretch_factor = 2 / (max_predictor - mean_predictor)
        return np.array([sat_level_guess, stretch_factor, mean_predictor])


class TwoPredictorExtrapolation(Extrapolation):
    """
    Base class for extrapolations with two predictors.
    Mainly used for classification of these subclasses.
    """

    # point to the corresponding single-predictor class (override in subclasses)
    single_predictor_cls: ClassVar[Optional[Type[Extrapolation]]] = None

    def check_predictor(self, x):
        x2 = x["x2"]
        assert (
            x2 is not None
        ), f"{type(self).__name__} requires a secondary predictor with field name 'x2', but it was not found in the predictor values."

    def selective_product(self, key: str, factors: dict):
        if key is None:
            # product of all factor values
            return np.prod(list(factors.values()), axis=0)
        elif key in factors:
            return factors[key]
        else:
            raise ValueError(
                f"Invalid factor key: {key}. Valid keys are: {list(factors.keys())} or None for product of all factors."
            )


class TwoPredictorLogisticExtrapolation(TwoPredictorExtrapolation):
    """
    Two-predictor logistic-style extrapolation:
    model: A * f_x1(x1; k_x1, x1_0) * f_x2(x2; k_x2, x2_0)
    Prm order: [saturation_level (A), k_x1, x1_0, k_x2, x2_0]
    """

    single_predictor_cls = LogisticExtrapolation

    prm_names: ClassVar[list[str]] = [
        "saturation_level",
        "x1_stretch_factor",
        "x1_offset",
        "x2_stretch_factor",
        "x2_offset",
    ]

    def func(self, x: np.ndarray, prms: np.ndarray, factor: str = None) -> np.ndarray:
        self.check_predictor(x)
        a, k_x1, x1_0, k_x2, x2_0 = prms
        x1, x2 = x["x1"], x["X2"]

        f1 = np.ones_like(x1) * a
        f2 = 1.0 / (1.0 + np.exp(-k_x1 * (x1 - x1_0)))
        f3 = 1.0 / (1.0 + np.exp(-k_x2 * (x2 - x2_0)))
        factors = {"f1": f1, "f2": f2, "f3": f3}
        return self.selective_product(factor, factors)

    def initial_guess(
        self,
        predictor_values: np.ndarray,
        data_to_extrapolate: np.ndarray,
    ) -> np.ndarray:
        max_level = np.max(data_to_extrapolate)
        sat_level_guess = 2.0 * max_level

        mean_x1 = np.mean(predictor_values["x1"][: self.n_historic, ...])
        max_x1 = np.max(predictor_values["x1"][: self.n_historic, ...])
        k_x1_guess = 2.0 / (max_x1 - mean_x1)

        mean_x2 = np.mean(predictor_values["x2"][: self.n_historic, ...])
        max_x2 = np.max(predictor_values["x2"][: self.n_historic, ...])
        k_x2_guess = 2.0 / (max_x2 - mean_x2)

        return np.array([sat_level_guess, k_x1_guess, mean_x1, k_x2_guess, mean_x2])


class GompertzExtrapolation(Extrapolation):
    """
    Gompertz extrapolation:
    Prm order: [saturation_level, offset, growth_rate]
    In this parameterization,
    - the offset shifts the curve horizontally, setting the half-point (50% saturation) at x = -offset,
    - and the growth_rate controls the steepness of the curve.
    The maximum derivative (at the inflection point) is exactly equal to: saturation_level * growth_rate / e.
    """

    prm_names: ClassVar[list[str]] = [
        "saturation_level",
        "offset",
        "growth_rate",
    ]

    def func(self, x: np.ndarray, prms: np.ndarray) -> np.ndarray:
        """
        x : structured array with fields 'x1' and 'x2'
        """
        a, b, c = prms[:3]
        inner = np.clip(-c * (x + b), -500, 500)
        return a * np.exp(-np.exp(inner) * np.log(2))

    def jacobian(self, x: np.ndarray, prms: np.ndarray) -> np.ndarray:
        a, b, c = prms[:3]
        f = self.func(x, prms)
        if f == 0:
            return np.zeros(3)
        # Use log(f/a) = -exp(-c*(x+b))*log(2) to avoid intermediate overflow
        log_f_over_a = np.log(f / a)
        da = f / a
        db = -f * c * log_f_over_a
        dc = -f * (x + b) * log_f_over_a
        return np.stack([da, db, dc], axis=-1)

    def log_jacobian(self, x: np.ndarray, prms: np.ndarray) -> np.ndarray:
        """Derivative of log(f) w.r.t. prms, computed directly in log-space.

        For Gompertz f = a * exp(-exp(-c*(x+b)) * ln2):
            log(f) = log(a) - exp(-c*(x+b)) * ln2
            d(log f)/da = 1/a
            d(log f)/db = c * exp(-c*(x+b)) * ln2
            d(log f)/dc = (x+b) * exp(-c*(x+b)) * ln2

        Unlike (1/f)*jacobian, these are numerically stable even when f ≈ 0.
        """
        a, b, c = prms[:3]
        exp_term = np.exp(np.clip(-c * (x + b), -500, 500))
        ln2 = np.log(2)
        d_log_f_da = 1.0 / a
        d_log_f_db = c * exp_term * ln2
        d_log_f_dc = (x + b) * exp_term * ln2
        return np.stack([d_log_f_da, d_log_f_db, d_log_f_dc], axis=-1)

    def initial_guess(
        self,
        predictor_values: np.ndarray,
        data_to_extrapolate: np.ndarray,
    ) -> np.ndarray:
        max_level = np.max(data_to_extrapolate)
        sat_level_guess = 2.0 * max_level

        c_guess = 1
        b_guess = 1
        return np.array([sat_level_guess, b_guess, c_guess])


class TwoPredictorGompertzExtrapolation(TwoPredictorExtrapolation):
    """
    Two-predictor Gompertz extrapolation:
    model: a * f_x1 * f_x2
    Prm order: [saturation_level (a), b_x1, c_x1, b_x2, c_x2]
    """

    single_predictor_cls = GompertzExtrapolation

    prm_names: ClassVar[list[str]] = [
        "saturation_level",
        "x1_offset",
        "x1_growth_rate",
        "x2_offset",
        "x2_growth_rate",
    ]

    def func(self, x: np.ndarray, prms: np.ndarray, factor: str = None) -> np.ndarray:
        self.check_predictor(x)
        a, b_x1, c_x1, b_x2, c_x2 = prms
        x1, x2 = x["x1"], x["x2"]

        f1 = np.ones_like(x1) * a
        f2 = np.exp(-np.exp(np.clip(-c_x1 * (x1 + b_x1), -500, 500)) * np.log(2))
        f3 = np.exp(-np.exp(np.clip(-c_x2 * (x2 + b_x2), -500, 500)) * np.log(2))
        factors = {"f1": f1, "f2": f2, "f3": f3}
        return self.selective_product(factor, factors)

    def initial_guess(
        self,
        predictor_values: np.ndarray,
        data_to_extrapolate: np.ndarray,
    ) -> np.ndarray:
        max_level = np.max(data_to_extrapolate)
        sat_level_guess = 2.0 * max_level

        c_x1_guess = 1
        b_x1_guess = 1

        c_x2_guess = 1
        b_x2_guess = 1

        return np.array([sat_level_guess, b_x1_guess, c_x1_guess, b_x2_guess, c_x2_guess])
