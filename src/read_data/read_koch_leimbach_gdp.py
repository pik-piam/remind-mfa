import os
import numpy as np
import pandas as pd
from src.tools.config import cfg
from src.tools.tools import fill_missing_values_linear
from src.read_data.load_data import load_gdp


def get_koch_leimbach_gdp_countries():
    df = _read_koch_leimbach_original()
    df_imf = load_gdp(gdp_source='IMF', country_specific=True, per_capita=False)
    df = _add_past_data_by_using_imf_trends(df, df_imf)
    df = fill_missing_values_linear(df)
    return df


def _add_past_data_by_using_imf_trends(df, df_imf):
    """ Fill 1900-1964 values with GDP trends from imf data (see other assumptions there)."""
    df_imf = df_imf[np.arange(1900, 1966)]
    df_imf = df_imf.div(df_imf[1965], axis=0)
    df_imf = df_imf.mul(df[1965], axis=0)
    df = pd.concat([df_imf[np.arange(1900, 1965)], df], axis=1, join='inner')
    return df


def _read_koch_leimbach_original():
    """
    GDP predictions by country according to: https://doi.org/10.1016/j.ecolecon.2023.107751
    """
    koch_leimbach_path = os.path.join(cfg.data_path, 'original', 'koch_leimbach', 'GDP.csv')
    df = pd.read_csv(koch_leimbach_path,
                     skiprows=4,
                     nrows=6972,
                     usecols=['dummy', 'dummy.1', 'gdp_SSP1', 'gdp_SSP2', 'gdp_SSP3', 'gdp_SSP4', 'gdp_SSP5'])
    df = df.rename(columns={
        'dummy': 'year',
        'dummy.1': 'country',
        'gdp_SSP1': 'SSP1',
        'gdp_SSP2': 'SSP2',
        'gdp_SSP3': 'SSP3',
        'gdp_SSP4': 'SSP4',
        'gdp_SSP5': 'SSP5',
    })

    df['year'] = df['year'].str[-4:].astype(int)  # change years to integers

    df = df.melt(id_vars=["year", "country"],
                 var_name="SSP",
                 value_name="Value")

    df = df.pivot(index=['country', 'SSP'], columns='year', values='Value')

    df *= 1000000  # data is provided in million 2005 USD

    return df


# -- TEST FILE FUNCTION --

def _test():
    from src.read_data.load_data import load_gdp
    df = load_gdp('Koch-Leimbach', country_specific=False, per_capita=True, recalculate=True)
    print(df)


if __name__ == "__main__":
    _test()
