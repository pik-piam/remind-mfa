import os
import pandas as pd
from src.read_data.read_IMF_gdp import get_past_according_to_gdppc_estimates
from src.tools.tools import transform_per_capita, fill_missing_values_linear
from src.tools.config import cfg
from src.read_data.load_data import load_gdp


def get_mueller_country_stocks():
    df_current = _get_current_mueller_stocks()
    df_past = get_past_according_to_gdppc_estimates(df_current)
    df = df_past.merge(df_current, on='country')
    df = fill_missing_values_linear(df, start_year=cfg.start_year, end_year=2008)

    df = _get_stock_by_subcategory(df)
    df[df < 0] = 0
    return df


# -- DATA ASSEMBLY FUNCTIONS --


def _get_current_mueller_stocks(normalize=True):
    df_mueller = _read_mueller_originial()
    df_iso3_map = read_mueller_iso3_map()

    df = pd.merge(df_iso3_map, df_mueller, left_on='country_name', right_on='Country')
    df = df.drop(columns=['country_name', 'Country'])
    df = df.set_index('country')

    if normalize:
        df_areas_to_normalize = _get_areas_to_normalize(df_iso3_map)
        df = _normalize_mueller_stocks(df, df_areas_to_normalize)

    return df


def _get_stock_by_subcategory(df_stocks):
    df_splits = _read_pauliuk_splits()
    df_splits = _normalize_sector_splits(df_splits)
    df_stocks = pd.merge(df_splits, df_stocks, on='country')
    df_stocks.iloc[:, 3:] = df_stocks.iloc[:, 3:].multiply(df_stocks['split_value'], axis='index')
    df_stocks = df_stocks.drop(columns=['split_value'])
    df_stocks = df_stocks.set_index(['country', 'category'])

    return df_stocks


# -- NORMALISATION FUNCTIONS --


def _normalize_sector_splits(df_splits):
    df_splits = _normalize_sector_splits_add_missing_countries(df_splits)

    # add iso3 codes, clean up

    df_iso3c = read_mueller_iso3_map()
    df_splits = pd.merge(df_iso3c, df_splits, left_on='country_name', right_on='Country name')
    df_splits = df_splits.drop(columns=['country_name', 'Country name'])
    df_splits = df_splits.set_index('country')

    # restructure

    df_splits = df_splits.stack()
    df_splits = df_splits.reset_index(name='split_value')
    df_splits = df_splits.rename(columns={'level_1': 'category'})

    return df_splits


def _normalize_sector_splits_add_missing_countries(df_splits):
    splits_frabenelux = list(df_splits.loc[14])[1:]  # France+Benelux in origingal file
    splits_taiwan = [0.23, 0.22, 0.42, 0.13]
    # assume distribution average of China [0.11,0.32,0.47,0.1], South Korea [0.29,0.25,0.31,0.15]
    # and Japan [0.3,0.1,0.47,0.13]
    row_index = len(df_splits)
    df_splits.loc[row_index] = ['France'] + splits_frabenelux
    df_splits.loc[row_index + 1] = ['Netherlands'] + splits_frabenelux
    df_splits.loc[row_index + 2] = ['Belgium-Luxembourg'] + splits_frabenelux
    df_splits.loc[row_index + 3] = ['Taiwan'] + splits_taiwan

    return df_splits


def _normalize_mueller_stocks(df_stocks_pc, df_areas):
    # parameters + data
    years_considered = list(range(1950, 2009))
    df_gdp = load_gdp(country_specific=True, per_capita=False)
    df_gdp = df_gdp[years_considered]
    countries_considered = df_areas.index

    # process
    df_gdp = pd.merge(df_areas, df_gdp, on='country')
    df_area_gdp_share = _get_gdp_shares_in_areas(df_gdp, years_considered)
    df_stocks_area_totals = _get_stocks_with_area_sums(df_stocks_pc, df_areas, countries_considered)
    df_new_stocks = df_stocks_area_totals * df_area_gdp_share
    df_new_stocks_pc = transform_per_capita(df_new_stocks, total_from_per_capita=False, country_specific=True)
    df_stocks_pc[df_stocks_pc.index.isin(countries_considered)] = df_new_stocks_pc

    return df_stocks_pc


def _get_areas_to_normalize(df_iso3_map: pd.DataFrame):
    areas_to_normalize = ['Belgium-Luxembourg', 'Czechoslovakia', 'Fmr USSR',
                          'Fmr Yugoslavia', 'Neth Antilles', 'So. African Customs Union']
    df_areas = pd.DataFrame.from_dict({
        'area': areas_to_normalize
    })
    df_areas = pd.merge(df_areas, df_iso3_map, left_on='area', right_on='country_name')
    df_areas = df_areas.drop(columns=['country_name'])
    df_areas = df_areas.set_index('country')

    return df_areas


# -- GROUPING CALCULATION FUNCTIONS --


def _get_gdp_shares_in_areas(df_gdp: pd.DataFrame, years_considered: list):
    gk_gdp = df_gdp.groupby('area')
    df_gdp_sums = gk_gdp[years_considered].transform('sum', numeric_only=True)
    df_gdp[years_considered] = df_gdp[years_considered] / df_gdp_sums
    df_area_gdp_share = df_gdp
    df_area_gdp_share = df_area_gdp_share.drop(columns=['area'])

    return df_area_gdp_share


def _get_stocks_with_area_sums(df_stocks_pc, df_areas, countries_considered):
    df_relevant_stocks_pc = df_stocks_pc[df_stocks_pc.index.isin(countries_considered)]
    df_relevant_stocks = transform_per_capita(df_relevant_stocks_pc, total_from_per_capita=True, country_specific=True)
    df_relevant_stocks = pd.merge(df_areas, df_relevant_stocks, on='country')
    gk_relevant_stocks = df_relevant_stocks.groupby('area')
    df_relevant_stocks_sums = gk_relevant_stocks.transform('sum', numeric_only=True)

    return df_relevant_stocks_sums


# -- READ RAW DATA FUNCTIONS --


def _read_mueller_originial():
    mueller_stock_path = os.path.join(cfg.data_path, 'original', 'Mueller',
                                      "Mueller_2013_CarbonEmissions_InfrastructureDevelopment_SI2.xlsx")
    df_stocks = pd.read_excel(mueller_stock_path,
                              engine='openpyxl',
                              sheet_name='steel stock per cap med',
                              skiprows=2,
                              usecols='A:BH')  # ['Country'] + years)

    return df_stocks


def read_mueller_iso3_map():
    mueller_iso3_path = os.path.join(cfg.data_path, 'original', 'Mueller', 'Mueller_countries.csv')
    df_iso3 = pd.read_csv(mueller_iso3_path)

    df_iso3 = df_iso3.rename(columns={
        'country': 'country_name',
        'iso3c': 'country'
    })

    return df_iso3


def _read_pauliuk_splits():
    splits_path = os.path.join(cfg.data_path, 'original', 'Pauliuk', 'Supplementary_Table_23.xlsx')
    df_splits = pd.read_excel(splits_path,
                              engine='openpyxl',
                              sheet_name='Supplementray_Table_23',
                              skiprows=3,
                              usecols='A:E')

    return df_splits


# -- TEST FILE FUNCTION --

def _test():
    from src.read_data.load_data import load_stocks
    df = load_stocks('Mueller', country_specific=False, per_capita=True, recalculate=True)
    print(df)


if __name__ == "__main__":
    _test()
