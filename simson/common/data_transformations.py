import numpy as np
import flodym as fd

from .data_extrapolations import (
    SigmoidalExtrapolation,
    ExponentialExtrapolation,
    WeightedProportionalExtrapolation,
    MultiDimLogSigmoidalExtrapolation,
    LogSigmoidalExtrapolation,
)


def extrapolate_stock(
        historic_stocks: fd.StockArray,
        dims: fd.DimensionSet,
        parameters: dict[str, fd.Parameter],
        curve_strategy: str,
        target_dim_letters=None,
        saturation_level=None,
):
    """Performs the per-capita transformation and the extrapolation."""

    if target_dim_letters is None:
        historic_dim_letters = historic_stocks.dims.letters
        target_dim_letters = ("t",) + historic_dim_letters[1:]
    else:
        historic_dim_letters = ("h",) + target_dim_letters[1:]

    # transform to per capita
    pop = parameters["population"]
    historic_pop = fd.FlodymArray(dims=dims[("h", "r")])
    historic_gdppc = fd.FlodymArray(dims=dims[("h", "r")])
    historic_stocks_pc = fd.FlodymArray(dims=dims[historic_dim_letters])
    stocks_pc = fd.FlodymArray(dims=dims[target_dim_letters])
    stocks = fd.FlodymArray(dims=dims[target_dim_letters])

    historic_pop[...] = pop[{"t": dims["h"]}]
    historic_gdppc[...] = parameters["gdppc"][{"t": dims["h"]}]
    historic_stocks_pc[...] = historic_stocks / historic_pop

    extrapolation_class_dict = {
        'GDP_regression': SigmoidalExtrapolation,
        'Exponential_GDP_regression': ExponentialExtrapolation,
        'LogSigmoid_GDP_regression': LogSigmoidalExtrapolation
    }

    assert curve_strategy in extrapolation_class_dict.keys(), \
        f"Extrapolation strategy {curve_strategy} is not defined."

    gdp_regression(historic_stocks_pc.values,
                   parameters["gdppc"].values,
                   stocks_pc.values,
                   extrapolation_class_dict[curve_strategy],
                   saturation_level=saturation_level)

    # transform back to total stocks
    stocks[...] = stocks_pc * pop

    # visualize_stock(self, self.parameters['gdppc'], historic_gdppc, stocks, historic_stocks, stocks_pc, historic_stocks_pc)
    return fd.StockArray(**dict(stocks))


def extrapolate_to_future(
        historic_values: fd.FlodymArray, scale_by: fd.FlodymArray
) -> fd.FlodymArray:
    if not historic_values.dims.letters[0] == "h":
        raise ValueError("First dimension of historic_parameter must be historic time.")
    if not scale_by.dims.letters[0] == "t":
        raise ValueError("First dimension of scaler must be time.")
    if not set(scale_by.dims.letters[1:]).issubset(historic_values.dims.letters[1:]):
        raise ValueError("Scaler dimensions must be subset of historic_parameter dimensions.")

    all_dims = historic_values.dims.union_with(scale_by.dims)

    dim_letters_out = ("t",) + historic_values.dims.letters[1:]
    extrapolated_values = fd.FlodymArray.from_dims_superset(
        dims_superset=all_dims, dim_letters=dim_letters_out
    )

    scale_by = scale_by.cast_to(extrapolated_values.dims)

    extrapolation = WeightedProportionalExtrapolation(
        data_to_extrapolate=historic_values.values, target_range=scale_by.values
    )
    extrapolated_values.set_values(extrapolation.extrapolate())

    return extrapolated_values


