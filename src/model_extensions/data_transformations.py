from copy import copy
import numpy as np
from scipy.optimize import least_squares

from sodym import (
    StockArray, DynamicStockModel, FlowDrivenStock,
    DimensionSet, NamedDimArray, Process, Parameter
)


def get_new_array(dims: DimensionSet, **kwargs) -> NamedDimArray:
    dims = copy(dims).get_subset(kwargs["dim_letters"]) if "dim_letters" in kwargs else dims
    return NamedDimArray(dims=dims, **kwargs)


def get_subset_transformer(dims: DimensionSet, dim_letters: tuple):
    """Get a Parameter/NamedDimArray which transforms between two dimensions, one of which is a subset of the
    other."""
    assert len(dim_letters) == 2, "Only two dimensions are allowed"
    dims = copy(dims).get_subset(dim_letters)
    assert set(dims[0].items).issubset(set(dims[1].items)) or set(dims[1].items).issubset(
        set(dims[0].items)
    ), f"Dimensions '{dims[0].name}' and '{dims[1].name}' are not subset and superset or vice versa."
    out = NamedDimArray(name=f"transform_{dims[0].letter}_<->_{dims[1].letter}", dims=dims)
    # set all values to 1 if first axis item equals second axis item
    for i, item in enumerate(dims[0].items):
        if item in dims[1].items:
            out.values[i, dims[1].index(item)] = 1
    return out    


def extrapolate_stock(
        historic_stocks: StockArray, dims: DimensionSet,
        parameters: dict[str, Parameter], curve_strategy: str
        ):
    """Performs the per-capita transformation and the extrapolation."""

    # transform to per capita
    pop = parameters['population']
    transform_t_thist  = get_subset_transformer(dims=dims, dim_letters=('t', 'h'))
    historic_pop       = get_new_array(dims=dims, dim_letters=('h','r'))
    historic_gdppc     = get_new_array(dims=dims, dim_letters=('h','r'))
    historic_stocks_pc = get_new_array(dims=dims, dim_letters=('h','r','g'))
    stocks_pc          = get_new_array(dims=dims, dim_letters=('t','r','g'))
    stocks             = get_new_array(dims=dims, dim_letters=('t','r','g'))

    historic_pop[...] = pop * transform_t_thist
    historic_gdppc[...] = parameters['gdppc'] * transform_t_thist
    historic_stocks_pc[...] = historic_stocks / historic_pop

    if curve_strategy == "GDP_regression":
        gdp_regression(historic_stocks_pc.values, parameters['gdppc'].values, stocks_pc.values)
    else:
        raise RuntimeError(f"Prediction strategy {curve_strategy} is not defined. "
                           f"It needs to be 'GDP_regression'.")

    # transform back to total stocks
    stocks[...] = stocks_pc * pop

    #visualize_stock(self, self.parameters['gdppc'], historic_gdppc, stocks, historic_stocks, stocks_pc, historic_stocks_pc)
    return StockArray(**dict(stocks))


def gdp_regression(historic_stocks_pc, gdppc, prediction_out):
    shape_out = prediction_out.shape
    assert len(shape_out) == 3, "Prediction array must have 3 dimensions: Time, Region, Good"
    pure_prediction = np.zeros_like(prediction_out)
    n_historic = historic_stocks_pc.shape[0]
    i_lh = n_historic - 1

    for i_region in range(shape_out[1]):
        for i_good in range(shape_out[2]):

            def fitting_function(prms):
                return (
                    prms[0] / (1. + np.exp(prms[1]/gdppc[:n_historic,i_region]))
                    ) - historic_stocks_pc[:,i_region,i_good]
                # Lagrangian multiplier to ensure matching last point:
                # + prms[2] * prms[0] / (1. + np.exp(prms[1]/gdppc[i_lh,0])) - stocks_pc[-1,0,i] )
            prms_out = least_squares(
                fitting_function,
                x0=np.array([2.*gdppc[i_lh,i_region], historic_stocks_pc[-1,i_region,i_good]]),
                gtol=1.e-12
            )
            assert prms_out.success

            pure_prediction[:,i_region,i_good] = prms_out.x[0] / (
                1. + np.exp(prms_out.x[1]/gdppc[:,i_region])
                )

        # def fitting_function(prms):
        #     return 2.*gdppc[i_lh,0] / (1. + np.exp(prms[0]/gdppc[cfg.i_historic,0])) - stocks_pc[:,0,i]
        # prms_out = least_squares(fitting_function, x0=np.array([stocks_pc[-1,0,i]]))
        # prediction = 2.*gdppc[i_lh,0] / (1. + np.exp(prms_out.x[0]/gdppc[:,0]))

    # fit b to last historic value
    prediction_out[...] = pure_prediction - (
        pure_prediction[i_lh,:,:] - historic_stocks_pc[i_lh,:,:]
        )
    prediction_out[:n_historic,:,:] = historic_stocks_pc

    # if cfg.do_visualize["stock_prediction"]:
    #     visualize_stock_prediction(gdppc, historic_stocks_pc, pure_prediction)
    return


def prepare_stock_for_mfa(
        dims: DimensionSet, stk: DynamicStockModel, prm: dict[str, Parameter], use: Process
    ):
    # We use an auxiliary stock for the prediction step to save dimensions and computation time
    # Therefore, we have to transfer the result to the higher-dimensional stock in the MFA system
    stock_extd = stk.stock * prm['material_shares_in_goods'] * prm['carbon_content_materials']
    inflow = stk.inflow * prm['material_shares_in_goods'] * prm['carbon_content_materials']
    outflow = stk.outflow * prm['material_shares_in_goods'] * prm['carbon_content_materials']
    stock_dims = dims.get_subset(('t','r','g','m','e'))
    stock_extd = StockArray(values=stock_extd.values, name='in_use_stock', dims=stock_dims)
    inflow = StockArray(values=inflow.values, name='in_use_inflow', dims=stock_dims)
    outflow = StockArray(values=outflow.values, name='in_use_outflow', dims=stock_dims)
    stock = FlowDrivenStock(
        stock=stock_extd, inflow=inflow, outflow=outflow, name='in_use', process_name='use',
        process=use,
    )
    return stock
