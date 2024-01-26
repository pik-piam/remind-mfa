import numpy as np
import scipy
import sys
# from scipy.optimize import least_squares
from src.tools.config import cfg
from src.read_data.load_data import load_data
from src.visualisation.visualize import visualize_stock_prediction


def predict_duerrwaechter(historic_stocks_pc):

    gdppc = load_data('gdp', percapita=True)

    # individual fix for 2020 to avoid negative production
    gdppc[2020-cfg.start_year,:] = (gdppc[2019-cfg.start_year,:] + gdppc[2021-cfg.start_year,:]) / 2.

    pure_prediction = np.ndarray(shape=(cfg.n_years, cfg.n_regions, cfg.n_use_categories))
    prediction = np.ndarray(shape=(cfg.n_years, cfg.n_regions, cfg.n_use_categories))
    i_lh = cfg.i_historic[-1] # last historic year

    for i in range(cfg.n_use_categories):

        def fitting_function(prms):
            return prms[0] / (1. + np.exp(prms[1]/gdppc[cfg.i_historic,0])) - historic_stocks_pc[:,0,i]
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


