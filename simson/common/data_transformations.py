import numpy as np
import flodym as fd

from .data_extrapolations import SigmoidalExtrapolation, ExponentialExtrapolation, WeightedProportionalExtrapolation


def extrapolate_stock(
        historic_stocks: fd.StockArray, dims: fd.DimensionSet,
        parameters: dict[str, fd.Parameter], curve_strategy: str,
        target_dim_letters=None
):
    """Performs the per-capita transformation and the extrapolation."""

    if target_dim_letters is None:
        historic_dim_letters = historic_stocks.dims.letters
        target_dim_letters = ('t',) + historic_dim_letters[1:]
    else:
        historic_dim_letters = ('h',) + target_dim_letters[1:]

    # transform to per capita
    pop = parameters['population']
    historic_pop = fd.FlodymArray(dims=dims[('h', 'r')])
    historic_gdppc = fd.FlodymArray(dims=dims[('h', 'r')])
    historic_stocks_pc = fd.FlodymArray(dims=dims[historic_dim_letters])
    stocks_pc = fd.FlodymArray(dims=dims[target_dim_letters])
    stocks = fd.FlodymArray(dims=dims[target_dim_letters])

    historic_pop[...] = pop[{'t': dims['h']}]
    historic_gdppc[...] = parameters['gdppc'][{'t': dims['h']}]
    historic_stocks_pc[...] = historic_stocks / historic_pop

    if curve_strategy == "GDP_regression":
        gdp_regression(historic_stocks_pc.values, parameters['gdppc'].values, stocks_pc.values)
    elif curve_strategy == 'Exponential_GDP_regression':
        gdp_regression(historic_stocks_pc.values, parameters['gdppc'].values, stocks_pc.values,
                       fitting_function_type='exponential')
    else:
        raise RuntimeError(f"Extrapolation strategy {curve_strategy} is not defined. "
                           f"It needs to be 'GDP_regression'.")

    # transform back to total stocks
    stocks[...] = stocks_pc * pop

    # visualize_stock(self, self.parameters['gdppc'], historic_gdppc, stocks, historic_stocks, stocks_pc, historic_stocks_pc)
    return fd.StockArray(**dict(stocks))


def extrapolate_to_future(historic_values: fd.FlodymArray, scale_by: fd.FlodymArray) -> fd.FlodymArray:
    if not historic_values.dims.letters[0] == 'h':
        raise ValueError("First dimension of historic_parameter must be historic time.")
    if not scale_by.dims.letters[0] == 't':
        raise ValueError("First dimension of scaler must be time.")
    if not set(scale_by.dims.letters[1:]).issubset(historic_values.dims.letters[1:]):
        raise ValueError("Scaler dimensions must be subset of historic_parameter dimensions.")

    all_dims = historic_values.dims.union_with(scale_by.dims)

    dim_letters_out = ('t',) + historic_values.dims.letters[1:]
    extrapolated_values = fd.FlodymArray.from_dims_superset(dims_superset=all_dims, dim_letters=dim_letters_out)

    scale_by = scale_by.cast_to(extrapolated_values.dims)

    extrapolation = WeightedProportionalExtrapolation(
        data_to_extrapolate=historic_values.values,
        target_range=scale_by.values)
    extrapolated_values.set_values(extrapolation.extrapolate())

    return extrapolated_values


def gdp_regression(historic_stocks_pc, gdppc, prediction_out, fitting_function_type='sigmoid'):
    shape_out = prediction_out.shape
    pure_prediction = np.zeros_like(prediction_out)
    n_historic = historic_stocks_pc.shape[0]

    if fitting_function_type == 'sigmoid':
        extrapolation_class = SigmoidalExtrapolation
    elif fitting_function_type == 'exponential':
        extrapolation_class = ExponentialExtrapolation
    else:
        raise ValueError('fitting_function_type must be either "sigmoid" or "exponential".')

    for idx in np.ndindex(shape_out[1:]):
        # idx is a tuple of indices for all dimensions except the time dimension
        index = (slice(None),) + idx
        current_hist_stock_pc = historic_stocks_pc[index]
        current_gdppc = gdppc[index[:2]]
        extrapolation = extrapolation_class(
            data_to_extrapolate=current_hist_stock_pc,
            target_range=current_gdppc
        )
        pure_prediction[index] = extrapolation.regress()

    prediction_out[...] = pure_prediction - (
            pure_prediction[n_historic - 1, :] - historic_stocks_pc[n_historic - 1, :]
    )
    prediction_out[:n_historic, ...] = historic_stocks_pc


def blend_short_term_to_long_term(to_smooth: fd.FlodymArray, smooth_extrapolation: fd.FlodymArray, type: str, start_idx: int, duration: int = None,
           sigmoid_factor=8):
    assert type in ['linear', 'sigmoid'], (f"type must be either 'linear' or 'sigmoid',"
                                           f"{type} is undefined.")
    assert to_smooth.dims == smooth_extrapolation.dims, \
        "to_smooth and smooth_extrapolation must have the same dimensions."
    result = to_smooth.model_copy()
    result.values = blend_np_arrays_by_time(to_smooth.values, smooth_extrapolation.values, type, start_idx, duration, sigmoid_factor)

    return result


def blend_np_arrays_by_time(to_smooth: np.ndarray, smooth_extrapolation: np.ndarray, type: str, start_idx: int, duration: int = None,
              sigmoid_factor=8):
    total_years = to_smooth.shape[0]
    if duration is None:
        duration = total_years - start_idx
    end_idx = start_idx + duration
    short_term_years = end_idx - start_idx

    # create scaler to weight the two arrays
    past = np.linspace(0, 0, num=123)
    if type == 'linear':
        short_term = np.linspace(0, 1, num=short_term_years)
    elif type == 'sigmoid':
        sigmoid_parameters = np.arange(short_term_years)
        short_term = 1 / (1 + np.e ** (-((
                sigmoid_parameters - short_term_years / 2)) / sigmoid_factor))  # increase last number to flatten sigmoid further
    future = np.linspace(1, 1, num=total_years - start_idx - short_term_years)
    scaler = np.concatenate((past, short_term, future))

    # perform smoothing
    to_smooth_weighted = np.einsum('t...,t->t...', to_smooth, scaler)
    smooth_extrapolation_weighted = np.einsum('t...,t->t...', smooth_extrapolation, 1 - scaler)
    result = to_smooth_weighted + smooth_extrapolation_weighted

    return result
