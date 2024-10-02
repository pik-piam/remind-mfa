from abc import abstractmethod
import numpy as np
from pydantic import BaseModel, ConfigDict
from typing import Union
from scipy.optimize import least_squares


class Extrapolation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    data_to_extrapolate: np.ndarray  # historical data, 1 dimensional (time)
    extrapolate_from: Union[np.ndarray, list[np.ndarray]]  # predictor variable(s)

    @property
    def n_historic(self):
        return self.data_to_extrapolate.shape[0]

    @abstractmethod
    def predict(self):
        pass


class SigmoidalExtrapolation(Extrapolation):

    def initial_guess(self):
        return np.array([2.*self.extrapolate_from[self.n_historic-1], self.data_to_extrapolate[-1]])

    def fitting_function(self, prms):
        return (
            prms[0] / (1. + np.exp(prms[1]/self.extrapolate_from[:self.n_historic]))
        ) - self.data_to_extrapolate

    def predict(self):
        prms_out = least_squares(self.fitting_function, x0=self.initial_guess(), gtol=1.e-12)
        prediction = prms_out.x[0] / (1. + np.exp(prms_out.x[1] / self.extrapolate_from))
        return prediction


class ExponentialExtrapolation(Extrapolation):
    initial_guess: np.ndarray = np.array([400, 1])  # these values work well for stock predictions
    # in the steel model, but should be passed on initialisation for other usecases.

    def fitting_function(self, prms):
        return (
            prms[0] * (1 - np.exp(-prms[1]*self.extrapolate_from[:self.n_historic]))
        ) - self.data_to_extrapolate

    def predict(self):
        prms_out = least_squares(self.fitting_function, x0=self.initial_guess, gtol=1.e-12)
        prediction = (prms_out.x[0] * (1 - np.exp(-prms_out.x[1] * self.extrapolate_from)))
        return prediction
