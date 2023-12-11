import os
import pandas as pd
from src.tools.config import cfg
from src.tools.tools import fill_missing_values_linear


def get_usgs_steel_prices():
    df_original = _read_usgs_original_steel_prices()
    df_original = _clean_usgs_original_prices(df_original)
    df = fill_missing_values_linear(df_original)  # steel price stays constant after 2010

    return df


def get_usgs_scrap_prices():
    df_original = _read_usgs_original_scrap_prices()
    df_original = _clean_usgs_original_prices(df_original)
    df = fill_missing_values_linear(df_original)  # scrap price stays constant before 1934 and after 2019

    return df


# -- READ AND CLEAN HELPER FUNCTIONS --


def _clean_usgs_original_prices(df_original):
    df_original = df_original.rename(columns={'Unit value (98$/t)': 'Steel Price'})
    df_original = df_original.set_index('Year')
    df_original = df_original.transpose()
    df_original.columns.name = None

    return df_original


def _read_usgs_original_steel_prices():
    steel_price_path = os.path.join(cfg.data_path, 'original', 'usgs', "ds140-iron-steel-2019.xlsx")
    df_original = pd.read_excel(
        steel_price_path,
        engine='openpyxl',
        sheet_name='Steel',
        skiprows=5,
        nrows=111,
        usecols=['Year', 'Unit value (98$/t)'])

    return df_original


def _read_usgs_original_scrap_prices():
    scrap_price_path = os.path.join(cfg.data_path, 'original', 'usgs', "ds140-iron-steel-scrap-2019.xlsx")
    df_original = pd.read_excel(
        scrap_price_path,
        engine='openpyxl',
        sheet_name='Iron and Steel Scrap',
        skiprows=4,
        nrows=86,
        usecols=['Year', 'Unit value (98$/t)'])

    return df_original


# -- TEST FILE FUNCTION --

def _test():
    from src.read_data.load_data import load_steel_prices
    df = load_steel_prices('USGS')
    print('\nSteel Prices:\n')
    print(df)
    from src.read_data.load_data import load_scrap_prices
    df = load_scrap_prices('USGS')
    print('\nScrap Prices:\n')
    print(df)


if __name__ == "__main__":
    _test()
