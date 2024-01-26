import os
import warnings
import pandas as pd
import numpy as np
from src.tools.config import cfg
# from src.read_data.load_data import load_gdp


def map_split_join_iso3(df, country_name_column: str = 'country_name') -> pd.DataFrame:
    df = map_iso3_codes(df, country_name_column)
    df = split_joint_country_data(df)
    df = join_split_country_data(df)
    return df


def map_iso3_codes(df: pd.DataFrame, country_name_column: str = 'country_name') -> pd.DataFrame:
    """
    Changes full country names in df to iso3 codes. For this, all country names need to be mapped in the iso3map.csv.
    If they aren't a warning is raised (see _check_ignored_rows method).

    :param df: The data frame that needs to be mapped to iso3 codes.
    :param country_name_column: The name of the country name column in the (original) df. Default is 'country_name'.
    :return: The updated df with the index 'country' as iso3 codes. Original column of country names has been dropped.
    """

    _check_ignored_rows(df, country_name_column)
    df = pd.merge(df_iso3, df, left_on='country_name', right_on=country_name_column)
    df = df.drop(columns=['country_name', country_name_column])
    df = df.set_index('country')

    return df


def _read_iso3_csv(filename: str) -> pd.DataFrame:
    """
    Reads any file containing iso3 name maps from the iso3 codes directory in data/original as a Data Frame.

    :param filename: Just the filename (with or without '.csv' extension)
    :return: The iso3 name map as a pd.DataFrame
    """
    if filename[-4:] != '.csv':
        filename = f'{filename}.csv'
    iso3_csv_path = os.path.join(cfg.data_path, 'original', 'iso3_codes', filename)
    df = pd.read_csv(iso3_csv_path)

    return df


def _check_ignored_rows(df: pd.DataFrame, country_name_column: str) -> None:
    """
    Check if the index of a row is not in the iso3 map. If the index is nan,
    or contains the words 'Other', 'World', or 'Total' this is ignored, otherwise a
    warning is raised. The conditions are applied because 'Total' rows are
    usually aggregated values, 'Other' rows are usually negligble, and rows
    with 'nan' as an index are not allocatable.

    :param df: The data frame that needs to be mapped to iso3 codes
    :param country_name_column: The name of the country name column in the (original) df. Default is 'country_name'.
    :return:
    """

    df_iso3_countries = pd.Index(df_iso3['country_name'])
    df_countries = pd.Index(df[country_name_column])
    ignored_rows = list(df_countries.difference(df_iso3_countries).unique())
    for row_name in ignored_rows:
        if isinstance(row_name, str):
            if 'Other' in row_name or 'Total' in row_name or 'World' in row_name:
                continue
        if isinstance(row_name, float):
            if row_name == np.nan:
                continue
        else:
            warn_message = f'{row_name} ignored when cleaning data.'
            warnings.warn(warn_message)


def split_joint_country_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Splits data of formerly joint regions like Yugoslavia or USSR into the countries as they are today.
    This is done by using the percentage each new country has of the total of all formerly joint countries
    in the first year when individual data is available. The mapping of formerly joint country to now split
    countries needs to be defined in iso3_countries_to_split.csv in data/original/iso3_codes.

    :param df: DataFrame before joint country data is split into new countries.
    :return: DataFrame when joint country data is split. Former countries are now ommited.
    """

    # create df where all countries of area get value of whole area
    df_before_split = pd.merge(df_split_map, df, left_on='joint_country_name', right_on='country')
    df_before_split = df_before_split.set_index('country')
    gk_before_split = df_before_split.groupby('joint_country_name')

    df_after_split = pd.merge(df_split_map, df, on='country')
    df_after_split = df_after_split.set_index('country')
    gk_after_split = df_after_split.groupby('joint_country_name')

    start_year = df.columns[0]
    for joint_country_name, df_after in gk_after_split:
        if joint_country_name not in gk_before_split.groups.keys():  # joint country data does not exist
            continue
        df_after = df_after.drop(columns=['joint_country_name'])
        df_before = gk_before_split.get_group(joint_country_name)
        df_before = df_before.drop(columns=['joint_country_name'])

        split_year = df_after.transpose().first_valid_index()  # first year, where any country data exists is chosen
        if split_year == start_year:  # data does not need to be split, all necessary data is available
            continue

        df_before = df_before.loc[:, :split_year - 1]
        df_after = df_after.loc[:, split_year:]

        # get percentages in first year that data is available
        df_split_year = df_after[split_year]
        df_split_year = df_split_year.fillna(0)
        df_percent = df_split_year / df_split_year.sum()

        df_before = df_before.multiply(df_percent, axis=0)
        df_final = pd.merge(df_before, df_after, on='country')

        # update data in original df
        df[df.index.isin(df_final.index)] = df_final
        df = df.drop(index=[joint_country_name])

    return df


def split_joint_country_data_for_parameters(df):
    # prepare new countries data
    df_new_countries = pd.merge(df_split_map, df, left_on='joint_country_name', right_on='country')
    df_new_countries = df_new_countries.drop(columns=['joint_country_name'])
    df_new_countries = df_new_countries.set_index('country')

    # delete old country data
    df = df[~df.index.isin(df_split_map['joint_country_name'])]

    # append new countries data
    df = pd.concat([df, df_new_countries])
    df = df.sort_index()

    return df


def join_split_country_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Joins formerly split country data in DataFrame into now merged country by adding all parts together.
    These areas need to be mapped in iso3_countries_to_join.csv in data/original/iso3_codes.

    :param df: DataFrame with data of formerly split countries.
    :return: That DataFramed with summed data of all subregions of now joint countries.
    """
    df_to_join = pd.merge(df_join_map, df, left_on='split_country_iso3', right_on='country')
    gk_to_join = df_to_join.groupby('country')
    for country, df_split in gk_to_join:
        split_countries = df_split['split_country_iso3']
        df_split = df_split.fillna(0)
        df_split = df_split.drop(columns=['split_country_iso3'])
        df_joint = df_split.sum(numeric_only=True)

        # update original df
        df = df.drop(index=split_countries)
        df.loc[country] = df_joint

    df = df.sort_index()

    return df


# def _get_gdp_percentages_of_joint_areas():
#     """
#     Helper function if formerly joint countries need to be split by shares of total GDP.
#     :return:
#     """
#     df_gdp = load_gdp(country_specific=True, per_capita=False)
#     df_gdp = pd.merge(df_split_map, df_gdp, left_on='country', right_index=True)
#     gk_gdp = df_gdp.groupby('joint_country_name')
#     df_gdp_sums = gk_gdp.transform('sum', numeric_only=True)
#     df_gdp.iloc[:, 2:] = df_gdp.iloc[:, 2:] / df_gdp_sums
#     df_gdp = df_gdp.set_index(['country', 'joint_country_name'])

#     return df_gdp


df_iso3 = _read_iso3_csv('iso3map')
df_split_map = _read_iso3_csv('iso3_countries_to_split')
df_join_map = _read_iso3_csv('iso3_countries_to_join')
