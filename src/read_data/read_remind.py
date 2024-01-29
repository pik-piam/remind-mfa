import os
import numpy as np
import pandas as pd
from src.tools.config import cfg
from src.tools.tools import fill_missing_values_linear


def get_remind_pop():
    return get_remind_data('population.csv', 'pop')


def get_remind_gdp():
    return get_remind_data('gdp_ppp.csv', 'gdp')


def get_remind_regions():
    return get_remind_region_mapping('remind_regions.csv')


def get_remind_eu_regions():
    return get_remind_region_mapping('remind_eu_regions.csv')


def get_remind_region_mapping(filename):
    remind_data_path = os.path.join(cfg.data_path, 'original', 'remind', filename)
    df_remind = pd.read_csv(remind_data_path)
    df_remind = df_remind \
        .set_index('country') \
        .rename(columns={'region': 'Region'})
    return df_remind


def get_remind_data(filename, data_type):
    df = _read_remind_data_raw(filename, data_type)
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


def _read_remind_data_raw(filename, data_type):

    path = os.path.join(cfg.data_path, 'original', 'remind', filename)
    df = pd.read_csv(path,
                     skiprows=4,
                     usecols=['dummy',
                              'dummy.1',
                              f'{data_type}_{cfg.scenario}'])
    df = df.rename(columns={
        'dummy': 'Time',
        'dummy.1': 'country',
        f'{data_type}_{cfg.scenario}': 'value'
    })

    df['Time'] = df['Time'].str[1:].astype(int)  # change years to integers

    df['value'] = 1e6 * df['value']  # gdp is provided in million 2005 USD, population in million people

    return df


# -- TEST FILE FUNCTION --



if __name__ == "__main__":
    print()
