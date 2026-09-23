from typing import Optional, Union, Any

import flodym as fd
import numpy as np

from remind_mfa.common.assumptions_doc import add_assumption_doc


def blend(
    target_dims: fd.DimensionSet,
    y_lower: fd.FlodymArray,
    y_upper: fd.FlodymArray,
    x: Union[fd.FlodymArray, str],
    x_lower: Union[fd.FlodymArray, int, float],
    x_upper: Union[fd.FlodymArray, int, float],
    type: str = "poly_mix",
) -> fd.FlodymArray:
    """
    Blend between two arrays (y_lower, y_upper) along a dimension or variable x, using a specified blending function.

    This function interpolates (or blends) between y_lower and y_upper based on the normalized position of x between x_lower and x_upper,
    using a chosen blending curve (e.g., linear, sigmoid, hermite, quintic, etc.).

    Args:
        target_dims (fd.DimensionSet):
            The target dimensions for the output array. All input arrays and scalars are broadcast/cast to these dimensions.
        y_lower (fd.FlodymArray):
            The value (array) to use when x == x_lower (i.e., at the lower bound).
        y_upper (fd.FlodymArray):
            The value (array) to use when x == x_upper (i.e., at the upper bound).
        x (Union[fd.FlodymArray, str]):
            The variable to blend along. Can be a FlodymArray (values for each point) or a string (dimension name/letter) to use the corresponding dimension values from target_dims.
        x_lower (Union[fd.FlodymArray, int, float]):
            The lower bound for x (can be scalar or array). Where x == x_lower, the result is y_lower.
        x_upper (Union[fd.FlodymArray, int, float]):
            The upper bound for x (can be scalar or array). Where x == x_upper, the result is y_upper.
        type (str, optional):
            The blending function to use. Options include: 'linear', 'sigmoid3', 'sigmoid4', 'hermite', 'quintic', 'poly_mix', etc.
            Default is 'poly_mix'.

    Returns:
        fd.FlodymArray: The blended/interpolated array, with dimensions target_dims.

    Example:
        blend(target_dims, y_lower, y_upper, x="t", x_lower=2020, x_upper=2050, type="hermite")
        # Blends y_lower to y_upper as the 't' dimension goes from 2020 to 2050 using a Hermite curve.

    """
    if isinstance(x, str):
        x = fd.FlodymArray(dims=target_dims[(x,)], values=np.array(target_dims[x].items))
    x = x.cast_to(target_dims)
    y_lower = prepare_array(y_lower, target_dims)
    y_upper = prepare_array(y_upper, target_dims)
    x_lower = prepare_array(x_lower, target_dims)
    x_upper = prepare_array(x_upper, target_dims)

    x = (x - x_lower) / (x_upper - x_lower)
    a = fd.FlodymArray(dims=x.dims, values=blending_factor(x.values, type))
    return a * y_upper + (1 - a) * y_lower


def _linear(x):
    x = np.clip(x, 0, 1)
    return x


def _sigmoid3(x):
    return 1.0 / (1.0 + np.exp(3 - 6 * x))


def _sigmoid4(x):
    return 1.0 / (1.0 + np.exp(4 - 8 * x))


def _extrapol_sigmoid3(x):
    return (_sigmoid3(x) - _sigmoid3(0)) / (_sigmoid3(1) - _sigmoid3(0))


def _extrapol_sigmoid4(x):
    return (_sigmoid4(x) - _sigmoid4(0)) / (_sigmoid4(1) - _sigmoid4(0))


def _clamped_sigmoid3(x):
    x = np.clip(x, 0, 1)
    return _extrapol_sigmoid3(x)


def _clamped_sigmoid4(x):
    x = np.clip(x, 0, 1)
    return _extrapol_sigmoid4(x)


def _hermite(x):
    x = np.clip(x, 0, 1)
    return 3 * x**2 - 2 * x**3


