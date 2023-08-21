import os
import pandas as pd
from src.tools.config import cfg
from src.tools.split_data_into_subregions import split_areas_by_gdp
from src.tools.tools import fill_missing_values_linear
from src.read_data.load_data import load_stocks


def get_worldsteel_trade_factor():
    df_use = _get_worldsteel_use()
    df_production = _get_worldsteel_production()

    # delete production data where no use data is available
    df_production = df_production[df_production.index.isin(df_use.index)]

    df_trade_factor = _calc_trade_factor(df_use, df_production, df_use)
    df_trade_factor = _add_missing_countries_trade_factor(df_trade_factor)
    return df_trade_factor



def get_worldsteel_scrap_trade_factor():
    df_scrap_imports = _get_worldsteel_scrap_imports()
    df_scrap_exports = _get_worldsteel_scrap_exports()
    df_production = _get_worldsteel_production()

    # delete scrap trade_all_areas data where no production data is available
    df_scrap_imports = df_scrap_imports[df_scrap_imports.index.isin(df_production.index)]
    df_scrap_exports = df_scrap_exports[df_scrap_exports.index.isin(df_production.index)]

    df_production = df_production.where(df_production!=0, 1) # TODO : discuss, does this make sense?

    df_scrap_trade_factor = _calc_trade_factor(df_scrap_imports, df_scrap_exports, df_production)
    df_scrap_trade_factor = _add_missing_countries_trade_factor(df_scrap_trade_factor)

    return df_scrap_trade_factor

def _add_missing_countries_trade_factor(df_trade_factor):
    """
    Assume complete import (1) for countries with missing trade_all_areas data.
    """

    df_stocks = load_stocks(country_specific=True)
    all_countries = df_stocks.index.get_level_values(0).unique()
    missing_countries = all_countries.difference(df_trade_factor.index)
    df_missing_countries = pd.DataFrame(1, missing_countries, df_trade_factor.columns)
    df_trade_factor = pd.concat([df_trade_factor, df_missing_countries])

    return df_trade_factor

def _calc_trade_factor(df_minuend, df_subtrahend, df_quotient):
    df_trade_diff = df_minuend.sub(df_subtrahend, fill_value=0)
    df_trade_factor = df_trade_diff.div(df_quotient, fill_value=0)

    # neglect where more is prouced/imported than used/produced
    # TODO : Include or not ??
    # df_trade_factor = df_trade_factor.where(df_trade_factor < 1, 1)

    return df_trade_factor


def _get_worldsteel_use():
    df_use = _read_worldsteel_original_use()
    df_iso3 = _read_worldsteel_iso3_map()
    areas_to_split = ['Joint Serbia and Montenegro', 'South African C.U. (1)', 'Belgium-Luxembourg']
    df_use = _clean_worldsteel_data(df_use, df_iso3, areas_to_split)
    return df_use


def _get_worldsteel_production():
    df_production = _read_worldsteel_original_production()
    df_iso3 = _read_worldsteel_iso3_map()
    df_production = _clean_worldsteel_data(df_production, df_iso3, ['Joint Serbia and Montenegro'])
    df_production = df_production.drop(index='ARM')  # faulty data for Armenia
    return df_production


def _get_worldsteel_scrap_exports():
    df_scrap_exports = _read_worldsteel_original_scrap_exports()
    df_iso3 = _read_worldsteel_scrap_iso3_map()
    df_scrap_exports = pd.merge(df_iso3, df_scrap_exports, on='country_name')
    df_scrap_exports = df_scrap_exports.drop(columns=['country_name'])
    df_scrap_exports = df_scrap_exports.set_index('country')

    df_scrap_exports *= 1000

    df_scrap_exports = fill_missing_values_linear(df_scrap_exports)

    return df_scrap_exports


