import numpy as np
import scipy
from src.tools.config import cfg
from src.new_odym.named_dim_arrays import NamedDimArray
from src.tools.visualize import visualize_stock_prediction

def predict_stocks(mfa, historic_stocks):
    """
    Calculates In-use steel stock per capita data based on GDP pC using approach given in
    config file (e.g. Pauliuk or Pehl).
    Optionally creates plot to show predict for Germany.
    :return: Steel data for the years 1900-2100, so BOTH present and past using predict
    approach given in config file.
    """

    # transform to per capita
    pop = NamedDimArray('population', ('t','r'), parent_alldims=mfa.dims).load_data()
    historic_pop = pop[:mfa.historic_years.len, :]
    historic_stocks_pc = np.einsum(f'trc,tr->trc', historic_stocks, 1./historic_pop)

    strategy=cfg.curve_strategy
    if strategy == "GDP_regression":
        stocks_pc = gdp_regression(mfa, historic_stocks_pc)
    else:
        raise RuntimeError(f"Prediction strategy {strategy} is not defined. "
                           f"It needs to be 'GDP_regression'.")

    # transform back to total stocks
    stocks = np.einsum(f'trc,tr->trc', stocks_pc, pop)

    return stocks


def gdp_regression(mfa, historic_stocks_pc):

    gdppc = NamedDimArray('gdppc', ('t','r'), parent_alldims=mfa.dims).load_data()

    # individual fix for 2020 to avoid negative production
    gdppc[mfa.years.index(2020),:] = (gdppc[mfa.years.index(2019),:] + gdppc[mfa.years.index(2021),:]) / 2.

    pure_prediction = np.ndarray(shape=mfa.dims.shape(('t','r','g')))
    prediction = np.ndarray(shape=mfa.dims.shape(('t','r','g')))
    i_lh = mfa.i_historic[-1] # last historic year

    for i in range(mfa.dims['Good'].len):

        def fitting_function(prms):
            return prms[0] / (1. + np.exp(prms[1]/gdppc[mfa.i_historic,0])) - historic_stocks_pc[:,0,i]
                    # Lagrangian multiplier to ensure matching last point:
                    # + prms[2] * prms[0] / (1. + np.exp(prms[1]/gdppc[i_lh,0])) - stocks_pc[-1,0,i] )
        prms_out = scipy.optimize.least_squares(fitting_function, x0=np.array([2.*gdppc[i_lh,0],historic_stocks_pc[-1,0,i]]), gtol=1.e-12)
        assert prms_out.success

        pure_prediction[:,0,i] = prms_out.x[0] / (1. + np.exp(prms_out.x[1]/gdppc[:,0]))


        # def fitting_function(prms):
        #     return 2.*gdppc[i_lh,0] / (1. + np.exp(prms[0]/gdppc[cfg.i_historic,0])) - stocks_pc[:,0,i]
        # prms_out = scipy.optimize.least_squares(fitting_function, x0=np.array([stocks_pc[-1,0,i]]))
        # prediction = 2.*gdppc[i_lh,0] / (1. + np.exp(prms_out.x[0]/gdppc[:,0]))

    # fit b to last historic value
    prediction = pure_prediction - (pure_prediction[i_lh,0,:] - historic_stocks_pc[i_lh,0,:])
    prediction[:i_lh+1,:,:] = historic_stocks_pc

    if cfg.do_visualize["stock_prediction"]:
        visualize_stock_prediction(gdppc, historic_stocks_pc, pure_prediction)

    return prediction
