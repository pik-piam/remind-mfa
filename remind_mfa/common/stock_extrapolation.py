import flodym as fd
import numpy as np
from remind_mfa.common.data_blending import blending_factor
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
    transition_smoothing: str = "critically_damped"
    """transition_smoothing (str): Method for blending between historical and future stock. Possible values are "critically_damped", "shift_zeroth_order", "none". Defaults to "critically_damped"."""
    lifetime: Optional[fd.FlodymArray] = None
    """lifetime of the stock, used to determine the number of timesteps that are used for the average slope calculation in the critically damped blend."""

    def extrapolate(self):
        """Preprocessing and extrapolation."""
        self.set_dims(self.indep_fit_dim_letters)
        self.init_arrays()
        self.calc_arrays_from_parameters_dict()
        self.set_predictor()
        self.get_pure_regression()
        self.get_pure_regression_single_predictor()
        self.fit()
        self.transform_two_predictor_regression()
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
        normalized_gdppc = (log_gdppc - np.mean(log_gdppc)) / (np.log10(1e5) - np.log10(1e3))

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

    def get_pure_regression_single_predictor(self):
        """Get a single-predictor regression based only on GDP per capita, which is used for the stock fitting.
        Historic stocks are divided by the time-dependent extrapolation function and then regressed only over GDP per capita.
        """
        if self.cfg.regress_over == RegressOverModes.LOGGDPPC_TIME:
            # transform historic stocks by dividing by the time-dependent part of the regression
            prms = [
                self.extrapolation.fit_prms[np.newaxis, ..., i]
                for i in range(self.extrapolation.n_prms)
            ]
            time_dependent_func = self.extrapolation.func(
                self.extrapolation.predictor_values, prms, factor="f3"
            )[: self.n_historic]
            data_to_extrapolate = self.extrapolation.data_to_extrapolate / time_dependent_func
            self.single_predictor = self.predictor["x1"]
            # adapt the bounds
            new_bounds = [b for b in self.bound_list.bound_list if b.var_name != "x2_growth_rate"]
            for i, b in enumerate(new_bounds):
                if b.var_name == "x1_growth_rate":
                    new_bounds[i].var_name = "growth_rate"
                    break
            bound_list = BoundList(
                target_dims=self.dims[self.indep_fit_dim_letters],
                bound_list=new_bounds,
            )
            self.extrapolation_single_predictor = (
                self.cfg.stock_extrapolation_class.single_predictor_cls(
                    data_to_extrapolate=data_to_extrapolate,
                    predictor_values=self.single_predictor,
                    independent_dims=self.fit_dim_idx,
                    bound_list=bound_list,
                    weights=self.extrapolation.weights,
                )
            )
            self.extrapolation_single_predictor.regress()
            self.stocks_to_fit = fd.StockArray(
                dims=self.dims[self.historic_dim_letters], values=data_to_extrapolate
            )
        else:
            self.extrapolation_single_predictor = self.extrapolation
            self.stocks_to_fit = self.historic_stocks_pc
            self.single_predictor = self.predictor

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
            historic_stocks_pc=self.stocks_to_fit,
            extrapolation=self.extrapolation_single_predictor,
            predictor=self.single_predictor,
            dims_out=self.dims_out,
            penalty_weights=penalty_weights,
        )
        self.fitted_regression = stock_fitter.fit()

    def transform_two_predictor_regression(self):
        """If the regression was performed with two predictors (e.g. time and GDP per capita), we need to transform it back to a regression over only GDP per capita for the stock correction."""
        if self.cfg.regress_over == RegressOverModes.LOGGDPPC_TIME:
            prms = [
                self.extrapolation.fit_prms[np.newaxis, ..., i]
                for i in range(self.extrapolation.n_prms)
            ]
            time_dependent_func = self.extrapolation.func(
                self.extrapolation.predictor_values, prms, factor="f3"
            )
            self.fitted_regression[...] = self.fitted_regression.values * time_dependent_func

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

    @property
    def dims_out(self):
        return self.dims[self.target_dim_letters]

    @property
    def n_historic(self):
        return self.dims["h"].len
    
    def critically_damped_blend(self, historical: np.ndarray, prediction: np.ndarray) -> np.ndarray:
        """
        Blend historical and extrapolated values using a forced critically damped system
        approach (PD-controller logic) to ensure a smooth transition.

        The transition is modeled as a dynamic critically damped spring-damper system:

            Y'' + 2kY' + k²Y = k²P(t) + 2kP'(t)

        where Y is the blended trajectory, P the extrapolation target, and k the damping
        parameter derived from ``approaching_time``. The ODE is solved using a semi-implicit
        Euler method. To prevent overshooting and eliminate steady-state tracking errors,
        the system combines an anticipatory D-term with a long-term quintic alpha-blend.
        Internal state (velocity) is re-synchronized at each step after blending.

        Args:
            historical (np.ndarray): Historical stock data with time as the first axis.
            prediction (np.ndarray): Extrapolated stock data from the regression, same shape
                as the full output (covering both historical and future period in first axis).

        Returns:
            np.ndarray: Stock array with exact historical values preserved up to the last
            historical index and a smooth blended trajectory thereafter.
        """
        time_arr = np.array(self.dims["t"].items)
        last_history_idx = len(historical) - 1

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

        # 1. Isolate the time window and prediction values we need to integrate over
        t_future = time_arr[last_history_idx:]
        p_future = prediction[last_history_idx:]

        # 2. Set the initial conditions at the transition point
        y0 = historical[last_history_idx, :]
        v0 = self._trend_slope(time_arr, historical, self._lifetime_dependent_n(), last_history_idx)
        # 3. Integrate to find the blended future path Y(t)
        y_future = self._integrate_transition(y0, v0, t_future, p_future, approaching_time)

        # 4. Construct the final contiguous array
        blended_stock = prediction.copy()
        blended_stock[:last_history_idx] = historical[:last_history_idx]  # Preserve exact history
        blended_stock[last_history_idx:] = y_future  # Apply blended future

        return blended_stock

    def _integrate_transition(
        self,
        y0: np.ndarray,
        v0: np.ndarray,
        t_array: np.ndarray,
        p_array: np.ndarray,
        approaching_time: float,
    ) -> np.ndarray:
        """
        Integrate a trajectory from an initial state (y0, v0) that smoothly tracks a target prediction p_array
        using a critically damped PD-controller, with a long-term quintic blend for exact convergence.

        The controller drives Y toward P via a dynamic critically damped spring-damper system :
            Y'' + 2k·Y' + k²Y = k²P(t) + 2k·P'(t)
        integrated with a semi-implicit Euler method.

        To avoid overshoot during saturation phases, P'(t) is estimated using a look-ahead index
        that decreases from 5 to 1 over the first half of ``approaching_time``, then stays at 1.
        On top of the controller, a quintic blend progressively replaces Y with P over the full
        time window, guaranteeing an exact match with P at ``t0 + 10 * approaching_time``.
        In a static system (no P' term) without blending, the system converges to 95% of the
        prediction after ``approaching_time`` years.

        Args:
            y0 (np.ndarray): Initial position at the transition point. Shape ``(spatial...)``.
            v0 (np.ndarray): Initial velocity (slope) at the transition point, same shape as ``y0``.
            t_array (np.ndarray): 1D array of time values starting at the transition point.
            p_array (np.ndarray): Target prediction array with time as the first axis,
                shape ``(len(t_array), spatial...)``. Must be uniformly spaced in time.
            approaching_time (float): Characteristic timescale in years. Governs the damping
                parameter ``k = 4.74 / approaching_time`` and the look-ahead ramp length.

        Returns:
            np.ndarray: Integrated trajectory array of shape ``(len(t_array), spatial...)``.
        """
        n_steps = len(t_array)
        dt = t_array[1] - t_array[0]
        k = 4.74 / approaching_time

        # --- Precompute look-ahead predictor velocity for each timestep ---
        # Using P'(t + n_fwd*dt) [fwd = forward] instead of P'(t) anticipates
        # future behavior of P (e.g. saturation), preventing the controller from
        # overshooting. n_fwd decreases linearly from n_fwd_max to 1 over the first
        # n_ramp_steps, then remains 1 for the rest of the integration.
        n_fwd_max = 5
        n_ramp_steps = int(approaching_time / 2)
        n_fwd = np.maximum(
            1, np.round(n_fwd_max * np.maximum(0.0, 1 - np.arange(n_steps) / n_ramp_steps))
        ).astype(int)
        # now, use n_fwd to construct index for p velocity
        lookahead_idx = np.minimum(np.arange(n_steps) + n_fwd - 1, n_steps - 2)
        vp_array = (p_array[lookahead_idx + 1] - p_array[lookahead_idx]) / dt

        # --- Precompute quintic blend weights ---
        # Alpha blends from 0 to 1 within 10x approaching_time using quintic function.
        t0 = t_array[0]
        t_full_match = t0 + 10 * approaching_time
        alpha_arr = blending_factor(
            np.clip((t_array - t0) / (t_full_match - t0), 0.0, 1.0), "quintic"
        )  # (n_steps,)

        # --- Initialize state ---
        y = np.zeros_like(p_array, dtype=float)
        v = np.zeros_like(p_array, dtype=float)
        y[0], v[0] = y0.copy(), v0.copy()
        y_curr, v_curr = y[0].copy(), v[0].copy()

        # --- Integrate ---
        for i in range(1, n_steps):
            # 1. Compute acceleration
            dv_dt = k**2 * (p_array[i] - y_curr) + 2 * k * (vp_array[i] - v_curr)
            # 2. Update velocity and position
            v_curr = v_curr + dv_dt * dt
            y_curr = y_curr + v_curr * dt

            # Quintic blend toward prediction
            y_curr = (1 - alpha_arr[i]) * y_curr + alpha_arr[i] * p_array[i]
            v_curr = (y_curr - y[i - 1]) / dt  # re-sync velocity after blend

            # Store results
            y[i], v[i] = y_curr, v_curr

        return y

    def _lifetime_dependent_n(
        self, lower_lt: float = 3.0, upper_lt: float = 30.0, min_n: int = 1, max_n: int = 10
    ) -> np.ndarray:
        """
        Calculate a dynamically scaled smoothing window size based on product lifetime.

        Short-lifetime products have volatile stocks and benefit from more smoothing;
        long-lifetime products have high inertia and need less. Window sizes are mapped
        from ``max_n`` (shortest lifetime) to ``min_n`` (longest lifetime) on a logarithmic
        scale.

        Args:
            lower_lt (float): Lower bound for clipping product lifetime in years. Defaults to 3.0.
            upper_lt (float): Upper bound for clipping product lifetime in years. Defaults to 30.0.
            min_n (int): Minimum smoothing window size (applied to long-lifetime products).
                Defaults to 1.
            max_n (int): Maximum smoothing window size (applied to short-lifetime products).
                Defaults to 10.

        Returns:
            np.ndarray: Array of integer window sizes (number of time steps minus one) shaped
            according to the spatial dimensions of the output stock array.

        Raises:
            ValueError: If more than one independent fit dimension is set.
        """
        if len(self.indep_fit_dim_letters) > 1:
            raise ValueError(
                "Multiple independent fit dimensions are not supported here. Please fix"
            )

        if self.lifetime is None:
            return np.full(self.dims_out.drop("t").shape, min_n, dtype=int)

        # use last historical lifetime
        lifetime = self.lifetime.cast_to(self.dims_out)[{"t": self.dims["h"].items[-1]}].values

        # 1. Clip lifetimes to strictly enforce bounds
        lt_clip = np.clip(lifetime, lower_lt, upper_lt)

        # 2. Logarithmic normalization (0.0 for shortest, 1.0 for longest)
        log_lt = np.log(lt_clip)
        log_lower = np.log(lower_lt)
        log_upper = np.log(upper_lt)

        if log_upper == log_lower:  # Prevent division by zero edge-case
            return np.full_like(self.lifetime.values, max_n, dtype=int)

        alpha = (log_lt - log_lower) / (log_upper - log_lower)

        # 3. Inverted mapping: alpha=0 maps to max_n, alpha=1 maps to min_n
        n_float = max_n - alpha * (max_n - min_n)

        # 4. Round to nearest integer for array indexing/window sizing
        return np.round(n_float).astype(int)

    def _trend_slope(
        self, t: np.ndarray, y: np.ndarray, n: Union[int, np.ndarray], idx: int, deg: int = 1
    ) -> np.ndarray:
        """
        Calculate the slope of ``y`` at a given time index across all spatial dimensions.

        For each dimension element combination a polynomial of degree ``deg`` (at most) is fitted to the
        ``n`` most recent time steps ending at ``idx``, and the analytical derivative of that
        polynomial is evaluated at ``t[idx]``. When fewer than two points are available
        (``current_deg == 0``), a simple  backward finite-difference fallback is used.

        Args:
            t (np.ndarray): 1-D array of time values.
            y (np.ndarray): Data array with time as the first axis, arbitrary spatial shape thereafter.
            n (int or np.ndarray): Smoothing window size. Either a scalar applied to all spatial
                positions or an array matching the spatial shape of ``y``.
            idx (int): Time index at which to evaluate the slope (typically the last historical index).
            deg (int): Maximum polynomial degree for the local fit. Defaults to 2.
                Only degrees 1 and 2 are supported.

        Returns:
            np.ndarray: Array of slopes with the same shape as ``y.shape[1:]``.

        Raises:
            ValueError: If ``n`` is an array whose shape does not match the spatial shape of ``y``.
            ValueError: If ``deg`` is not 1 or 2.
        """
        dim_shape = y.shape[1:]  # assuming time is the first dimension
        deriv_array = np.zeros(dim_shape, dtype=float)

        # Standardize n into an array so we can index it easily
        if isinstance(n, (int, np.integer)):
            n_array = np.full(dim_shape, n, dtype=int)
        else:
            n_array = np.asarray(n)
            if n_array.shape != dim_shape:
                raise ValueError(
                    f"Shape of n {n_array.shape} must match spatial shape of y {dim_shape}."
                )

        for spatial_idx in np.ndindex(dim_shape):
            current_n = n_array[spatial_idx]
            start_idx = max(0, idx - current_n)

            time_slice = slice(start_idx, idx + 1)
            t_window = t[time_slice]
            y_window = y[(time_slice,) + spatial_idx]

            # Set degree based on available points, not exceeding specified deg
            current_deg = min(deg, current_n - 1)
            if current_deg == 0:
                # fall back to finite difference
                deriv_array[spatial_idx] = (y_window[-1] - y_window[-2]) / (
                    t_window[-1] - t_window[-2]
                )
                continue

            # Fit polynomial to this single 1D array
            coeffs = np.polyfit(t_window, y_window, deg=current_deg)

            if current_deg == 1:
                deriv_array[spatial_idx] = coeffs[0]
            elif current_deg == 2:
                deriv_array[spatial_idx] = 2 * coeffs[0] * t_window[-1] + coeffs[1]
            else:
                raise ValueError("Only polynomial degrees 1 or 2 are supported.")

        return deriv_array
