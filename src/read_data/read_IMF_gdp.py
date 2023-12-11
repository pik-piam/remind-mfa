import os
import pandas as pd
from src.tools.config import cfg
from src.tools.tools import fill_missing_values_linear, transform_per_capita
from src.read_data.read_REMIND_regions import get_remind_regions


def get_imf_gdp_countries():
    df_current = _read_imf_original()
    df_future = _get_future_gdp_pc()
    df_past = get_past_according_to_gdppc_estimates(df_current)
    df = df_past.merge(df_current, on='country')
    df = df.merge(df_future, on='country')
    df = fill_missing_values_linear(df)
    return df


# -- FORMATING DATA FUNCTIONS --


def get_past_according_to_gdppc_estimates(df_current):
    past_region_percentages = _read_1900_1940_region_percentages_of_1950_gdps()
    past_country_percentages = _get_past_percentages_by_country(past_region_percentages)
    df_past = past_country_percentages.multiply(df_current[1950], axis=0)

    return df_past


def _get_past_percentages_by_country(df_region_percentages):
    regions = get_remind_regions()
    df = pd.merge(regions.reset_index(), df_region_percentages, on='region')
    df = df.set_index('country')
    df = df.drop('region', axis=1)

    return df


def _get_future_gdp_pc():
    df_future_gdp = _read_koch_leimbach_gdp_predictions()
    df_future_gdp *= 1000000  # as data is given in millions, multiply by 1000000
    df_future_gdppc = transform_per_capita(df_future_gdp, total_from_per_capita=False, country_specific=True)

    return df_future_gdppc


# -- READ RAW DATA FUNCTIONS --


def _read_1900_1940_region_percentages_of_1950_gdps():
    """
    Past estimates according to: http://dx.doi.org/10.1787/9789264214262-en
    """
    past_estimates_path = os.path.join(cfg.data_path, 'original', 'oecd', 'OECD_past_gdp.csv')
    df = pd.read_csv(past_estimates_path, index_col='region')
    df.columns = df.columns.astype(int)
    gdp_of_1950 = df[1950]
    df = df.divide(gdp_of_1950, axis=0)
    df = df.drop(1950, axis=1)

    return df


def _read_koch_leimbach_gdp_predictions():
    """
    GDP predictions by country according to: https://doi.org/10.1016/j.ecolecon.2023.107751
    """
    predictions_path = os.path.join(cfg.data_path, 'original', 'koch_leimbach', 'GDP.csv')
    df = pd.read_csv(predictions_path,
                     skiprows=4,
                     usecols=['dummy', 'dummy.1', 'gdp_SSP2'])
    df = df.rename(columns={
        'dummy': 'year',
        'dummy.1': 'country',
        'gdp_SSP2': 'gdp_pc'  # choose ssp2 scenario as default
    })

    df['year'] = df['year'].str[-4:].astype(int)  # change years to integers
    # change to horizontal format
    df = df.pivot(index='country', columns='year', values='gdp_pc')

    return df


def _read_imf_original():
    imf_gdp_path = os.path.join(cfg.data_path, 'original', 'imf', 'GDPpC_210countries_1950-2015.xlsx')
    df = pd.read_excel(imf_gdp_path,
                       engine='openpyxl',
                       skiprows=2,
                       usecols=['ISO3', 'Year', 'IHME USD (2005 base year)'])
    df = df.rename(columns={
        'ISO3': 'country',
        'IHME USD (2005 base year)': 'gdp_pc'
    })
    # change to horizontal format
    df = df.pivot(index='country', columns='Year', values='gdp_pc')
    # change year columns from float to int
    df.columns = df.columns.astype(int)

    return df


# -- TEST FILE FUNCTION --

def _test():
    from src.read_data.load_data import load_gdp
    df = load_gdp('IMF', country_specific=False, is_per_capita=False)
    print(df)


if __name__ == "__main__":
    _test()
