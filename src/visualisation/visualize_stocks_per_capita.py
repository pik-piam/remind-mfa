import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from src.read_data.read_mueller_stocks import load_mueller_stocks
from src.read_data.read_pauliuk_stocks import load_pauliuk_stocks
from src.read_data.read_IMF_gdp import load_imf_gdp
from src.tools.tools import show_and_save, Years, get_steel_category_total
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
    load_and_vis_stocks('Mueller',df_stocks_regions, df_gdppc_regions, start_year, end_year, regions)

def load_and_vis_stocks_pauliuk(df_gdppc_regions, start_year, end_year, regions):
    df_stocks_regions = load_pauliuk_stocks(per_capita=True, country_specific=False)
    df_stocks_regions = get_steel_category_total(df_stocks_regions, region_data=True)
    load_and_vis_stocks('UniFreiburg',df_stocks_regions, df_gdppc_regions, start_year, end_year, regions)


def load_and_vis_stocks(data_src, df_stocks_regions, df_gdppc_regions, start_year, end_year, regions):
    src_in_title = data_src + " Paper"
    src_in_fname = data_src + "data"
    years = range(start_year, end_year+1)
    x_years = [years for i in range(len(regions))]
    x_gdppc = []
    for index, row in df_gdppc_regions.iterrows():
        x_gdppc.append(np.array(row[start_year-1900:end_year+1-1900]))
    make_stocks_figs_all(df_stocks_regions, x_years, x_gdppc, src_in_title, src_in_fname)


def add_gdppc(df_global: pd.DataFrame, df_regional: pd.DataFrame,
              gdppc_global: pd.DataFrame, gdppc_regional: pd.DataFrame):

    df_regional = pd.merge(df_regional, gdppc_regional, on=['region', 'Year'], how='left')
    df_global = pd.merge(df_global, gdppc_global, on='Year', how='left')
    return df_global, df_regional


def make_stocks_figs_all(df_stocks_regions, x_years, x_gdppc, src_in_title, src_in_fname):
    make_stocks_fig(df_stocks_regions, x_gdppc, 'GDP pC (USD 2005)',
                    f"Regional stock over GDP ({src_in_title})",
                    f"stock_gdp_regional_{src_in_fname}")
    make_stocks_fig(df_stocks_regions, x_years, 'Year',
                    f"Regional stock over Time ({src_in_title})",
                    f"stock_time_regional_{src_in_fname}")
    return


def make_stocks_fig(df: pd.DataFrame, x_data, x_variable: str, title: str, fname: str):
    plt.figure()
    x_data_idx = 0
    for index, row in df.iterrows():
        region = index
        #avoid eur, ref Pauliuk TODO adapt!
        if title in ["Regional stock over GDP (UniFreiburg Paper)", 'Regional stock over Time (UniFreiburg Paper)']:
            if region in ['EUR', 'REF']:
                x_data_idx+=1
                continue
        stock_data = np.array(row[start_year-1900:end_year+1-1900])
        x_data_row = x_data[x_data_idx]
        x_data_idx +=1
        plt.scatter(x_data_row, stock_data,
                    color=REGION_COLORS[region], label=region)
    plt.xlabel(x_variable)
    plt.ylabel("Steel stock pC (t)")
    plt.title(title)
    plt.legend(loc='upper left')
    show_and_save(fname)


if __name__ == "__main__":

    cfg.customize()

    gdppc_regions = load_imf_gdp(per_capita=True, country_specific=False)

    start_year = 1900
    end_year = 2008
    regions = [r for r in REGION_COLORS.keys() if r not in ['World']]
    load_and_vis_stocks_pauliuk(gdppc_regions,start_year, end_year, regions)

    start_year = 1950
    end_year = 2008
    regions = [r for r in REGION_COLORS.keys() if r not in ['World']]
    load_and_vis_stocks_mueller(gdppc_regions, start_year, end_year, regions)
