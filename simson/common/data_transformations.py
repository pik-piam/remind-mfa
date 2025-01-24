from copy import copy
import numpy as np

from flodym import (
    StockArray, DynamicStockModel, SimpleFlowDrivenStock,
    DimensionSet, FlodymArray, Process, Parameter
)

from .data_extrapolations import SigmoidalExtrapolation, ExponentialExtrapolation, WeightedProportionalExtrapolation


def extrapolate_stock(
        historic_stocks: StockArray, dims: DimensionSet,
        parameters: dict[str, Parameter], curve_strategy: str,
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
    historic_pop = FlodymArray(dims=dims[('h', 'r')])
    historic_gdppc = FlodymArray(dims=dims[('h', 'r')])
    historic_stocks_pc = FlodymArray(dims=dims[historic_dim_letters])
    stocks_pc = FlodymArray(dims=dims[target_dim_letters])
    stocks = FlodymArray(dims=dims[target_dim_letters])

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
    return StockArray(**dict(stocks))


def extrapolate_to_future(historic_values: FlodymArray, scale_by: FlodymArray) -> FlodymArray:
    if not historic_values.dims.letters[0] == 'h':
        raise ValueError("First dimension of historic_parameter must be historic time.")
    if not scale_by.dims.letters[0] == 't':
        raise ValueError("First dimension of scaler must be time.")
    if not set(scale_by.dims.letters[1:]).issubset(historic_values.dims.letters[1:]):
        raise ValueError("Scaler dimensions must be subset of historic_parameter dimensions.")

    all_dims = historic_values.dims.union_with(scale_by.dims)

    dim_letters_out = ('t',) + historic_values.dims.letters[1:]
    extrapolated_values = FlodymArray.from_dims_superset(dims_superset=all_dims, dim_letters=dim_letters_out)

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


def prepare_stock_for_mfa(
        dims: DimensionSet, dsm: DynamicStockModel, prm: dict[str, Parameter], use: Process
):
    # We use an auxiliary stock for the prediction step to save dimensions and computation time
    # Therefore, we have to transfer the result to the higher-dimensional stock in the MFA system
    stock_extd = dsm.stock * prm['material_shares_in_goods'] * prm['carbon_content_materials']
    inflow = dsm.inflow * prm['material_shares_in_goods'] * prm['carbon_content_materials']
    outflow = dsm.outflow * prm['material_shares_in_goods'] * prm['carbon_content_materials']
    stock_dims = dims.get_subset(('t', 'r', 'g', 'm', 'e'))
    stock_extd = StockArray(values=stock_extd.values, name='in_use_stock', dims=stock_dims)
    inflow = StockArray(values=inflow.values, name='in_use_inflow', dims=stock_dims)
    outflow = StockArray(values=outflow.values, name='in_use_outflow', dims=stock_dims)
    stock = SimpleFlowDrivenStock(
        stock=stock_extd, inflow=inflow, outflow=outflow, name='in_use', process_name='use',
        process=use,
    )
    return stock


def transform_t_to_hist(ndarray: FlodymArray, dims: DimensionSet):
    """Transforms an array with time dimension to an array with historic time dimension."""
    hist_dim = dims['h']
    time_dim = dims['t']
    assert time_dim.items[
           :len(hist_dim.items)] == hist_dim.items, "Time dimension must start with historic time dimension."
    new_dims = ndarray.dims.replace('t', hist_dim)
    hist_array = FlodymArray.from_dims_superset(dims_superset=new_dims, dim_letters=new_dims.letters)
    hist_array.values = ndarray.values[:len(hist_dim.items)]
    return hist_array
