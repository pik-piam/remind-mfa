import flodym as fd
import numpy as np
from scipy.optimize import minimize
from pydantic import model_validator

from remind_mfa.common.helpers import RemindMFABaseModel
from remind_mfa.common.data_extrapolations import Extrapolation


class StockFitter(RemindMFABaseModel):
    historic_stocks_pc: fd.FlodymArray  # pC
    extrapolation: Extrapolation
    dims_out: fd.DimensionSet
    penalty_weights: dict
    predictor: np.ndarray
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
            raise ValueError("The regression array must have the same 'r' and goods dimensions as historic_in.")
        return self

    @model_validator(mode="after")
    def check_prms(self):
        e = self.extrapolation
        # TODO: adapt for logistic; also get common normalization
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
        hdims = self.historic_stocks_pc.dims
        prms = np.ndarray(
            shape=(
                hdims["r"].len,
                hdims[self.goods_dim_letter].len,
                self.extrapolation.n_prms
                )
            )
        self._n_hist = hdims["h"].len
        # normalize by saturation level to make absolute values and gradients more comparable across goods
        fit_prms = self.extrapolation.fit_prms
        sat_level = fd.FlodymArray(dims=hdims["g",], values=fit_prms[...,0].copy())
        historic = (self.historic_stocks_pc / sat_level).values
        fit_prms[...,0] = 1.
        for ig in range(hdims[self.goods_dim_letter].len):
            for ir in range(hdims["r"].len):
                prms[ir, ig, :] = self.fit_single(
                    historic=historic[:, ir, ig],
                    predictor=self.predictor[:,ir,ig],
                    prms_0=fit_prms[ig, :]
                    )
        values_out = self.extrapolation.func(self.predictor[np.newaxis,...], np.moveaxis(prms[np.newaxis,...], -1, 0))
        stocks_pc_out = fd.FlodymArray(dims=self.dims_out, values=values_out[0, ...]) * sat_level
        return stocks_pc_out

    def fit_single(self, historic, predictor, prms_0):
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

    def penalty(self, historic, predictor, prms, prms_0):
        return (
            self.pen_data_0th_order(historic, predictor, prms)
            + self.pen_data_1st_order(historic, predictor, prms)
            + self.pen_common(prms, prms_0)
        )

    def jacobian(self, historic, predictor, prms, prms_0):
        return (
            self.dpen_data_0th_order(historic, predictor, prms)
            + self.dpen_data_1st_order(historic, predictor, prms)
            + self.dpen_common(prms, prms_0)
        )

    def pen_data_0th_order(self, historic, predictor, prms):
        last_x = self.last_hist(predictor)
        fit = self.extrapolation.func(last_x, prms)
        target = self.last_hist(historic)
        return self.norm((fit - target)) * self.penalty_weights["data_0th_order"]

    def pen_data_1st_order(self, historic, predictor, prms):
        fit_slope = self.first_future_slope(predictor, lambda x: self.extrapolation.func(x, prms))
        target_slope = self.last_hist_slope(historic)
        return self.norm((fit_slope - target_slope)) * self.penalty_weights["data_1st_order"]

    def dpen_data_1st_order(self, historic, predictor, prms):
        fit_slope = self.first_future_slope(predictor, lambda x: self.extrapolation.func(x, prms))
        dfit_slope = self.first_future_slope(predictor, lambda x: self.extrapolation.jacobian(x, prms))
        target_slope = self.last_hist_slope(historic)
        return self.dnorm((fit_slope - target_slope)) * self.penalty_weights["data_1st_order"] * dfit_slope

    def dpen_data_0th_order(self, historic, predictor, prms):
        last_x = self.last_hist(predictor)
        fit = self.extrapolation.func(last_x, prms)
        dfit = self.extrapolation.jacobian(last_x, prms)
        target = self.last_hist(historic)
        return self.dnorm((fit - target)) * self.penalty_weights["data_0th_order"] * dfit

    def pen_common(self, prms, prms_0):
        return np.sum(self.norm(prms - prms_0) * self.penalty_weights["prms"])

    def dpen_common(self, prms, prms_0):
        return self.dnorm(prms - prms_0) * self.penalty_weights["prms"]

    @staticmethod
    def norm(x):
        return x**2 #+ np.abs(x)

    @staticmethod
    def dnorm(x):
        return 2*x #+ np.sign(x)

    def last_hist(self,arr):
        # TODO: refine
        return arr[self._n_hist - 1]

    def last_hist_slope(self, arr):
        n = 10
        return (arr[self._n_hist - 1] - arr[self._n_hist - 1 - n]) / (n/20)

    def first_future_slope(self, arr, func):
        n = 10
        return (func(arr[self._n_hist + n - 1]) - func(arr[self._n_hist - 1])) / (n/20)