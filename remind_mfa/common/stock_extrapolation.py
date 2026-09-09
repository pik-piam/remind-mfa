import logging
from unittest import case

import flodym as fd
import numpy as np
from remind_mfa.common.data_blending import CriticallyDampedBlender
from typing import Tuple, Union, Optional
from pydantic import ConfigDict

from remind_mfa.common.data_transformations import broadcast_trailing_dimensions, BoundList
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.helpers import RemindMFABaseModel
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
    dims: fd.DimensionSet
    """Dimension set for the data."""
    parameters: dict[str, fd.Parameter]
    """Parameters for the extrapolation."""
    target_dim_letters: Union[Tuple[str, ...], str] = "all"
    """Sets the dimensions of the stock extrapolation output. If "all", the output will have the same shape as historic_stocks, except for the time dimension. Defaults to "all"."""
    end_use_good_letter: str = "g"
    """Letter of the end-use good dimension"""
    bound_list: BoundList = BoundList()
    """bound_list (BoundList): List of bounds for the extrapolation. Defaults to an empty BoundList."""
    do_gdppc_accumulation: bool = True
    """do_gdppc_accumulation (bool): Flag to perform GDP per capita accumulation. Defaults to True."""
    transition_smoothing: str = "critically_damped"
    """transition_smoothing (str): Method for blending between historical and future stock. Possible values are "critically_damped", "shift_zeroth_order", "none". Defaults to "critically_damped"."""
    lifetime: Optional[fd.FlodymArray] = None
    """lifetime of the stock, used to determine the number of timesteps that are used for the average slope calculation in the critically damped blend."""

    def extrapolate(self):
        """Preprocessing and extrapolation."""
        self.set_dims()
        self.calc_arrays_from_parameters_dict()
        self.common_regression()
        self.regional_adaptation()
        # apply stock scenario: scale the extrapolated trajectory before smoothing
        self.fitted_regression[...] = self.fitted_regression * self.parameters["stock_factor"]
        self.smooth_transition()
        # transform back to total stocks
        self.stocks[...] = self.stocks_pc * self.pop
        return self

    def set_dims(self):
        """
        Check target_dim_letters.
        Set fit_dim_letters and check:
        fit_dim_letters should be the same as target_dim_letters, but without the time dimension, except if otherwise defined.
        In this case, fit_dim_letters should be a subset of target_dim_letters.
        This check cannot be performed if self.target_dim_letters or self.fit_dim_letters is None.
        """
        self.historic_dim_letters = self.historic_stocks.dims.letters
        self.target_dim_letters = ("t",) + self.historic_dim_letters[1:]
        self.fit_dim_idx = self.historic_stocks.dims.index(self.end_use_good_letter)

    def calc_arrays_from_parameters_dict(self):
        """Calc drivers (GDP and population) and various variations of it"""
        self.historic_pop = fd.Parameter(dims=self.dims[("h", "r")])
        self.historic_stocks_pc = fd.StockArray(dims=self.dims[self.historic_dim_letters])
        self.stocks_pc = fd.StockArray(dims=self.dims_out)
        self.stocks = fd.StockArray(dims=self.dims_out)

        self.pop = self.parameters["population"]
        self.gdppc = self.parameters["gdppc"]
        self.adapt_gdppc()
        self.historic_pop[...] = self.pop[{"t": self.dims["h"]}]
        self.historic_stocks_pc[...] = self.historic_stocks / self.historic_pop

        self.predictor = self.get_predictor(self.gdppc.values)

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

    def get_predictor(self, gdppc: np.ndarray) -> np.ndarray:
        """Log GDP per capita is standardized to have a mean of 0 and a range of approximately 1.
        Designed to also be called from outside the class, e.g. for visualization.

        Args:
            gdppc (np.ndarray): GDP per capita values to use; having this as an input allows to use
              different GDP per capita values for visualization of the regression predictor, for example.

        Returns:
            np.ndarray: The predictor values for the regression
        """
        # Standardize GDPpc:
        # The mean is data-driven and therefore dependent on the predictor, but also unit-independent.
        # Nevertheless, this should not have an impact on the regression result, as it only shifts the values.
        # The range is hardcoded in units of years/$, which makes it independent of the predictor data.
        # This is necessary to ensure comparable regression results on different predictor data.
        # If other units are used, the range needs to be adapted accordingly.
        log_gdppc = np.log10(gdppc)
        normalized_gdppc = (log_gdppc - np.mean(log_gdppc)) / (np.log10(1e5) - np.log10(1e3))
        return normalized_gdppc

    def common_regression(self):
        """Regress over the chosen predictor, common for all regions.
        The extrapolation object contains the pure regression result without any correction or
        fitting to the historic stocks.
        """
        all_weights = (self.gdppc * self.pop).get_shares_over(("r",))
        historic_weights = all_weights[{"t": self.dims["h"]}]
        data_to_extrapolate = self.historic_stocks_pc.values
        predictor_values = self.predictor
        weights = historic_weights.values
        self.extrapolation = self.cfg.stock_extrapolation_class(
            data_to_extrapolate=data_to_extrapolate,
            predictor_values=predictor_values,
            independent_dims=(self.fit_dim_idx,),
            bound_list=self.bound_list,
            weights=weights,
        )
        self.extrapolation.regress()

    def regional_adaptation(self):
        """Makes region-specific alterations to the common regression parameters to better fit
        historic stock trends.
        Minimization of a penalty function is used to find a good compromise between fitting the
        historical data and keeping the regression parameters close to the pure regression.
        Details on the penalty function and the optimization can be found in the StockFitter class.
        """

        # Note that the weights do not necessarily reflect the importance of different metrics during the optimization.
        # This is due to the fact that different metrics may operate on different regimes and have different units.
        penalty_weights = {
            "data_0th_order": 0.2,
            "rel_data_0th_order": 0.25,
            "data_1st_order": 0.4,
            "prms": np.array(
                [
                    0.4,  # saturation_level
                    0.30,  # offset
                    0.10,  # growth_rate
                ]
            ),
        }
        # order of magnitude of a realistic, but significant change / discrepancy
        order_of_magnitude = {
            "data_0th_order": 0.1,
            "rel_data_0th_order": 0.5,
            "data_1st_order": 0.01,  # TODO
            "prms": np.array(
                [
                    0.2,  # saturation_level
                    0.2,  # offset
                    2.0,  # growth_rate
                ]
            ),
        }
        penalty_weights = {
            k: penalty_weights[k] / StockFitter.norm(order_of_magnitude[k]) for k in penalty_weights
        }
        stock_fitter = StockFitter(
            historic_stocks_pc=self.historic_stocks_pc,
            extrapolation=self.extrapolation,
            predictor=self.predictor,
            dims_out=self.dims_out,
            penalty_weights=penalty_weights,
            current_population=self.pop[{"t": self.dims["h"].items[-1]}],
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
                blender = CriticallyDampedBlender(
                    time=self.dims["t"].items,
                    historical=self.historic_stocks_pc.values,
                    prediction=self.fitted_regression.values,
                    lifetime=self._prepare_lifetime_for_blender(),
                )
                approaching_time = 50
                add_assumption_doc(
                    type="integer number",
                    name="years for blending to regression",
                    value=approaching_time,
                    description=(
                        "Number of years for the blending from historical to regressed in-use stocks. "
                        "Governs the damping parameter k."
                    ),
                )
                stocks_pc_out[...] = blender.blend(approaching_time)
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

    @property
    def dims_out(self):
        return self.dims[self.target_dim_letters]

    @property
    def n_historic(self):
        return self.dims["h"].len

    def _prepare_lifetime_for_blender(self):
        if self.lifetime is None:
            return None
        lifetime = self.lifetime.cast_to(self.dims_out)[{"t": self.dims["h"].items[-1]}].values
        return lifetime
