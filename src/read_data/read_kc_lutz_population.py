import os
import numpy as np
import pandas as pd
from src.tools.config import cfg
from src.tools.tools import fill_missing_values_linear
from src.read_data.load_data import load_pop


def get_kc_lutz_pop_countries():
    df = _read_kc_lutz_pop_original()
    df_un = load_pop(pop_source='UN', country_specific=True)
    df = _add_past_data_by_using_imf_trends(df, df_un)
    df = fill_missing_values_linear(df)
    return df


def _add_past_data_by_using_imf_trends(df, df_un):
    """ Fill 1900-1959 values with population trends from UN data (should be very similar numbers)."""
    df_un = df_un[np.arange(1900, 1961)]
    df_un = df_un.div(df_un[1960], axis=0)
    df_un = df_un.mul(df[1960], axis=0)
    df = pd.concat([df_un[np.arange(1900, 1960)], df], axis=1, join='inner')
    return df


def _read_kc_lutz_pop_original():
    """
    GDP predictions by country according to: https://doi.org/10.1016/j.ecolecon.2023.107751
    """
    kc_lutz_path = os.path.join(cfg.data_path, 'original', 'kc-lutz', 'population.csv')
    df = pd.read_csv(kc_lutz_path,
                     skiprows=4,
                     nrows=20418,
                     usecols=['dummy', 'dummy.1', 'pop_SSP1', 'pop_SSP2', 'pop_SSP3', 'pop_SSP4', 'pop_SSP5'])
    df = df.rename(columns={
        'dummy': 'year',
        'dummy.1': 'country',
        'pop_SSP1': 'SSP1',
        'pop_SSP2': 'SSP2',
        'pop_SSP3': 'SSP3',
        'pop_SSP4': 'SSP4',
        'pop_SSP5': 'SSP5',
    })
    df['year'] = df['year'].str[-4:].astype(int)  # change years to integers

    df = df.melt(id_vars=["year", "country"],
                 var_name="SSP",
                 value_name="Value")

    df = df.pivot(index=['country', 'SSP'], columns='year', values='Value')

    df *= 1000000  # data is provided in million

    return df


# -- TEST FILE FUNCTION --

def _test():
    from src.read_data.load_data import load_pop
    df = load_pop('KC-Lutz', country_specific=False, recalculate=True)
    print(df)


if __name__ == "__main__":
    _test()