def _get_worldsteel_scrap_imports():
    df_scrap_imports = _read_worldsteel_original_scrap_imports()
    df_iso3 = _read_worldsteel_scrap_iso3_map()
    df_scrap_imports = pd.merge(df_iso3, df_scrap_imports, on='country_name')
    df_scrap_imports = df_scrap_imports.drop(columns=['country_name'])
    df_scrap_imports = df_scrap_imports.set_index('country')

    df_scrap_imports *= 1000

    df_scrap_imports = fill_missing_values_linear(df_scrap_imports)

    return df_scrap_imports


def _clean_worldsteel_data(df: pd.DataFrame, df_iso3: pd.DataFrame, areas_to_split : list):
    df = df.set_index('country_name')
    df = _merge_worldsteel_serbia_montenegro(df)
    df = pd.merge(df_iso3, df, left_on='country_name', right_index=True)
    df = df.drop(columns=['country_name'])
    df = df.set_index('country')
    df = split_areas_by_gdp(areas_to_split, df, df_iso3)
    df = df.replace('...', pd.NA)
    df *= 1000
    df = fill_missing_values_linear(df)
    return df


def _merge_worldsteel_serbia_montenegro(df_original):
    serbia_data = df_original.loc['Serbia']
    montenegro_data = df_original.loc['Montenegro']
    serbia_and_montenegro_data = df_original.loc['Serbia and Montenegro']
    fryugoslavia_data = df_original.loc['F.R. Yugoslavia']

    df_original = df_original.drop(index=['Serbia', 'Montenegro', 'Serbia and Montenegro', 'F.R. Yugoslavia'])

    joint_data = serbia_data + montenegro_data
    joint_data = joint_data.add(serbia_and_montenegro_data, fill_value=0)
    joint_data = joint_data.add(fryugoslavia_data, fill_value=0)

    df_original.loc['Joint Serbia and Montenegro'] = joint_data

    return df_original


def _read_worldsteel_original_scrap_exports():
    scrap_path = os.path.join(cfg.data_path, 'original', 'worldsteel', 'Scrap_Trade_2018-2017.xlsx')
    df_scrap_exports = pd.read_excel(
        io=scrap_path,
        engine='openpyxl',
        sheet_name='Exports of Scrap')
    return df_scrap_exports


def _read_worldsteel_original_scrap_imports():
    scrap_path = os.path.join(cfg.data_path, 'original', 'worldsteel', 'Scrap_Trade_2018-2017.xlsx')
    df_scrap_imports = pd.read_excel(
        io=scrap_path,
        engine='openpyxl',
        sheet_name='Imports of Scrap')
    return df_scrap_imports


def _read_worldsteel_iso3_map():
    iso3_map_path = os.path.join(cfg.data_path, 'original', 'worldsteel', 'WorldSteel_countries.csv')
    df = pd.read_csv(iso3_map_path)
    return df


def _read_worldsteel_scrap_iso3_map():
    iso3_map_path = os.path.join(cfg.data_path, 'original', 'worldsteel', 'WorldSteel_scrap_countries.csv')
    df = pd.read_csv(iso3_map_path)
    return df


def _read_worldsteel_original_production():
    production_path = os.path.join(cfg.data_path, 'original', 'worldsteel', "Steel_Statistical_Yearbook_combined.ods")
    df_production = pd.read_excel(production_path,
                                  sheet_name='Total Production of Crude Steel',
                                  engine='odf',
                                  usecols='A:AC')
    df_production = df_production.rename(columns={'country': 'country_name'})

    return df_production


def _read_worldsteel_original_use():
    use_path = os.path.join(cfg.data_path, 'original', 'worldsteel',
                            "Steel_Statistical_Yearbook_combined.ods")
    df_use = pd.read_excel(use_path,
                           sheet_name='Apparent Steel Use (Crude Steel Equivalent)',
                           engine='odf',
                           usecols='A:AC')
    df_use = df_use.rename(columns={'country': 'country_name'})
    return df_use


def _test():
    df_trade_factor = get_worldsteel_trade_factor()
    df_scrap_trade_factor = get_worldsteel_scrap_trade_factor()
    print(df_trade_factor)
    print(df_scrap_trade_factor)

    print(list(df_scrap_trade_factor.loc['HRV']))

if __name__ == "__main__":
    _test()