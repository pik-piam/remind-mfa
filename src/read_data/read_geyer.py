import os
import numpy as np
import pandas as pd
from src.tools.config import cfg
from src.tools.tools import fill_missing_values_linear
from src.read_data.load_data import load_pop


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


def _read_geyer_production():
    df = pd.read_excel(geyer_file_path(),
                       sheet_name="S1")
    return df


def _read_geyer_lifetimes():
    df = pd.read_excel(geyer_file_path(),
                       sheet_name="S4")
    shares = _read_geyer_shares(sectors=geyer_in_use_categories)
    sector_weights = _sum_shares(shares, keep_by='Sector')
    df = df \
        .rename(columns={'Mean (in years)': 'mean', 'Standard deviation': 'std'}) \
        .assign(**{'variance': lambda df: df['std']**2}) \
        .merge(sector_weights, on='Market Sector', how='left') \
        .rename(columns={'value': 'weight'}) \
        .assign(**{'weighted mean': lambda df: df['mean'] * df['weight'],
                   'weighted squared mean': lambda df: df['mean']**2 * df['weight'],
                   'weighted variance': lambda df: df['variance'] * df['weight']})
    df = _sum_rows_by_mapping(df, 'Market Sector', _geyer_in_use_categories_mapping())
    df = df \
        .assign(**{'weighted mean': lambda df: df['weighted mean'] / df['weight'],
                   'weighted squared mean': lambda df: df['weighted squared mean'] / df['weight'],
                   'weighted variance': lambda df: df['weighted variance'] / df['weight']}) \
        .assign(**{'mean': lambda df: df['weighted mean'],
                   'variance': lambda df: (df['weighted variance'] + df['weighted squared mean'] - df['weighted mean']**2)}) \
        .assign(**{'std': lambda df: np.sqrt(df['variance'])}) \
        .filter(['Market Sector', 'mean', 'std'])
    return df

def _read_geyer_shares(elements: list = cfg.elements, sectors: list = cfg.in_use_categories):
    df_raw = pd.read_excel(geyer_file_path(),
                       sheet_name="S2")
    df = _sum_rows_by_mapping(df_raw, 'Market Sector', _geyer_in_use_categories_mapping(sectors))
    df = _transpose(df, 'Market Sector', 'Element')
    df = _sum_rows_by_mapping(df, 'Element', _geyer_element_mapping(elements))
    df = _transpose(df, 'Element', 'Market Sector')
    return df


def _sum_shares(df, keep_by: str):
    if keep_by=='Element':
        df = _sum_and_transpose(df, 'Market Sector', 'Element')
    elif keep_by=='Sector':
        df = _transpose(df, 'Market Sector', 'Element')
        df = _sum_and_transpose(df, 'Element', 'Market Sector')
    else:
        raise Exception('invalid argument')
    return df


def _sum_and_transpose(df: pd.DataFrame, index_column: str, new_index_name: str):
    df= df \
        .drop(columns=index_column) \
        .sum() \
        .T \
        .reset_index() \
        .rename(columns={'index': new_index_name, 0: 'value'})
    return df

def _transpose(df: pd.DataFrame, index_column: str, new_index_name: str):
    df = df \
        .set_index(index_column) \
        .T \
        .reset_index()\
        .rename(columns={'index': new_index_name})
    return df

def _sum_rows_by_mapping(df: pd.DataFrame, column_name: str, mapping: pd.DataFrame):
    value_cols = np.setdiff1d(df.columns, column_name)
    df = df \
        .merge(mapping,
               left_on=column_name,
               right_on='source',
               how='left')
    df = df[df['target'].notnull()]
    df = df \
        .groupby('target') \
        .agg({c: 'sum' for c in value_cols}) \
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
    df = _read_geyer_lifetimes()
    print(df)
