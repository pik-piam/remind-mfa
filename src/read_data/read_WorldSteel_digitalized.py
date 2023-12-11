import os
import pandas as pd
from src.tools.config import cfg
from src.tools.country_mapping import map_iso3_codes, split_joint_country_data, join_split_country_data

WS_DIGITALIZED_PATH = os.path.join(cfg.data_path, 'original', 'worldsteel', 'WS_digitalized')


def get_worldsteel_original(yearbook_filenames, database_filename, skiprows, nrows, usecols):
    df = pd.DataFrame()

    for filename in yearbook_filenames:
        df_decade = read_worldsteel_yearbook_data(filename)
        df_decade = map_iso3_codes(df_decade)
        df = pd.merge(df, df_decade, left_index=True, right_index=True, how='outer')

    df_database = read_worldsteel_database_file(database_filename, skiprows, nrows, usecols)
    df_database = map_iso3_codes(df_database, 'Country')

    df = pd.merge(df, df_database, left_index=True, right_index=True, how='outer')

    df = split_joint_country_data(df)
    df = join_split_country_data(df)

    df = df.fillna(0)

    return df


def read_worldsteel_database_file(filename, skiprows, nrows, usecols):
    path = os.path.join(WS_DIGITALIZED_PATH, filename)
    df = pd.read_excel(path,
                       skiprows=skiprows,
                       nrows=nrows,
                       usecols=usecols)
    return df


def read_worldsteel_yearbook_data(filename: str):
    path = os.path.join(WS_DIGITALIZED_PATH, filename)
    df = pd.read_excel(path)

    return df
