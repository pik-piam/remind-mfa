import numpy as np
import flodym as fd

from simson.common.data_transformations import smooth_np


S_IND = np.array([0.47, 0.32, 0.10, 0.11])
S_USA = np.array([0.47, 0.10, 0.13, 0.30])
GDPPC_IND = 2091
GDPPC_USA = 43458


def calc_demand_sector_splits_via_gdp(gdppc):
    # this is just the values we plot over
    # this is the core of the calculation: sigmoid over gdppc
    # -3 and +3 are x-values where the sigmoid has almost reached its limits (0 and 1)
    def alpha(gdppc):
        x = -3. + 6. * (np.log(gdppc) - np.log(GDPPC_IND)) / (np.log(GDPPC_USA) - np.log(GDPPC_IND))
        return 1. / (1. + np.exp(-x))

    a = alpha(gdppc.values)
    # stretch a such that it is 0 at GDPPC_IND and 1 at GDPPC_USA (actually overhsooting/extrpolating their values slightly)
    a_ind = alpha(GDPPC_IND)
    a_usa = alpha(GDPPC_USA)
    a = (a - a_ind) / (a_usa - a_ind)

    # s = a*S_USA + (1-a)*S_IND
    # with correct numpy dimensions
    sector_split = a[:, :, np.newaxis] * S_USA + (1 - a[:, :, np.newaxis]) * S_IND
    return sector_split


def calc_stock_sector_splits(dims, gdp, lifetime_mean, historical_sector_splits):
    fin_sector_split = calc_final_stock_sector_splits(lifetime_mean)[0]
    # choose only first region, TODO: implement check that accounts for different regions
    general_splits = calc_general_stock_sector_split(fin_sector_split, gdp)

    # merge historical and general split with sigmoid scaling

    sector_splits = merge_historical_and_general_split(historical_sector_splits, general_splits)

    # normalise
    sector_splits /= sector_splits.sum(axis=-1)[:, :, np.newaxis]

    # convert to NamedDimArray
    sector_splits_nda = fd.StockArray.from_dims_superset(dims_superset=dims, dim_letters=('t', 'r', 'g'))
    sector_splits_nda.values = sector_splits

    return sector_splits_nda


def merge_historical_and_general_split(historical_sector_splits, general_split):
    # prepare simply extrapolation of historical sector splits by assuming same split as last year
    extrapolated_historical_sector_splits = np.ones_like(general_split)
    extrapolated_historical_sector_splits *= historical_sector_splits[-1]
    extrapolated_historical_sector_splits[:123] = historical_sector_splits

    # smooth both curves with sigmoid smoothing
    sector_split = smooth_np(extrapolated_historical_sector_splits, general_split,
                             type='sigmoid', start_idx=historical_sector_splits.shape[0])
    return sector_split


def calc_general_stock_sector_split(fin_sector_split, gdp):
    LOWER_END = 1000
    UPPER_END = 100000

    first_sector_split = np.array([0.47, 0.33, 0.098, 0.102])

    def alpha(gdp):
        x = -3. + 6. * (np.log10(gdp) - np.log10(LOWER_END)) / (np.log10(UPPER_END) - np.log10(LOWER_END))
        return 1. / (1. + np.exp(-x))

    a = alpha(gdp)
    # stretch a such that it is 0 at GDPPC_IND and 1 at GDPPC_USA (actually overhsooting/extrpolating their values slightly)
    a_first = alpha(LOWER_END)
    a_fin = alpha(UPPER_END)
    a = (a - a_first) / (a_fin - a_first)
    sector_split = a[:, :, np.newaxis] * fin_sector_split + (1 - a[:, :, np.newaxis]) * first_sector_split

    # TODO delete visualisation
    visualise = False
    if visualise:
        gdppc = np.linspace(-5000, 120000, 300)
        log_gdppc = np.linspace(3, 5, 300)
        gdppc = 10. ** log_gdppc
        a = alpha(gdppc)
        # stretch a such that it is 0 at GDPPC_IND and 1 at GDPPC_USA (actually overhsooting/extrpolating their values slightly)
        a_first = alpha(LOWER_END)
        a_fin = alpha(UPPER_END)
        a = (a - a_first) / (a_fin - a_first)
        sector_split = a[:, np.newaxis] * fin_sector_split + (1 - a[:, np.newaxis]) * first_sector_split
        import plotly.express as px
        import pandas as pd
        names = ['Construction', 'Machinery', 'Products', 'Transport']
        df = pd.DataFrame(sector_split, columns=names)
        df['gdppc'] = gdppc
        fig = px.line(df, x='gdppc', y=names)
        # vertcial lines at LOWER_END and UPPER_END
        # fig.add_vline(x=LOWER_END, line_dash="dash", line_color="green")
        # fig.add_vline(x=UPPER_END, line_dash="dash", line_color="red")
        # fig.update_layout(xaxis_type="log")
        fig.show()

    return sector_split


def calc_final_stock_sector_splits(lifetime_mean):
    b = 1 / (1 + np.e ** 3)
    a = S_USA + (b / (1 - 2 * b)) * (S_USA - S_IND)
    dividend = np.einsum('rg,g->rg', lifetime_mean, a)
    divisor = dividend.sum(axis=-1)

    stock_share = np.einsum('rg,r->rg', dividend, 1 / divisor)

    return stock_share
