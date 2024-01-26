import os
import numpy as np
import pandas as pd
from src.tools.config import cfg


def geyer_file_path():
    return os.path.join(cfg.data_path, 'original', 'geyer', 'supplementary_materials.xlsx')


geyer_elements = ['HDPE', 'LDPE', 'PP', 'PS', 'PVC', 'PET', 'PUR', 'Other']
geyer_in_use_categories = ['Packaging',
                           'Transportation',
                           'Building and Construction',
                           'Electrical / Electronic',
                           'Consumer & Institutional Products',
                           'Industrial Machinery',
                           'Other']
aspect_name_mapping = {'Market Sector': 'Good',
                       'Year': 'Time'}

def get_geyer_production():
    df = pd.read_excel(geyer_file_path(),
                       sheet_name="S1")
    df = df.rename(columns=aspect_name_mapping)
    df = df.rename(columns={'Global Production (Mt)': 'value'})
    df['value'] *= 1e6 # convert to tonnes
    df['Region'] = 'World'

    shares = get_geyer_shares()
    sector_split = sector_shares(shares)
    df = df.merge(sector_split,
                  how='cross',
                  suffixes=['_prod', '_share'])
    df['value'] = df['value_prod'] * df['value_share']
    df = df.drop(columns=['value_prod', 'value_share'])
    return df


def get_geyer_lifetimes():
    df = pd.read_excel(geyer_file_path(),
                       sheet_name="S4")
    df = df.rename(columns=aspect_name_mapping)
    shares = get_geyer_shares(sectors=geyer_in_use_categories)
    sector_weights = sector_shares(shares)
    df = df \
        .rename(columns={'Mean (in years)': 'mean', 'Standard deviation': 'std'}) \
        .assign(**{'variance': lambda df: df['std']**2}) \
        .merge(sector_weights, on='Good', how='left') \
        .rename(columns={'value': 'weight'}) \
        .assign(**{'weighted mean': lambda df: df['mean'] * df['weight'],
                   'weighted squared mean': lambda df: df['mean']**2 * df['weight'],
                   'weighted variance': lambda df: df['variance'] * df['weight']})
    df = _sum_by_mapping(df, 'Good', _geyer_in_use_categories_mapping())
    df = df \
        .assign(**{'weighted mean': lambda df: df['weighted mean'] / df['weight'],
                   'weighted squared mean': lambda df: df['weighted squared mean'] / df['weight'],
                   'weighted variance': lambda df: df['weighted variance'] / df['weight']}) \
        .assign(**{'mean': lambda df: df['weighted mean'],
                   'variance': lambda df: (df['weighted variance'] + df['weighted squared mean'] - df['weighted mean']**2)}) \
        .assign(**{'std': lambda df: np.sqrt(df['variance'])})
    df= df .filter(['Good', 'mean', 'std'])
    return df

def get_geyer_shares(elements: list = cfg.elements, sectors: list = cfg.in_use_categories):
    df = pd.read_excel(geyer_file_path(),
                       sheet_name="S2")
    df = df.rename(columns=aspect_name_mapping)
    df = df.melt(id_vars='Good', var_name='Element', value_name='value')
    df = _sum_by_mapping(df, 'Good', _geyer_in_use_categories_mapping(sectors))
    df = _sum_by_mapping(df, 'Element', _geyer_element_mapping(elements))
    return df


def element_shares(shares: pd.DataFrame):
    return shares \
        .groupby('Element', as_index=False) \
        .agg({'value': 'sum'})


def sector_shares(shares: pd.DataFrame):
    return shares \
        .groupby('Good', as_index=False) \
        .agg({'value': 'sum'})


def _sum_by_mapping(df: pd.DataFrame, column_name: str, mapping: pd.DataFrame):
    df = df \
        .merge(mapping,
               left_on=column_name,
               right_on='source',
               how='inner')
    index_cols = [c for c in cfg.aspects if c in df.columns and c != column_name] + ['target']
    value_cols = [c for c in df.columns if c not in index_cols and c not in [column_name, 'source']]
    df = df \
        .groupby(by=index_cols) \
        .agg({v: 'sum' for v in value_cols}) \
        .reset_index() \
        .rename(columns={'target': column_name})

    return df


def _geyer_element_mapping(target_elements: list = cfg.elements):
    mapping = {'HDPE': 'PE',
               'LDPE': 'PE',
               'Other': 'Other Elements'}
    df = _get_mapping_df(geyer_elements, target_elements, mapping)
    return df


def _geyer_in_use_categories_mapping(target_sectors: list = cfg.in_use_categories):
    mapping = {'Electrical /Electronic': 'Other Uses',
               'Consumer & Institutional Products': 'Other Uses',
               'Industrial Machinery': 'Other Uses',
               'Other': 'Other Uses'}
    df = _get_mapping_df(geyer_in_use_categories, target_sectors, mapping)
    return df


def _get_mapping_df(source: list, target: list, mapping: dict):
    same_as_target = [i if i in source else None for i in target]
    df = pd.DataFrame.from_dict({'same_as_target': same_as_target, 'target': target})
    mapping_df = pd.DataFrame.from_dict({'from_mapping': list(mapping.keys()), 'target': list(mapping.values())})
    mapping_df = mapping_df.query('target in @target')
    df = df.merge(mapping_df, how='left', on=['target'])
    df['source'] = df['same_as_target'].fillna(df['from_mapping'])
    df = df.drop(columns=['same_as_target', 'from_mapping'])
    if df['source'].isnull().any():
        raise Exception('Problem with mapping: No source for values found: ' + ", ".join(df[df['source'].isnull()]['target'].values))
    # TODO: Throw error if mapping contains same items in source and target
    return df


if __name__ == "__main__":
    df = get_geyer_production()
    print(df)
