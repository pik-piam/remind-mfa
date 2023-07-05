import matplotlib.pyplot as plt
import pandas as pd
from src.read_data.read_mueller_stocks import load_mueller_stocks, transform_dict_to_dfs
from src.read_data.read_pauliuk_stocks import load_pauliuk_to_dfs
from src.read_data.read_IMF_gdp import load_imf_gdp, gdppc_dict_to_dfs
from src.tools.tools import show_and_save, Years
from src.tools.config import cfg


REGION_COLORS = {'LAM': 'green',
                 'OAS': 'red',
                 'SSA': 'yellow',
                 'EUR': 'blue',
                 'NEU': 'black',
                 'MEA': 'brown',
                 'REF': 'orange',
                 'CAZ': 'purple',
                 'CHA': 'gray',
                 'IND': 'lightgreen',
                 'JPN': 'lightblue',
                 'USA': 'cyan',
                 'World': 'blue'}


def load_and_vis_stocks_pauliuk(gdppc_global, gdppc_regional,
                                start_year, end_year, regions):

    years = Years(start_year, end_year, 1900)
    df_global, df_regional = load_pauliuk_to_dfs(years)
    df_regional = df_regional.query("region in @regions")
    df_global, df_regional = add_gdppc(df_global, df_regional,
                                       gdppc_global, gdppc_regional)
    make_stocks_figs_all(df_global, df_regional, 'Uni Freiburg database', 'freiburgdata')


def load_and_vis_stocks_mueller(gdppc_global, gdppc_regional,
                                start_year, end_year, regions):

    years = Years(start_year, end_year, 1900)
    stocks = load_mueller_stocks()
    df_global, df_regional = transform_dict_to_dfs(stocks, years)
    df_regional = df_regional.query("`region` in @regions")
    df_global, df_regional = add_gdppc(df_global, df_regional,
                                       gdppc_global, gdppc_regional)
    make_stocks_figs_all(df_global, df_regional, 'Mueller Paper', 'muellerdata')


def add_gdppc(df_global: pd.DataFrame, df_regional: pd.DataFrame,
              gdppc_global: pd.DataFrame, gdppc_regional: pd.DataFrame):

    df_regional = pd.merge(df_regional, gdppc_regional, on=['region', 'Year'], how='left')
    df_global = pd.merge(df_global, gdppc_global, on='Year', how='left')
    return df_global, df_regional


def make_stocks_figs_all(df_global, df_regional, src_in_title, src_in_fname):
    make_stocks_fig(df_global, 'GDP pC (USD 2005)',
                    f"Global stock over GDP ({src_in_title})",
                    f"stock_gdp_global_{src_in_fname}")
    make_stocks_fig(df_global, 'Year',
                    f"Global stock over Time ({src_in_title})",
                    f"stock_time_global_{src_in_fname}")
    make_stocks_fig(df_regional, 'GDP pC (USD 2005)',
                    f"Regional stock over GDP ({src_in_title})",
                    f"stock_gdp_regional_{src_in_fname}")
    make_stocks_fig(df_regional, 'Year',
                    f"Regional stock over Time ({src_in_title})",
                    f"stock_time_regional_{src_in_fname}")
    return


def make_stocks_fig(df: pd.DataFrame, x_variable: str, title: str, fname: str):
    plt.figure()
    for region, df_reg in df.groupby('region'):
        plt.scatter(df_reg[x_variable].values, df_reg['stock_pc'].values,
                    color=REGION_COLORS[region], label=region)
    plt.xlabel(x_variable)
    plt.ylabel("Steel stock pC (t)")
    plt.title(title)
    plt.legend(loc='upper left')
    show_and_save(fname)


if __name__ == "__main__":

    cfg.customize()

    gdppc_dict = load_imf_gdp()
    gdppc_global, gdppc_regional = gdppc_dict_to_dfs(gdppc_dict)

    start_year = 1900
    end_year = 2008
    regions = [r for r in REGION_COLORS.keys() if r not in ['World']]
    load_and_vis_stocks_pauliuk(gdppc_global, gdppc_regional,
                                start_year, end_year, regions)

    start_year = 1950
    end_year = 2008
    regions = [r for r in REGION_COLORS.keys() if r not in ['World']]
    load_and_vis_stocks_mueller(gdppc_global, gdppc_regional, start_year, end_year, regions)
