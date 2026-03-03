import flodym as fd
import numpy as np
from scipy.optimize import minimize
from pydantic import model_validator
from typing import ClassVar

from remind_mfa.common.helpers import RemindMFABaseModel
from remind_mfa.common.data_extrapolations import Extrapolation


class StockFitter(RemindMFABaseModel):
    historic_stocks_pc: fd.FlodymArray
    extrapolation: Extrapolation
    dims_out: fd.DimensionSet
    penalty_weights: dict
    predictor: np.ndarray
    good_dimletter: str
    _n_hist: int = None

    @model_validator(mode="after")
    def check_dims(self):
        if self.historic_stocks_pc.dims.letters[0] != "h":
            raise ValueError("The first dimension of historic_in must be 'h'.")
        if self.historic_stocks_pc.dims.letters[1] != "r":
            raise ValueError("The second dimension of historic_in must be 'r'.")
        if self.historic_stocks_pc.dims.ndim != 3:
            raise ValueError("The historic_in array must have exactly 3 dimensions.")

        if self.dims_out.letters[0] != "t":
            raise ValueError("The first dimension of regression must be 't'.")
        if self.dims_out.letters[1:] != self.historic_stocks_pc.dims.letters[1:]:
            raise ValueError(
                "The regression array must have the same 'r' and goods dimensions as historic_in."
            )
        return self

    @model_validator(mode="after")
    def check_prms(self):
        e = self.extrapolation
        # TODO: adapt for logistic; also get common normalization
        # harmonize parameter names and find comparable way of measurement
        if e.prm_names[0] != "saturation_level":
            raise ValueError("saturation_level not in prm_names.")
        if e.prm_names[1] != "offset":
            raise ValueError("offset not in prm_names.")
        if e.prm_names[2] != "growth_rate":
            raise ValueError("growth_rate not in prm_names.")
        return self

    @property
    def goods_dim_letter(self):
        return self.historic_stocks_pc.dims.letters[2]

    def fit(self):
        """prepare parameters for single fitting function
        loop over good and regions, call single fitting function for each of them
        """
        hdims = self.historic_stocks_pc.dims
        prms = np.ndarray(
            shape=(hdims["r"].len, hdims[self.goods_dim_letter].len, self.extrapolation.n_prms)
        )
        self._n_hist = hdims["h"].len
        for ig in range(hdims[self.goods_dim_letter].len):
            for ir in range(hdims["r"].len):
                prms[ir, ig, :] = self.fit_single(
                    historic=self.historic_stocks_pc.values[:, ir, ig],
                    predictor=self.predictor[:, ir, ig],
                    prms_0=self.extrapolation.fit_prms[ig, :],
                )
        values_out = self.extrapolation.func(
            self.predictor[np.newaxis, ...], np.moveaxis(prms[np.newaxis, ...], -1, 0)
        )

        stocks_pc_out = fd.FlodymArray(dims=self.dims_out, values=values_out[0, ...])
        return stocks_pc_out

    def fit_single(
        self, historic: np.ndarray, predictor: np.ndarray, prms_0: np.ndarray
    ) -> np.ndarray:
        """Carry out the fitting for a single good and region by minimizing the penalty function.
        Wraps/uses scipy's minimize function.
        Passes a transformed penalty function and its jacobian to scipy, which only depend on prms.

        Args:
            historic (np.ndarray): historic data
            predictor (np.ndarray): predictor, usually log(GDPpC)
            prms_0 (np.ndarray): initial guess for the parameters

        Returns:
            np.ndarray: fitted parameters fot that good and region
        """
        result = minimize(
            fun=lambda prms: self.penalty(historic, predictor, prms, prms_0),
            jac=lambda prms: self.jacobian(historic, predictor, prms, prms_0),
            x0=prms_0,
            tol=0.001,
        )
        if result.success:
            return result.x
        else:
            raise RuntimeError(f"Optimization failed: {result.message}")

    def penalty(
        self, historic: np.ndarray, predictor: np.ndarray, prms: np.ndarray, prms_0: np.ndarray
    ) -> np.ndarray:
        """Absolute penalty function to be minimized in the fitting process.

        Args:
            historic (np.ndarray): historic data
            predictor (np.ndarray): predictor, usually log(GDPpC)
            prms (np.ndarray): parameters for which the penalty is calculated, will be updated
              iteratively by scipy's optimization algorithm
            prms_0 (np.ndarray): initial guess for the parameters, used in the penalty to avoid
              unreasonably large deviations from the initial guess

        Returns:
            np.ndarray: penalty value for the given parameters, to be minimized in the fitting process
        """
        return (
            self.pen_data_0th_order(historic, predictor, prms)
            + self.pen_data_1st_order(historic, predictor, prms)
            + self.pen_common(prms, prms_0)
        )

    def jacobian(
        self: np.ndarray,
        historic: np.ndarray,
        predictor: np.ndarray,
        prms: np.ndarray,
        prms_0: np.ndarray,
    ) -> np.ndarray:
        """Derivative of the penalty function with respect to the parameters,
        used to helps scipy's optimization algorithm.

        Args:
            historic (np.ndarray): historic data
            predictor (np.ndarray): predictor, usually log(GDPpC)
            prms (np.ndarray): parameters for which the penalty is calculated, will be updated
              iteratively by scipy's optimization algorithm
            prms_0 (np.ndarray): initial guess for the parameters, used in the penalty to avoid
              unreasonably large deviations from the initial guess

        Returns:
            np.ndarray: penalty value for the given parameters, to be minimized in the fitting process
        """
        return (
            self.dpen_data_0th_order(historic, predictor, prms)
            + self.dpen_data_1st_order(historic, predictor, prms)
            + self.dpen_common(prms, prms_0)
        )

    def pen_data_0th_order(self, historic, predictor, prms):
        """penalty for the absolute deviation of the fitted function from the last historic data
        points
        """
        last_x = self.last_hist(predictor)
        fit = self.extrapolation.func(last_x, prms)
        target = self.last_hist(historic)
        return self.norm((fit - target)) * self.penalty_weights["data_0th_order"]

    def pen_data_1st_order(self, historic, predictor, prms):
        """penalty for the deviation of the slope of the fitted function from the slope of the
        historic data in the last historic data points
        """
        fit_slope = self.first_future_slope(predictor, lambda x: self.extrapolation.func(x, prms))
        target_slope = self.last_hist_slope(historic)
        return self.norm((fit_slope - target_slope)) * self.penalty_weights["data_1st_order"]

    def dpen_data_1st_order(self, historic, predictor, prms):
        """derivative of pen_data_1st_order with respect to prms"""
        fit_slope = self.first_future_slope(predictor, lambda x: self.extrapolation.func(x, prms))
        dfit_slope = self.first_future_slope(
            predictor, lambda x: self.extrapolation.jacobian(x, prms)
        )
        target_slope = self.last_hist_slope(historic)
        return (
            self.dnorm((fit_slope - target_slope))
            * self.penalty_weights["data_1st_order"]
            * dfit_slope
        )

    def dpen_data_0th_order(self, historic, predictor, prms):
        """derivative of pen_data_0th_order with respect to prms"""
        last_x = self.last_hist(predictor)
        fit = self.extrapolation.func(last_x, prms)
        dfit = self.extrapolation.jacobian(last_x, prms)
        target = self.last_hist(historic)
        return self.dnorm((fit - target)) * self.penalty_weights["data_0th_order"] * dfit

    def pen_common(self, prms, prms_0):
        return np.sum(self.norm(prms - prms_0) * self.penalty_weights["prms"])

    def dpen_common(self, prms, prms_0):
        """derivative of pen_common with respect to prms"""
        return self.dnorm(prms - prms_0) * self.penalty_weights["prms"]

    @staticmethod
    def norm(x):
        """How the penalty reacts to deviations from target values"""
        return x**2  # + np.abs(x)

    @staticmethod
    def dnorm(x):
        """derivative of norm"""
        return 2 * x  # + np.sign(x)

    def last_hist(self, arr):
        # TODO: refine
        return arr[self._n_hist - 1]

    def last_hist_slope(self, arr):
        # TODO use real years, use propper fit (this would reduce performance)?
        # if we use relative slope optimization, even dividing by n (or years) is not necessary
        n = 3
        return (arr[self._n_hist - 1] - arr[self._n_hist - 1 - n]) / n

    def first_future_slope(self, arr, func):
        # TODO use real years
        n = 3
        return (func(arr[self._n_hist + n - 1]) - func(arr[self._n_hist - 1])) / n
