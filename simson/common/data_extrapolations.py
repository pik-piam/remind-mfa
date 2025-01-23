from abc import abstractmethod
import numpy as np
import sys
from pydantic import BaseModel, ConfigDict, model_validator
from scipy.optimize import least_squares


class Extrapolation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    data_to_extrapolate: np.ndarray  # historical data, 1 dimensional (time)
    target_range: np.ndarray # predictor variable(s)

    @property
    def n_historic(self):
        return self.data_to_extrapolate.shape[0]

    def extrapolate(self, historic_from_regression: bool = False):
        regression = self.regress()
        if not historic_from_regression:
            regression[:self.n_historic] = self.data_to_extrapolate
        return regression

    @abstractmethod
    def regress(self):
        pass


class OneDimensionalExtrapolation(Extrapolation):
    @model_validator(mode="after")
    def validate_data(self):
        assert self.data_to_extrapolate.ndim == 1, "Data to extrapolate must be 1-dimensional."
        assert self.target_range.ndim == 1, "Target range must be 1-dimensional."
        assert self.data_to_extrapolate.shape[0] < self.target_range.shape[0], (
            "data_to_extrapolate must be smaller then target_range")
        return self


class WeightedProportionalExtrapolation(Extrapolation):
    """
    Regression of a function of the form y = a * x, i.e. a linear scaling without offset.
    For regression, the last n_last_points_to_match points are used. Their weights are linearly decreasing to zero.
    """

    @model_validator(mode="after")
    def validate_data(self):
        return self

    n_last_points_to_match: int = 5

    def regress(self):
        """"
        Formula a = sum_i (w_i x_i y_i) / sum_i (w_i x_i^2) is the result of the weighted least squares regression
        a = argmin sum_i (w_i (a * x_i - y_i)^2).
        """
        regression_x = self.target_range[self.n_historic-self.n_last_points_to_match:self.n_historic]
        regression_y = self.data_to_extrapolate[-self.n_last_points_to_match:]
        regression_weights = np.arange(1, self.n_last_points_to_match + 1)
        regression_weights = regression_weights / regression_weights.sum()
        slope = np.sum(regression_x.transpose() * regression_y.transpose() * regression_weights) / np.sum(regression_x.transpose()**2 * regression_weights)
        regression = self.target_range * slope
        return regression


class SigmoidalExtrapolation(OneDimensionalExtrapolation):

    def initial_guess(self):
        return np.array([2.*self.target_range[self.n_historic-1], self.data_to_extrapolate[-1]])

    def fitting_function(self, prms):
        return (
            prms[0] / (1. + np.exp(prms[1]/self.target_range[:self.n_historic]))
        ) - self.data_to_extrapolate

    def regress(self):
        prms_out = least_squares(self.fitting_function, x0=self.initial_guess(), gtol=1.e-12)
        regression = prms_out.x[0] / (1. + np.exp(prms_out.x[1] / self.target_range))
        return regression


class ExponentialExtrapolation(OneDimensionalExtrapolation):

    def initial_guess(self):
        current_level = self.data_to_extrapolate[-1]
        current_extrapolator = self.target_range[self.n_historic - 1]
        initial_saturation_level = 2. * current_level if np.max(np.abs(current_level)) > sys.float_info.epsilon else 1.0
        initial_stretch_factor = - np.log(1 -  current_level / initial_saturation_level) / current_extrapolator

        return np.array([initial_saturation_level, initial_stretch_factor])

    def fitting_function(self, prms):
        return (
            prms[0] * (1 - np.exp(-prms[1]*self.target_range[:self.n_historic]))
        ) - self.data_to_extrapolate

    def regress(self):
        prms_out = least_squares(self.fitting_function, x0=self.initial_guess(), gtol=1.e-12)
        regression = (prms_out.x[0] * (1 - np.exp(-prms_out.x[1] * self.target_range)))

        return regression
