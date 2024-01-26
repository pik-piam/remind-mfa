import os
import numpy as np
import pandas as pd
from src.tools.config import cfg
from src.tools.tools import fill_missing_values_linear


def get_remind_gdp():
    df = _read_remind_gdp_raw()
    df = _extrapolate_past(df)
    df = fill_missing_values_linear(df)
    return df


def _extrapolate_past(df: pd.DataFrame):
    def _extrapolate_single(df):
        growth_rate = np.power(df['value'].values[70] / df['value'].values[0], 1./70.)
        values_prepend = df['value'].values[0] * growth_rate**np.arange(-10, 0)
        df_prepend = pd.DataFrame.from_dict({'Time': np.arange(1950,1960), 'country': df['country'].values[:10], 'value': values_prepend})
        return pd.concat([df_prepend, df])

    df = df \
        .groupby(by='country') \
        .apply(lambda group: _extrapolate_single(group)) \
        .reset_index(drop=True)
    return df


def _read_remind_gdp_raw():
    """
    GDP predictions by country according to: https://doi.org/10.1016/j.ecolecon.2023.107751
    """
    path = os.path.join(cfg.data_path, 'original', 'koch_leimbach', 'gdp_ppp.csv')
    df = pd.read_csv(path,
                     skiprows=4,
                     usecols=['dummy', 'dummy.1', 'gdp_SSP1', 'gdp_SSP2', 'gdp_SSP3', 'gdp_SSP4', 'gdp_SSP5'])
    df = df.rename(columns={
        'dummy': 'Time',
        'dummy.1': 'country',
        'gdp_SSP1': 'SSP1',
        'gdp_SSP2': 'SSP2',
        'gdp_SSP3': 'SSP3',
        'gdp_SSP4': 'SSP4',
        'gdp_SSP5': 'SSP5',
    })

    df['Time'] = df['Time'].str[1:].astype(int)  # change years to integers

    df['value'] = 1000000*df[cfg.scenario]  # data is provided in million 2005 USD

    df = df.drop(columns=['SSP1', 'SSP2', 'SSP3', 'SSP4', 'SSP5'])

    return df


# -- TEST FILE FUNCTION --



if __name__ == "__main__":
    print()