def gdp_regression(historic_stocks_pc, gdppc, prediction_out, extrapolation_class=SigmoidalExtrapolation,
                   saturation_level=None):
    shape_out = prediction_out.shape
    pure_prediction = np.zeros_like(prediction_out)
    n_historic = historic_stocks_pc.shape[0]

    # TODO decide whether to delete these lines
    do_accumulate_gdp = False
    if do_accumulate_gdp:
        visualise = True
        if visualise:
            former_gdp = gdppc
            from matplotlib import pyplot as plt
            regions = ['CAZ', 'CHA', 'EUR', 'IND', 'JPN', 'LAM', 'MEA', 'NEU', 'OAS', 'REF', 'SSA', 'USA']
            years = range(1900, 2101)
            for r, region in enumerate(regions):
                plt.plot(years, former_gdp[:, r], label=region)
            for r, region in enumerate(regions):
                plt.plot(years, np.maximum.accumulate(gdppc, axis=0)[:, r], linestyle='--')
            plt.xlabel('Year')
            plt.ylabel('GDP pc')
            plt.title('GDP over Time')
            plt.legend()
            plt.show()
            a = 0
        gdppc = np.maximum.accumulate(gdppc, axis=0)  # doesn't let GDP drop ever

    for idx in np.ndindex(shape_out[1:]):
        # idx is a tuple of indices for all dimensions except the time dimension
        idx_with_time_dim = (slice(None),) + idx
        current_hist_stock_pc = historic_stocks_pc[idx_with_time_dim]
        current_gdppc = gdppc[idx_with_time_dim[:2]]
        current_saturation_level = saturation_level
        if isinstance(saturation_level, np.ndarray):
            current_saturation_level = saturation_level[idx]
        extrapolation = extrapolation_class(
            data_to_extrapolate=current_hist_stock_pc,
            target_range=current_gdppc,
            saturation_level=current_saturation_level
        )
        pure_prediction[idx_with_time_dim] = extrapolation.regress()

        if np.any(extrapolation.get_params() < 0):
            # TODO, parameters, especially the stretch factor, should not be negative
            a = 0

    # TODO: Discuss this - how should we deal with continuation at current point (currently changes sat level
    do_fit_current_levels = False
    if do_fit_current_levels:
        prediction_out[...] = pure_prediction - (
                pure_prediction[n_historic - 1, :] - historic_stocks_pc[n_historic - 1, :])
    else:
        prediction_out[...] = pure_prediction

    prediction_out[:n_historic, ...] = historic_stocks_pc

    # TODO delete visualisation
    visualise = True

    if visualise:

        if len(pure_prediction.shape) == 3:
            pure_prediction = np.sum(pure_prediction, axis=2)
            prediction_out = np.sum(prediction_out, axis=2)

        from matplotlib import pyplot as plt
        regions = ['CAZ', 'CHA', 'EUR', 'IND', 'JPN', 'LAM', 'MEA', 'NEU', 'OAS', 'REF', 'SSA', 'USA']
        for r, region in enumerate(regions):
            # plt.plot(gdppc[:, r], pure_prediction[:, r], label=region, linestyle='--')
            plt.plot(gdppc[:, r], prediction_out[:, r], label=region)
        plt.legend()
        plt.xlabel('GDP pc')
        # plt.axvline(x=2022, color='r', linestyle='--')
        plt.ylabel('Stocks pc')
        plt.title('Stocks over GDP')
        plt.show()

        for r, region in enumerate(regions):
            plt.plot(gdppc[:, r], pure_prediction[:, r], label=region)
            # plt.plot(gdppc[:, r], prediction_out[:, r], label=region)
        plt.legend()
        # plt.axvline(x=2022, color='r', linestyle='--')
        plt.xlabel('GDP pc (logarithmic)')
        plt.xscale('log')
        plt.ylabel('Stocks pc')
        plt.title('Stocks over log of GDP')
        plt.show()

        for r, region in enumerate(regions):
            # plt.plot(range(1900, 2101), pure_prediction[:, r], label=region, linestyle='--')
            plt.plot(range(1900, 2101), prediction_out[:, r], label=region)
        plt.axvline(x=2022, color='r', linestyle='--')
        plt.legend()
        plt.xlabel('Year')
        plt.ylabel('Stocks pc')
        plt.title('Stocks over Time')
        plt.show()

        a = 0