def _quintic(x):
    x = np.clip(x, 0, 1)
    return 6 * x**5 - 15 * x**4 + 10 * x**3


def _poly_mix(x):
    return 0.5 * _hermite(x) + 0.5 * _quintic(x)


def _converge_quadratic(x):
    x = np.clip(x, 0, 1)
    return 1 - (1 - x) ** 2


_BLEND_FUNCTIONS = {
    "linear": _linear,
    "sigmoid3": _sigmoid3,
    "sigmoid4": _sigmoid4,
    "extrapol_sigmoid3": _extrapol_sigmoid3,
    "extrapol_sigmoid4": _extrapol_sigmoid4,
    "clamped_sigmoid3": _clamped_sigmoid3,
    "clamped_sigmoid4": _clamped_sigmoid4,
    "hermite": _hermite,
    "quintic": _quintic,
    "poly_mix": _poly_mix,
    "converge_quadratic": _converge_quadratic,
}

BLEND_TYPES = list(_BLEND_FUNCTIONS)
"""Names of all available blending functions."""


def blending_factor(x: np.ndarray, type: str) -> np.ndarray:
    if type not in _BLEND_FUNCTIONS:
        raise ValueError(f"Unknown blending function {type}. Must be one of {BLEND_TYPES}")
    return _BLEND_FUNCTIONS[type](x)


def prepare_array(value: Any, target_dims: fd.DimensionSet) -> fd.FlodymArray:
    if isinstance(value, (int, float)):
        array = fd.FlodymArray(dims=target_dims)
        array[...] = value
    elif isinstance(value, fd.FlodymArray):
        array = value.cast_to(target_dims)
    else:
        raise ValueError("value must be either a FlodymArray or a scalar.")
    return array


