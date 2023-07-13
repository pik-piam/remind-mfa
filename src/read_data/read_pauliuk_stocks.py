import os
import pandas as pd
from src.tools.config import cfg
from src.curve.predict_steel import get_stock_prediction_pauliuk_for_pauliuk
from src.tools.tools import read_processed_data
from src.tools.tools import transform_per_capita
from src.tools.tools import group_country_data_to_regions


def load_pauliuk_stocks(country_specific=False, per_capita=True):
    if country_specific:
        df_country = _load_pauliuk_steel_countries()
        if not per_capita:
            df_country = transform_per_capita(df_country, total_from_per_capita=True, country_specific=True)
        return df_country
    else:  # region specific
        df_region = _load_pauliuk_steel_regions()
        if not per_capita:
            df_region = transform_per_capita(df_region, total_from_per_capita=True, country_specific=False)
        return df_region


# -- MAIN DATA LOADING FUNCTIONS --


def _load_pauliuk_steel_regions():
    steel_regions_path = os.path.join(cfg.data_path, 'processed', 'pauliuk_steel_regions.csv')
    if os.path.exists(steel_regions_path) and not cfg.recalculate_data:
        df = read_processed_data(steel_regions_path)
        df = df.reset_index()
        df = df.set_index(['region', 'category'])
    else:  # recalculate and store
        df_by_country = _load_pauliuk_steel_countries()
        df = group_country_data_to_regions(df_by_country, is_per_capita=True, group_by_subcategories=True)
        df.to_csv(steel_regions_path)
    return df


def _load_pauliuk_steel_countries():
    pauliuk_steel_countries_path = os.path.join(cfg.data_path, 'processed', 'pauliuk_steel_countries.csv')
    if os.path.exists(pauliuk_steel_countries_path) and not cfg.recalculate_data:
        df = read_processed_data(pauliuk_steel_countries_path)
        df = df.reset_index()
        df = df.set_index(['country', 'category'])
    else:  # recalculate and store
        df = _get_pauliuk_stocks()
        df.to_csv(pauliuk_steel_countries_path)
    return df


# -- DATA ASSEMBLY FUNCTIONS --

def _get_pauliuk_stocks():
    df_current = get_current_pauliuk_stocks()
    df = get_stock_prediction_pauliuk_for_pauliuk(df_current)
    return df


def get_current_pauliuk_stocks():
    df_original = read_pauliuk_original()
    df_original = clean_pauliuk(df_original)
    df_iso3_map = read_pauliuk_iso3_map()
    df_original = _normalize_pauliuk_original(df_original, df_iso3_map)

    return df_original


def _normalize_pauliuk_original(df_original, df_iso3_map):
    df_original = df_original.pivot(index=['country_name', 'category'], columns='year', values='stock')
    df_original = df_original.reset_index()
    df = pd.merge(df_iso3_map, df_original, on='country_name')
    df = df.drop(columns='country_name')
    df = df.set_index(['country', 'category'])

    return df


def clean_pauliuk(df_pauliuk):
    # clean up
    df_pauliuk = df_pauliuk.rename(columns={'aspect 3 : time': 'year',
                                            'aspect 4 : commodity': 'category_description',
                                            'aspect 5 : region': 'country_name',
                                            'value': 'stock'})
    df_pauliuk['stock'] = df_pauliuk['stock'] * 1000.
    df_cat_names = pd.DataFrame.from_dict({
        'category_description': ['vehicles and other transport equipment',
                                 'industrial machinery',
                                 'buildings - construction - infrastructure',
                                 'appliances - packaging - other'],
        'category': cfg.subcategories
    })

    df_pauliuk = pd.merge(df_cat_names, df_pauliuk, on='category_description')
    df_pauliuk = df_pauliuk.drop(columns=['category_description'])
    return df_pauliuk


def read_pauliuk_original():
    pauliuk_data_path = os.path.join(cfg.data_path, 'original', 'unifreiburg_ie_db',
                                     '2_IUS_steel_200R_4Categories.xlsx')
    df_pauliuk = pd.read_excel(
        io=pauliuk_data_path,
        engine='openpyxl',
        sheet_name='Data',
        usecols=['aspect 3 : time', 'aspect 4 : commodity', 'aspect 5 : region', 'value'])

    return df_pauliuk


def read_pauliuk_iso3_map():
    pauliuk_iso3_path = os.path.join(cfg.data_path, 'original', 'unifreiburg_ie_db', 'Pauliuk_countries.csv')
    df_iso3 = pd.read_csv(pauliuk_iso3_path)

    df_iso3 = df_iso3.rename(columns={
        'country': 'country_name',
        'iso3c': 'country'
    })

    return df_iso3


# -- TEST FILE FUNCTION --

def _test():
    df = _get_pauliuk_stocks()
    print(df)


if __name__ == "__main__":
    _test()
