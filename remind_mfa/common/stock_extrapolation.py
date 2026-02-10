import flodym as fd
import numpy as np
from typing import Tuple, Union, Optional
from pydantic import ConfigDict
from copy import deepcopy

from remind_mfa.common.data_transformations import broadcast_trailing_dimensions, BoundList
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.helpers import RegressOverModes, RemindMFABaseModel
from remind_mfa.common.common_config import ModelSwitches


class StockExtrapolation(RemindMFABaseModel):
    """
    Class for extrapolating stocks based on historical data and GDP per capita.
    """
    model_config = ConfigDict(extra="allow")

    cfg: ModelSwitches
    """Configuration for the model."""
    historic_stocks: fd.FlodymArray
    """Historical stock data."""
    additional_stock_data: Optional[fd.FlodymArray] = None
    """additional data used for the extrapolation, like an expert guess"""
    additional_stock_data_weight: Optional[float] = 0.
    """relative weight of the additional stock data in the regression.
    only used if additional_stock_data is not None.
    """
    dims: fd.DimensionSet
    """Dimension set for the data."""
    parameters: dict[str, fd.Parameter]
    """Parameters for the extrapolation."""
    target_dim_letters: Union[Tuple[str, ...], str] = "all"
    """Sets the dimensions of the stock extrapolation output. If "all", the output will have the same shape as historic_stocks, except for the time dimension. Defaults to "all"."""
    indep_fit_dim_letters: Union[Tuple[str, ...], str] = ()
    """indep_fit_dim_letters (Union[Tuple[str, ...]], str): Sets the dimensions across which an individual fit is performed, must be subset of target_dim_letters. If "all", all dimensions given in target_dim_letters are regressed individually. If empty (), all dimensions are regressed aggregately. Defaults to ()."""
    bound_list: BoundList = BoundList()
    """bound_list (BoundList): List of bounds for the extrapolation. Defaults to an empty BoundList."""
    do_gdppc_accumulation: bool = True
    """do_gdppc_accumulation (bool): Flag to perform GDP per capita accumulation. Defaults to True."""
    gdp_weight_in_weighted_sum: Optional[float] = None
    """relative weight of gdp in predictor weighted sum for predictor type LOGGDPPC_TIME_WEIGHTED_SUM"""
    stock_correction: str = "gaussian_first_order"
    """stock_correction (str): Method for stock correction. Possible values are "gaussian_first_order", "shift_zeroth_order", "none". Defaults to "gaussian_first_order"."""
    n_deriv: int = 5
    """Number of historic years used for determination of regressed and actual growth rates of
    in-use stocks, which are then used for a correction reconciling the two and blending from
    observed to regression.
    """

    def extrapolate(self):
        """Preprocessing and extrapolation."""
        self.set_dims(self.indep_fit_dim_letters)
        self.init_arrays()
        self.calc_arrays_from_parameters_dict()
        self.set_predictor()
        self.get_pure_regression()
        self.correct_stock()
        # transform back to total stocks
        self.stocks[...] = self.stocks_pc * self.pop
        return self

    def set_dims(self, indep_fit_dim_letters: Tuple[str, ...]):
        """
        Check target_dim_letters.
        Set fit_dim_letters and check:
        fit_dim_letters should be the same as target_dim_letters, but without the time dimension, except if otherwise defined.
        In this case, fit_dim_letters should be a subset of target_dim_letters.
        This check cannot be performed if self.target_dim_letters or self.fit_dim_letters is None.
        """
        if self.target_dim_letters == "all":
            self.historic_dim_letters = self.historic_stocks.dims.letters
            self.target_dim_letters = ("t",) + self.historic_dim_letters[1:]
        else:
            self.historic_dim_letters = ("h",) + self.target_dim_letters[1:]

        if indep_fit_dim_letters == "all":
            # fit_dim_letters should be the same as target_dim_letters, but without the time dimension
            self.indep_fit_dim_letters = tuple(x for x in self.target_dim_letters if x != "t")
        else:
            self.indep_fit_dim_letters = indep_fit_dim_letters
            if not set(self.indep_fit_dim_letters).issubset(self.target_dim_letters):
                raise ValueError("fit_dim_letters must be subset of target_dim_letters.")
        self.get_fit_idx()

    def get_fit_idx(self):
        """Get the indices of the fit dimensions in the historic_stocks dimensions."""
        self.fit_dim_idx = tuple(
            i
            for i, x in enumerate(self.historic_stocks.dims.letters)
            if x in self.indep_fit_dim_letters
        )

    def init_arrays(self):
        self.historic_pop = fd.Parameter(dims=self.dims[("h", "r")])
        self.historic_gdppc = fd.Parameter(dims=self.dims[("h", "r")])
        self.historic_stocks_pc = fd.StockArray(dims=self.dims[self.historic_dim_letters])
        if self.additional_stock_data is not None:
            self.additional_stock_data_pc = fd.StockArray(dims=self.dims_out)
        self.stocks_pc = fd.StockArray(dims=self.dims_out)
        self.stocks = fd.StockArray(dims=self.dims_out)

    def calc_arrays_from_parameters_dict(self):
        self.pop = self.parameters["population"]
        self.gdppc = self.parameters["gdppc"]
        self.adapt_gdppc()
        self.historic_pop[...] = self.pop[{"t": self.dims["h"]}]
        self.historic_gdppc[...] = self.gdppc[{"t": self.dims["h"]}]
        self.historic_stocks_pc[...] = self.historic_stocks / self.historic_pop
        if self.additional_stock_data is not None:
            self.additional_stock_data_pc[...] = self.additional_stock_data / self.pop

    def adapt_gdppc(self):
        if self.do_gdppc_accumulation:
            add_assumption_doc(
                type="model assumption",
                name="Usage of cumulative GDP per capita",
                description=(
                    "Accumulated GDPpc is used for stock extrapolation to prevent "
                    "stock shrink in times of decreasing GDPpc. "
                ),
            )
            self.gdppc = self.gdppc.apply(np.maximum.accumulate, kwargs=dict(axis=0))
        self.gdppc = self.gdppc.cast_to(self.dims_out)

        add_assumption_doc(
            name="synthetic recent GDP for regression correction",
            type="ad-hoc fix",
            description=(
                "GDP per capita SSP curves assume a steady growth after 2025, which in some "
                "regions breaks historic trends. Here, we overwrite recent historic GDP per capita "
                "by extrapolating back from 2025 using the growth rates after 2025. "
                "This creates continuity between the recent historic GDP growth used for the "
                "gaussian correction and the future assumed growth rates and thereby prevents "
                "discontinuities in production."
            ),
        )
        growth = self.gdppc[2026] / self.gdppc[2027]
        for i in range(self.n_deriv + 5):
            self.gdppc[2025 - i] = self.gdppc[2025 - i + 1] * growth

    def set_predictor(self):
        self.predictor = self.get_predictor(self.gdppc.values, self.gdp_weight_in_weighted_sum)

    def get_predictor(self, gdppc: np.ndarray, gdp_weight_in_weighted_sum: Optional[float] = None):
        match self.cfg.regress_over:
            case RegressOverModes.GDPPC:
                return gdppc
            case RegressOverModes.LOGGDPPC:
                return np.log10(gdppc)
            case RegressOverModes.LOCGDPPC_TIME_WEIGHTED_SUM:
                time = np.array(self.dims["t"].items)
                return np.log10(gdppc) * gdp_weight_in_weighted_sum + time[:, None, None]
            case RegressOverModes.LOGGDPPC_TIME:
                time = np.array(self.dims["t"].items)
                time = broadcast_trailing_dimensions(time, gdppc)
                predictor = np.empty(gdppc.shape, dtype=[("x1", np.float64), ("x2", np.float64)])
                predictor["x1"] = np.log10(gdppc)
                predictor["x2"] = time
                return predictor

    def get_pure_regression(self):
        """Updates per capita stock to future by extrapolation."""
        if self.additional_stock_data is None:
            data_to_extrapolate = self.historic_stocks_pc.values
            predictor_values = self.predictor
            weights = None
        else:
            # we prepend the common regression as additional "historic" data with lower weighting
            historic_in = self.historic_stocks_pc.values
            additional = self.additional_stock_data_pc.values
            data_to_extrapolate = np.concatenate([additional, historic_in], axis=0)
            weights = np.concatenate(
                [
                    np.ones_like(additional) * self.additional_stock_data_weight,
                    np.ones_like(historic_in),
                ],
                axis=0,
            )
            predictor_values = np.concatenate(
                [
                    self.predictor,
                    self.predictor
                ],
                axis=0,
            )
        self.extrapolation = self.cfg.stock_extrapolation_class(
            data_to_extrapolate=data_to_extrapolate,
            predictor_values=predictor_values,
            independent_dims=self.fit_dim_idx,
            bound_list=self.bound_list,
            weights=weights
        )
        pure_regression = self.extrapolation.regress()
        if self.additional_stock_data is not None:
            # remove prepended additional data
            pure_regression = pure_regression[self.dims_out["t"].len:, ...]

        self.pure_regression = fd.FlodymArray(dims=self.stocks_pc.dims, values=pure_regression)
        self.export_pure_parameters()

    def export_pure_parameters(self):
        """for export to csv, used in plastics
        TODO: check if still needed
        """
        if self.indep_fit_dim_letters:
            parameter_dims: fd.DimensionSet = self.dims[self.indep_fit_dim_letters]
        else:
            parameter_dims = fd.DimensionSet(dim_list=[])
        parameter_names = fd.Dimension(
            name="Parameter Names", letter="p", items=self.extrapolation.prm_names
        )
        parameter_dims = parameter_dims.expand_by([parameter_names])
        self.pure_parameters = fd.FlodymArray(
            dims=parameter_dims, values=self.extrapolation._fit_prms
        )

    def correct_stock(self):
        stocks_pc_out = np.zeros_like(self.stocks_pc.values)

        match self.stock_correction:
            case "none":
                stocks_pc_out[...] = self.pure_regression.values
            case "gaussian_first_order":
                stocks_pc_out[...] = self.gaussian_correction(
                    self.historic_stocks_pc.values,
                    self.pure_regression.values,
                    self.n_deriv
                )
                add_assumption_doc(
                    type="model assumption",
                    name="Usage of Gaussian correction",
                    description=(
                        "Gaussian correction is used to blend historic trends with the extrapolation."
                    ),
                )
            case "shift_zeroth_order":
                # match last point by adding the difference between the last historic point and the
                # corresponding prediction
                stocks_pc_out[...] = self.pure_regression.values - (
                    self.pure_regression.values[self.n_historic - 1, :]
                    - self.historic_stocks_pc.values[self.n_historic - 1, :]
                )
                add_assumption_doc(
                    type="model assumption",
                    name="Usage of zeroth order correction",
                    description=(
                        "Zeroth order correction is used to match the last historic point with the "
                        "extrapolated stock."
                    ),
                )
            case _:
                raise ValueError(f"Unknown stock_correction method: {self.stock_correction}")

        stocks_pc_out[:self.n_historic, ...] = self.historic_stocks_pc.values
        self.stocks_pc.set_values(stocks_pc_out)

    def gaussian_correction(
        self, historic: np.ndarray, prediction: np.ndarray, n: int = 5
    ) -> np.ndarray:
        """
        Gaussian smoothing of extrapolation between the historic and future interface to remove discontinuities
        of 0th and 1st order derivatives. Multiplies Gaussian with a Taylor expansion around
        the difference beteween historic and fit.
        Args:
            historic (np.ndarray): Historical stock data.
            prediction (np.ndarray): Predicted stock data from regression.
            n (int): Number of years for the linear regression fit. Defaults to 5.
        Returns:
            np.ndarray: Corrected stock data after applying Gaussian smoothing.
        """
        time = np.array(self.dims["t"].items)
        last_history_idx = len(historic) - 1
        last_history_year = time[last_history_idx]
        # offset between historic and prediction at transition point
        difference_0th = historic[last_history_idx, :] - prediction[last_history_idx, :]

        def lin_fit(x, y, last_idx, n=n):
            """Linear fit of the last n points."""
            x_cut = np.vstack([x[last_idx - n : last_idx], np.ones(n)]).T
            y_cut = y[last_idx - n : last_idx, :]
            y_reshaped = y_cut.reshape(n, -1).T
            slopes = [np.linalg.lstsq(x_cut, y_dim, rcond=None)[0][0] for y_dim in y_reshaped]
            slopes_reshaped = np.array(slopes).reshape(y.shape[1:])
            return slopes_reshaped

        last_historic_1st = lin_fit(time, historic, last_history_idx)
        last_prediction_1st = lin_fit(time, prediction, last_history_idx)

        # offset of the 1st derivative at the transition point
        difference_1st = (last_historic_1st - last_prediction_1st) / (
            last_history_year - time[last_history_idx - 1]
        )

        def gaussian(t, approaching_time):
            """After the approaching time, the amplitude of the gaussian has decreased to 5%."""
            a = np.sqrt(np.log(20))
            return np.exp(-((a * t / approaching_time) ** 2))

        approaching_time_0th = 50
        add_assumption_doc(
            type="integer number",
            name="years for absolute blending to regression",
            value=approaching_time_0th,
            description=(
                "Number of years for the blending from historical to regressed in-use stocks. "
            ),
        )
        approaching_time_1st = 30
        add_assumption_doc(
            type="integer number",
            name="years for derivative blending to regression",
            value=approaching_time_1st,
            description=(
                "Number of years for the blending from historical to regressed in-use stock "
                "growth rates. "
            ),
        )
        time_extended = time.reshape(-1, *([1] * len(difference_0th.shape)))
        corr0 = difference_0th * gaussian(time_extended - last_history_year, approaching_time_0th)
        corr1 = (
            difference_1st
            * (time_extended - last_history_year)
            * gaussian(time_extended - last_history_year, approaching_time_1st)
        )
        correction = corr0 + corr1

        return prediction[...] + correction

    @property
    def dims_out(self):
        return self.dims[self.target_dim_letters]

    @property
    def n_historic(self):
        return self.dims["h"].len
