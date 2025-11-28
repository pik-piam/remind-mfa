from abc import abstractmethod
from typing import Optional, Tuple
import numpy as np
import sys
from pydantic import model_validator
from scipy.optimize import least_squares
from pydantic import PrivateAttr

from remind_mfa.common.helper import RemindMFABaseModel
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
    prm_names: list[str] = []
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
        regression = np.zeros_like(self.predictor_values)
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
        outside_bounds = (initial_guess < bounds[0]) + (initial_guess > bounds[1])
        if np.any(outside_bounds):
            initial_guess[outside_bounds] = (
                bounds[0][outside_bounds] + bounds[1][outside_bounds]
            ) / 2
        fit_prms = least_squares(fitting_function, x0=initial_guess, gtol=1.0e-12, bounds=bounds).x
        regression = self.func(predictor, fit_prms)
        return fit_prms, regression


class ProportionalExtrapolation(Extrapolation):

    prm_names: list[str] = ["proportionality_factor"]

    @staticmethod
    def func(x, prms):
        return prms[0] * x

    def initial_guess(self, predictor_values, data_to_extrapolate):
        return np.array([1.0])


class PehlExtrapolation(Extrapolation):

    prm_names: list[str] = ["saturation_level", "stretch_factor"]

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

    prm_names: list[str] = ["saturation_level", "stretch_factor"]

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


class SigmoidExtrapolation(Extrapolation):

    prm_names: list[str] = ["saturation_level", "stretch_factor", "x_offset"]

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


class LogSigmoidExtrapolation(SigmoidExtrapolation):
    """
    LogSigmoidExtrapolation is a specific implementation of SigmoidExtrapolation that uses a logarithmic transformation
    for the predictor values.
    """

    @staticmethod
    def func(x, prms):
        return SigmoidExtrapolation.func(np.log10(x), prms)

    def initial_guess(self, predictor_values, data_to_extrapolate):
        return super().initial_guess(np.log10(predictor_values), data_to_extrapolate)
