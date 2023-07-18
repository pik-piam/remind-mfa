import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from src.read_data.read_mueller_stocks import load_mueller_stocks
from src.read_data.read_pauliuk_stocks import load_pauliuk_stocks
from src.read_data.read_IMF_gdp import load_imf_gdp
from src.tools.tools import show_and_save, get_steel_category_total
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


def load_and_vis_stocks_mueller(df_gdppc_regions, start_year, end_year, regions):
    df_stocks_regions = load_mueller_stocks(per_capita=True, country_specific=False)
    df_stocks_regions = get_steel_category_total(df_stocks_regions, region_data=True)
    load_and_vis_stocks('Mueller', df_stocks_regions, df_gdppc_regions, start_year, end_year, regions)


def load_and_vis_stocks_pauliuk(df_gdppc_regions, start_year, end_year, regions):
    df_stocks_regions = load_pauliuk_stocks(per_capita=True, country_specific=False)
    df_stocks_regions = get_steel_category_total(df_stocks_regions, region_data=True)
    load_and_vis_stocks('UniFreiburg', df_stocks_regions, df_gdppc_regions, start_year, end_year, regions)


def load_and_vis_stocks(data_src, df_gdp, df_stocks_regions):
    src_in_title = data_src + " Paper"
    src_in_fname = data_src + "data"
    x_gdppc = []
    for index, row in df_gdp.iterrows():
        x_gdppc.append(np.array(row[start_year - 1900:end_year + 1 - 1900]))
    make_stocks_figs_all(df_stocks_regions, x_gdppc, src_in_title, src_in_fname)


def add_gdppc(df_global: pd.DataFrame, df_regional: pd.DataFrame,
              gdppc_global: pd.DataFrame, gdppc_regional: pd.DataFrame):
    df_regional = pd.merge(df_regional, gdppc_regional, on=['region', 'Year'], how='left')
    df_global = pd.merge(df_global, gdppc_global, on='Year', how='left')
    return df_global, df_regional


def make_stocks_figs_all(data_source : str, is_per_capita : bool, df_stocks: pd.DataFrame, df_gdp: pd.DataFrame = None, do_time_plot : bool = True):
    if df_gdp is not None:
        df = pd.concat([df_stocks, df_gdp], keys=['Steel','GDP'], names=['type'])
        make_stocks_fig(df, x_variable='GDP', data_source = data_source, is_per_capita=is_per_capita)
    if do_time_plot:
        years = list(df_stocks.columns)
        df_time = pd.DataFrame([years] * len(df_stocks),
                                         index = df_stocks.index,
                                         columns = df_stocks.columns)
        df = pd.concat([df_stocks, df_time], keys=['Steel', 'Time'], names=['type'])
        make_stocks_fig(df, x_variable='Time', data_source = data_source, is_per_capita=is_per_capita)


def make_stocks_fig(df: pd.DataFrame, x_variable: str, data_source: str, is_per_capita : bool):

    title = f"{data_source} steel stock{' per capita' if is_per_capita else ''} over {x_variable}"
    file_name = f"{data_source}_steel_stock{'_pc' if is_per_capita else ''}_over_{x_variable}"
    plt.figure()
    df = df.reset_index()
    df = df.set_index(['country', 'type'])
    for region, df_reg in df.groupby('country'):
        steel_data = df_reg.loc[region, 'Steel'].values
        x_data = df_reg.loc[region, x_variable].values
        plt.scatter(x_data, steel_data, label=region)

    x_label = 'Time (y)'
    if x_variable=='GDP':
        x_label = f"GDP{' pC' if is_per_capita else ''} (USD 2008)"
    plt.xlabel(x_label)
    plt.ylabel(f"Steel stock{' pC' if is_per_capita else ''} (t)")
    plt.title(title)
    plt.legend(loc='upper left')
    show_and_save(file_name)


"""def make_stocks_fig(df: pd.DataFrame, x_data_list, x_data_type: str, title: str, fname: str):
    plt.figure()
    x_data_idx = 0
    for index, row in df.iterrows():
        region = index
        # avoid eur, ref Pauliuk TODO adapt!
        if title in ["Regional stock over GDP (UniFreiburg Paper)", 'Regional stock over Time (UniFreiburg Paper)']:
            if region in ['EUR', 'REF']:
                x_data_idx += 1
                continue
        stock_data = np.array(row[start_year - 1900:end_year + 1 - 1900])
        x_data = x_data_list[x_data_idx]
        x_data_idx += 1
        plt.scatter(x_data, stock_data,
                    color=REGION_COLORS[region], label=region)
    plt.xlabel(x_data_type)
    plt.ylabel("Steel stock pC (t)")
    plt.title(title)
    plt.legend(loc='upper left')
    show_and_save(fname)"""


if __name__ == "__main__":
    cfg.customize()

    gdppc_regions = load_imf_gdp(per_capita=True, country_specific=False)

    start_year = 1900
    end_year = 2008
    regions = [r for r in REGION_COLORS.keys() if r not in ['World']]
    load_and_vis_stocks_pauliuk(gdppc_regions, start_year, end_year, regions)

    start_year = 1950
    end_year = 2008
    regions = [r for r in REGION_COLORS.keys() if r not in ['World']]
    load_and_vis_stocks_mueller(gdppc_regions, start_year, end_year, regions)