class CriticallyDampedBlender:

    def __init__(
        self,
        time: Union[np.ndarray, list],
        historical: np.ndarray,
        prediction: np.ndarray,
        lifetime: Optional[np.ndarray] = None,
    ):
        """
        Args:
            time (Union[np.ndarray, list]): Time values including historical and future periods.
            Same length as prediction
            historical (np.ndarray): Historical stock data with time as the first axis.
            prediction (np.ndarray): Extrapolated stock data from the regression, same shape
                as the full output (covering both historical and future period in first axis).
            lifetime (Optional[np.ndarray]): Lifetime used to dynamically determine trend window size.
            Should have the same shape as prediction/historical, except time (0th axis)
        """
        self.time = np.array(time)
        self.historical = historical
        self.prediction = prediction

        assert (
            self.time.shape[0] == self.prediction.shape[0]
        ), "Time and prediction must have the same length."
        assert (
            self.historical.shape[1:] == self.prediction.shape[1:]
        ), "Historical and prediction must have the same shape, except along the time dimension."
        assert (
            self.historical.shape[0] <= self.prediction.shape[0]
        ), "Historical data cannot be longer than prediction."

        self.lifetime = lifetime
        if self.lifetime is not None:
            assert (
                self.lifetime.shape == self.prediction.shape[1:]
            ), "Lifetime must match spatial shape of prediction."

    def blend(
        self,
        approaching_time: float = 50,
    ) -> np.ndarray:
        """
        Blend historical and extrapolated values using a forced critically damped system
        approach (PDA-controller logic) to ensure a C2-continuous transition.

        The transition is modeled as a third-order critically damped tracking system:

            Y''' + 3kY'' + 3k²Y' + k³Y = k³P(t) + 3k²P'(t) + 3kP''(t)

        where Y is the blended trajectory, P the extrapolation target, and
        k = 6.30 / approaching_time the damping parameter. The initial position is the
        last historical value; the initial velocity and acceleration are estimated from
        local polynomial fits to the recent historical trend, so position, slope, and
        curvature are all continuous at the transition point. The ODE is integrated with
        a semi-implicit Euler method; P''(t) is estimated with a look-ahead so the
        controller reacts to upcoming changes in P (e.g. saturation) before they occur,
        while P'(t) uses the plain local slope.

        Args:
            approaching_time (float): Characteristic timescale in years. Sets the damping
                parameter ``k = 6.30 / approaching_time`` (95% step-response convergence
                within ``approaching_time`` years), derived from solving
                ``e^{-x}(1 + x + x**2/2) = 0.05`` for ``x = k * approaching_time``.
                Must satisfy ``k * dt <= 0.5`` for
                numerical stability, i.e. ``approaching_time >= 12.6 years``. Defaults to 50.

        Returns:
            np.ndarray: Stock array with exact historical values preserved up to the last
            historical index and a smooth blended trajectory thereafter.
        """
        last_history_idx = len(self.historical) - 1

        # 1. Isolate the time window and prediction values we need to integrate over
        t_future = self.time[last_history_idx:]
        p_future = self.prediction[last_history_idx:]

        # 2. Set the initial conditions at the transition point
        y0 = self.historical[last_history_idx, :]
        trend_window = self._lifetime_dependent_n()
        v0, _ = self._trend_derivatives(
            self.time,
            self.historical,
            trend_window,  # short term velocity trend
            last_history_idx,
            deg=1,
        )
        _, a0 = self._trend_derivatives(
            self.time,
            self.historical,
            2 * (trend_window + 1),  # long term acceleration trend (+1 due to higher deg)
            last_history_idx,
            deg=2,
        )

        # 3. Integrate to find the blended future path Y(t)
        y_future = self._integrate_transition(
            y0,
            v0,
            a0,
            t_future,
            p_future,
            approaching_time,
        )

        # 4. Construct the final contiguous array
        blended_stock = self.prediction.copy()
        blended_stock[:last_history_idx] = self.historical[
            :last_history_idx
        ]  # Preserve exact history
        blended_stock[last_history_idx:] = y_future  # Apply blended future

        return blended_stock

    def _integrate_transition(
        self,
        y0: np.ndarray,
        v0: np.ndarray,
        a0: np.ndarray,
        t_array: np.ndarray,
        p_array: np.ndarray,
        approaching_time: float,
    ) -> np.ndarray:
        """
        Integrate a trajectory from an initial state (y0, v0, a0) that smoothly tracks a
        target prediction p_array using a third-order critically damped controller.

        The controller drives Y toward P via:
            Y''' + 3k·Y'' + 3k²·Y' + k³Y = k³P(t) + 3k²·P'(t) + 3k·P''(t),
            k = 6.30 / approaching_time
        integrated with a semi-implicit Euler method. P'(t) is the local slope; P''(t)
        is estimated with a look-ahead to prevent overshoot during saturation phases.

        Args:
            y0 (np.ndarray): Initial position at the transition point. Shape ``(spatial...)``.
            v0 (np.ndarray): Initial velocity (slope) at the transition point, same shape as ``y0``.
            a0 (np.ndarray): Initial acceleration (curvature) at the transition point,
                same shape as ``y0``.
            t_array (np.ndarray): 1D array of time values starting at the transition point.
            p_array (np.ndarray): Target prediction array with time as the first axis,
                shape ``(len(t_array), spatial...)``. Must be uniformly spaced in time.
            approaching_time (float): Characteristic timescale in years. Sets the damping
                parameter ``k = 6.30 / approaching_time``.

        Returns:
            np.ndarray: Integrated trajectory array of shape ``(len(t_array), spatial...)``.

        Raises:
            ValueError: If ``k * dt > 0.5``, i.e. ``approaching_time`` is too small relative
                to the time step for the integration to be numerically stable.
        """
        n_steps = len(t_array)
        dt = t_array[1] - t_array[0]

        # 6.30 is the solution to (1+x+x²/2)*exp(-x) = 0.05: the third-order critically
        # damped step response. k = 6.30 / approaching_time means 95% convergence within
        # approaching_time years.
        k = 6.30 / approaching_time

        # The semi-implicit Euler scheme diverges for k*dt above ~0.52.
        if k * dt > 0.5:
            raise ValueError(
                f"approaching_time={approaching_time} is too small for time step dt={dt}: "
                f"k*dt = {k * dt:.2f} > 0.5 makes the integration numerically unstable. "
                f"Use approaching_time >= {12.6 * dt:.1f}."
            )

        # --- Precompute predictor velocity and look-ahead acceleration ---
        vp_array, ap_array = self._calculate_derivatives(p_array, dt, n_steps, approaching_time)

        # --- Initialize state ---
        y = np.zeros_like(p_array, dtype=float)
        v = np.zeros_like(p_array, dtype=float)
        a = np.zeros_like(p_array, dtype=float)
        y[0], v[0], a[0] = y0.copy(), v0.copy(), a0.copy()
        y_curr, v_curr, a_curr = y[0].copy(), v[0].copy(), a[0].copy()

        # --- Integrate ---
        for i in range(1, n_steps):
            # 1. Compute jerk.
            da_dt = (
                k**3 * (p_array[i - 1] - y_curr)
                + 3 * k**2 * (vp_array[i - 1] - v_curr)
                + 3 * k * (ap_array[i - 1] - a_curr)
            )
            # 2. Update acceleration, velocity, and position.
            a_curr = a_curr + da_dt * dt
            v_curr = v_curr + a_curr * dt
            y_curr = y_curr + v_curr * dt
            # Store results.
            y[i], v[i], a[i] = y_curr, v_curr, a_curr

        return y

    def _calculate_derivatives(
        self,
        p_array: np.ndarray,
        dt: float,
        n_steps: int,
        approaching_time: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Estimate P'(t) at each timestep, and P''(t + n_fwd(t)*dt) — the curvature of the
        prediction looked up n_fwd steps ahead. Only the curvature term is shifted:
        looking ahead lets it anticipate future changes in P (e.g. saturation), so the
        derivative term of the controller begins reacting before P actually flattens,
        preventing overshoot. The velocity term uses the plain local slope.

        n_fwd ramps continuously from n_fwd_max down to 0 over the first half of
        approaching_time, then stays at 0 (plain local curvature). The continuous ramp
        avoids the discrete jumps that arise from integer look-ahead steps. Both
        derivatives are computed on the raw prediction first; only the curvature is then
        sampled at the shifted position, so the ramp itself does not distort the estimate.

        Returns:
            tuple[np.ndarray, np.ndarray]: Local first derivative and look-ahead second
            derivative of the prediction, each of shape ``(n_steps, spatial...)``.
        """
        n_fwd_max = 5
        n_ramp_steps = max(1, int((approaching_time / 2) / dt))

        # Continuous look-ahead amount for each step: 5 → 0 over n_ramp_steps, then 0
        n_fwd_cont = n_fwd_max * np.maximum(0.0, 1.0 - np.arange(n_steps) / n_ramp_steps)

        # Slope and curvature of p at every step
        # (central differences; second-order one-sided at boundaries)
        vp_raw = np.gradient(p_array, dt, axis=0)
        ap_raw = np.gradient(vp_raw, dt, axis=0)

        # For each step i, look n_fwd_cont[i] steps forward in the derivative arrays
        look_pos = np.clip(np.arange(n_steps, dtype=float) + n_fwd_cont, 0, n_steps - 1)

        # Fractional interpolation between the two bracketing integer positions
        lo = look_pos.astype(int)
        hi = np.minimum(lo + 1, n_steps - 1)
        w = (look_pos - lo).reshape((-1,) + (1,) * (p_array.ndim - 1))
        ap_lookahead = (1 - w) * ap_raw[lo] + w * ap_raw[hi]
        return vp_raw, ap_lookahead

    def _lifetime_dependent_n(
        self,
        lower_lt: float = 3.0,
        upper_lt: float = 30.0,
        min_n: int = 1,
        max_n: int = 10,
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
        """

        if self.lifetime is None:
            return np.full_like(self.prediction[0], min_n, dtype=int)

        # 1. Clip lifetimes to strictly enforce bounds
        lt_clip = np.clip(self.lifetime, lower_lt, upper_lt)

        # 2. Logarithmic normalization (0.0 for shortest, 1.0 for longest)
        log_lt = np.log(lt_clip)
        log_lower = np.log(lower_lt)
        log_upper = np.log(upper_lt)

        if log_upper == log_lower:  # Prevent division by zero edge-case
            return np.full_like(self.lifetime, max_n, dtype=int)

        alpha = (log_lt - log_lower) / (log_upper - log_lower)

        # 3. Inverted mapping: alpha=0 maps to max_n, alpha=1 maps to min_n
        n_float = max_n - alpha * (max_n - min_n)

        # 4. Round to nearest integer for array indexing/window sizing
        return np.round(n_float).astype(int)

    def _trend_derivatives(
        self,
        t: np.ndarray,
        y: np.ndarray,
        window_size: Union[int, np.ndarray],
        idx: int,
        deg: int = 1,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Calculate the first and second derivative of ``y`` at a given time index across
        all spatial dimensions.

        For each dimension element combination a polynomial of degree ``deg`` is fitted to
        the ``window_size + 1`` most recent time steps ending at ``idx``, and the analytical
        derivatives of that polynomial are evaluated at ``t[idx]``. For ``deg=1``, the
        second derivative is zero.

        Args:
            t (np.ndarray): 1-D array of time values.
            y (np.ndarray): Data array with time as the first axis, arbitrary spatial shape thereafter.
            window_size (int or np.ndarray): Smoothing window size. Either a scalar applied to all spatial
                positions or an array matching the spatial shape of ``y``. Must be at least ``deg``
                everywhere so the fit is well-determined.
            idx (int): Time index at which to evaluate the derivatives (typically the last
                historical index).
            deg (int): Polynomial degree for the local fit. Defaults to 1.

        Returns:
            tuple[np.ndarray, np.ndarray]: Arrays of first and second derivatives, each with
            the same shape as ``y.shape[1:]``.

        Raises:
            ValueError: If any entry of ``window_size`` is smaller than ``deg``.
            ValueError: If ``window_size`` is an array whose shape does not match the spatial shape of ``y``.
        """

        if not np.all(window_size >= deg):
            raise ValueError(
                f"Window size {window_size} must be at least {deg} to fit a polynomial of degree {deg}."
            )

        dim_shape = y.shape[1:]  # assuming time is the first dimension
        deriv_array = np.zeros(dim_shape, dtype=float)
        second_deriv_array = np.zeros(dim_shape, dtype=float)

        # Standardize n into an array so we can index it easily
        if isinstance(window_size, (int, np.integer)):
            window_sizes = np.full(dim_shape, window_size, dtype=int)
        else:
            window_sizes = np.asarray(window_size)
            if window_sizes.shape != dim_shape:
                raise ValueError(
                    f"Shape of window_size {window_sizes.shape} must match spatial shape of y {dim_shape}."
                )

        # TODO can this be vectorized?
        for spatial_idx in np.ndindex(dim_shape):
            start_idx = max(0, idx - window_sizes[spatial_idx])

            time_slice = slice(start_idx, idx + 1)
            t_window = t[time_slice]
            y_window = y[(time_slice,) + spatial_idx]

            # Fit polynomial to this single 1D array
            polynomial = np.polynomial.Polynomial.fit(t_window, y_window, deg=deg)

            deriv_array[spatial_idx] = polynomial.deriv(1)(t[idx])
            second_deriv_array[spatial_idx] = polynomial.deriv(2)(t[idx])

        return deriv_array, second_deriv_array
