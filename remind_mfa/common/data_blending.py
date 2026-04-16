from typing import Optional, Union, Any

import flodym as fd
import numpy as np

from remind_mfa.common.assumptions_doc import add_assumption_doc


def blend(
    target_dims: fd.DimensionSet,
    y_lower: fd.FlodymArray,
    y_upper: fd.FlodymArray,
    x: Union[fd.FlodymArray, str],  # str: dimension letter
    x_lower: Union[fd.FlodymArray, int, float],
    x_upper: Union[fd.FlodymArray, int, float],
    type: str = "poly_mix",
) -> fd.FlodymArray:
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


def blending_factor(x: np.ndarray, type: str) -> np.ndarray:

    def linear(x):
        x = np.clip(x, 0, 1)
        return x

    def sigmoid3(x):
        return 1.0 / (1.0 + np.exp(3 - 6 * x))

    def sigmoid4(x):
        return 1.0 / (1.0 + np.exp(4 - 8 * x))

    def extrapol_sigmoid3(x):
        return (sigmoid3(x) - sigmoid3(0)) / (sigmoid3(1) - sigmoid3(0))

    def extrapol_sigmoid4(x):
        return (sigmoid4(x) - sigmoid4(0)) / (sigmoid4(1) - sigmoid4(0))

    def clamped_sigmoid3(x):
        x = np.clip(x, 0, 1)
        return extrapol_sigmoid3(x)

    def clamped_sigmoid4(x):
        x = np.clip(x, 0, 1)
        return extrapol_sigmoid4(x)

    def hermite(x):
        x = np.clip(x, 0, 1)
        return 3 * x**2 - 2 * x**3

    def quintic(x):
        x = np.clip(x, 0, 1)
        return 6 * x**5 - 15 * x**4 + 10 * x**3

    def poly_mix(x):
        return 0.5 * hermite(x) + 0.5 * quintic(x)

    def converge_quadratic(x):
        x = np.clip(x, 0, 1)
        return 1 - (1 - x) ** 2

    function_map = {
        "linear": linear,
        "sigmoid3": sigmoid3,
        "sigmoid4": sigmoid4,
        "extrapol_sigmoid3": extrapol_sigmoid3,
        "extrapol_sigmoid4": extrapol_sigmoid4,
        "clamped_sigmoid3": clamped_sigmoid3,
        "clamped_sigmoid4": clamped_sigmoid4,
        "hermite": hermite,
        "quintic": quintic,
        "poly_mix": poly_mix,
        "converge_quadratic": converge_quadratic,
    }

    if type not in function_map:
        raise ValueError(
            f"Unknown blending function {type}. Must be one of {list(function_map.keys())}"
        )
    return function_map[type](x)


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
        
        assert self.time.shape[0] == self.prediction.shape[0], "Time and prediction must have the same length."
        assert self.historical.shape[1:] == self.prediction.shape[1:], "Historical and prediction must have the same spatial shape."
        assert self.historical.shape[0] <= self.prediction.shape[0], "Historical data cannot be longer than prediction."

        self.lifetime = lifetime
        if self.lifetime is not None:
            assert self.lifetime.shape == self.prediction.shape[1:], "Lifetime must match spatial shape of prediction."

    def blend(self) -> np.ndarray:
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

        Returns:
            np.ndarray: Stock array with exact historical values preserved up to the last
            historical index and a smooth blended trajectory thereafter.
        """
        last_history_idx = len(self.historical) - 1

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
        t_future = self.time[last_history_idx:]
        p_future = self.prediction[last_history_idx:]

        # 2. Set the initial conditions at the transition point
        y0 = self.historical[last_history_idx, :]
        v0 = self._trend_slope(self.time, self.historical, self._lifetime_dependent_n(), last_history_idx)
        # 3. Integrate to find the blended future path Y(t)
        y_future = self._integrate_transition(y0, v0, t_future, p_future, approaching_time)

        # 4. Construct the final contiguous array
        blended_stock = self.prediction.copy()
        blended_stock[:last_history_idx] = self.historical[:last_history_idx]  # Preserve exact history
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
        Raises:
            ValueError: If more than one independent fit dimension is set.
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
            deg (int): Maximum polynomial degree for the local fit. Defaults to 1.

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