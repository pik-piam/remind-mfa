import flodym as fd
import numpy as np
from typing import Tuple, Union, Optional
from pydantic import ConfigDict

from remind_mfa.common.data_transformations import broadcast_trailing_dimensions, BoundList
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.helpers import RegressOverModes, RemindMFABaseModel
from remind_mfa.common.common_config import ModelSwitches
from remind_mfa.common.fit_stocks import StockFitter


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
    additional_stock_data_weight: Optional[float] = 0.0
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
    transition_smoothing: str = "critically_damped"
    """transition_smoothing (str): Method for blending between historical and future stock. Possible values are "critically_damped", "shift_zeroth_order", "none". Defaults to "critically_damped"."""

    def extrapolate(self):
        """Preprocessing and extrapolation."""
        self.set_dims(self.indep_fit_dim_letters)
        self.init_arrays()
        self.calc_arrays_from_parameters_dict()
        self.set_predictor()
        self.get_pure_regression()
        self.fit()
        self.smooth_transition()
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
        """Initialize arrays for helpers and stocks in different versions:
        Only the historic part, per capita, and so on
        """
        self.historic_pop = fd.Parameter(dims=self.dims[("h", "r")])
        self.historic_gdppc = fd.Parameter(dims=self.dims[("h", "r")])
        self.historic_stocks_pc = fd.StockArray(dims=self.dims[self.historic_dim_letters])
        if self.additional_stock_data is not None:
            self.additional_stock_data_pc = fd.StockArray(dims=self.dims_out)
        self.stocks_pc = fd.StockArray(dims=self.dims_out)
        self.stocks = fd.StockArray(dims=self.dims_out)

    def calc_arrays_from_parameters_dict(self):
        """Calc drivers (GDP and population) and various variations of it"""
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

    def set_predictor(self):
        """wrapper for the get_predictor function using class attributes.
        get_predictor is designed to be called with other gdp values, e.g. for visualization
        """
        self.predictor = self.get_predictor(self.gdppc.values)

    def get_predictor(self, gdppc: np.ndarray) -> np.ndarray:
        """Get regression predictor: Can be either log GDP per capita or a combination of log GDP per capita and time.
        In all cases, the predictor is standardized to have a mean of 0 and a range of approximately 1.

        Args:
            gdppc (np.ndarray): GDP per capita values to use; having this as an input allows to use
              different GDP per capita values for visualization of the regression predictor, for example.

        Returns:
            np.ndarray: The predictor values for the regression
        """
        # Standardize time and GDPpc:
        # The mean is data-driven and therefore dependent on the predictor, but also unit-independent.
        # Nevertheless, this should not have an impact on the regression result, as it only shifts the values.
        # The range is hardcoded in units of years/$, which makes it independent of the predictor data.
        # This is necessary to ensure comparable regression results on different predictor data.
        # If other units are used, the range needs to be adapted accordingly.
        time = np.array(self.dims["t"].items)
        normalized_time = (time - np.mean(time)) / (2100 - 1900)
        log_gdppc = np.log10(gdppc)
        normalized_gdppc = (log_gdppc - np.log10(1e4)) / (np.mean(log_gdppc) - np.log10(1e3))

        match self.cfg.regress_over:
            case RegressOverModes.LOGGDPPC:
                return normalized_gdppc
            case RegressOverModes.LOGGDPPC_TIME:
                time = broadcast_trailing_dimensions(normalized_time, normalized_gdppc)
                predictor = np.empty(gdppc.shape, dtype=[("x1", np.float64), ("x2", np.float64)])
                predictor["x1"] = normalized_gdppc
                predictor["x2"] = time
                return predictor

    def get_pure_regression(self):
        """Regress over the chosen predictor, common for all regions.
        The extrapolation object contains the pure regression result without any correction or
        fitting to the historic stocks.
        """
        all_weights = (self.gdppc * self.pop).get_shares_over(("r",))
        historic_weights = all_weights[{"t": self.dims["h"]}]
        if self.additional_stock_data is None:
            data_to_extrapolate = self.historic_stocks_pc.values
            predictor_values = self.predictor
            weights = historic_weights.values
        else:
            # we prepend the common regression as additional "historic" data with lower weighting
            historic_in = self.historic_stocks_pc.values
            additional = self.additional_stock_data_pc.values
            data_to_extrapolate = np.concatenate([additional, historic_in], axis=0)
            weights = np.concatenate(
                [
                    all_weights.values * self.additional_stock_data_weight,
                    historic_weights.values,
                ],
                axis=0,
            )
            predictor_values = np.concatenate(
                [self.predictor, self.predictor],
                axis=0,
            )
        self.extrapolation = self.cfg.stock_extrapolation_class(
            data_to_extrapolate=data_to_extrapolate,
            predictor_values=predictor_values,
            independent_dims=self.fit_dim_idx,
            bound_list=self.bound_list,
            weights=weights,
        )
        pure_regression = self.extrapolation.regress()
        if self.additional_stock_data is not None:
            # remove prepended additional data
            pure_regression = pure_regression[self.dims_out["t"].len :, ...]

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

    def fit(self):
        """Makes region-specific alterations to the common regression parameters to better fit
        historic stock trends.
        Minimization of a penalty function is used to find a good compromise between fitting the
        historical data and keeping the regression parameters close to the pure regression.
        Details on the penalty function and the optimization can be found in the StockFitter class.
        """

        # TODO add comment
        penalty_weights = {
            "data_0th_order": 20.0,
            "rel_data_0th_order": 20.0,
            "data_1st_order": 10.0,
            "prms": np.array(
                [
                    10.0,  # saturation_level
                    1.0,  # offset
                    1.0,  # growth_rate
                ]
            ),
        }
        stock_fitter = StockFitter(
            historic_stocks_pc=self.historic_stocks_pc,
            extrapolation=self.extrapolation,
            predictor=self.predictor,
            dims_out=self.dims_out,
            penalty_weights=penalty_weights,
            good_dimletter=self.target_dim_letters[-1], # TODO make this selection clearer
        )
        self.fitted_regression = stock_fitter.fit()

    def smooth_transition(self):
        """The fit function returns a regression which only approximately continues historic trends.
        Here we create a smooth transition between the historic stocks and the fitted regression,
        which is then used as the final extrapolation result.
        """
        stocks_pc_out = np.zeros_like(self.stocks_pc.values)

        match self.transition_smoothing:
            case "none":
                stocks_pc_out[...] = self.fitted_regression.values
            case "critically_damped":
                stocks_pc_out[...] = self.critically_damped_blend(
                    self.historic_stocks_pc.values, self.fitted_regression.values
                )
                add_assumption_doc(
                    type="model assumption",
                    name="Usage of critically damped blend",
                    description=(
                        "Critically damped blending is used to smoothly transition from historic trends to the extrapolation."
                    ),
                )
            case "shift_zeroth_order":
                # match last point by adding the difference between the last historic point and the
                # corresponding prediction
                stocks_pc_out[...] = self.fitted_regression.values - (
                    self.fitted_regression.values[self.n_historic - 1, :]
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
                raise ValueError(f"Unknown stock_correction method: {self.smooth_transition}")

        stocks_pc_out[: self.n_historic, ...] = self.historic_stocks_pc.values
        self.stocks_pc.set_values(stocks_pc_out)

    def critically_damped_blend(
        self, historical: np.ndarray, prediction: np.ndarray
    ) -> np.ndarray:
        """
        Blend historical and extrapolated stock values using a critically damped system approach to ensure a smooth transition.
        In a critically damped system (e.g. spring that returns to equilibrium as quickly as possible without oscillating),
        if x0 is the initial position and v0 the initial velocity, the position x at a time t is given by:
        x(t) = (x0 + (v0 + k * x0) * t) * exp(-k * t).
        The parameter k determines how quickly the equilibrium is restored, with higher values leading to a faster transition.
        Here, we use the difference between historical and extrapolated stocks at the transition point as the initial offset (x0),
        and the difference in slopes at the transition point as the initial velocity (v0).
        Args:
            historical (np.ndarray): Historical stock data.
            prediction (np.ndarray): Extrapolated stock data from regression.
        Returns:
            np.ndarray: Stock with smooth transition from historical to prediction.
        """
        time = np.array(self.dims["t"].items)
        last_history_idx = len(historical) - 1
        last_history_year = time[last_history_idx]

        # offset between historic and prediction at transition point
        difference_0th = historical[last_history_idx, :] - prediction[last_history_idx, :]

        def avg_slope(x, y, n=1):
            """Assuming time is the first dimension, calculate the average slope over the last n historical timesteps.
            If n is 1, this is the slope between the last two historical timesteps."""
            ydiff = y[last_history_idx, :] - y[last_history_idx - n, :]
            xdiff = x[last_history_idx] - time[last_history_idx - n]
            return ydiff / xdiff

        # offset of the 1st derivative at the transition point
        difference_1st = avg_slope(time, historical) - avg_slope(time, prediction)

        approaching_time = 80
        add_assumption_doc(
            type="integer number",
            name="years for blending to regression",
            value=approaching_time,
            description=(
                "Number of years for the blending from historical to regressed in-use stocks." \
                "After this time, the initial offset between historical and regressed stock is reduced to 5 percent." \
            ),
        )
        
        # Construct time that starts at 0 in last historical year.
        time_extended = time.reshape(-1, *([1] * len(difference_0th.shape)))
        delta_t = time_extended - last_history_year
        
        # Amplitude decreases to 5 percent after approaching_time years
        k = 4.74 / approaching_time 

        # Critically damped system solution
        correction = (difference_0th + (difference_1st + k * difference_0th) * delta_t) * np.exp(-k * delta_t)

        return prediction[...] + correction

    @property
    def dims_out(self):
        return self.dims[self.target_dim_letters]

    @property
    def n_historic(self):
        return self.dims["h"].len
