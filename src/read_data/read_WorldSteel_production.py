import os
import pandas as pd
from src.read_data.read_WorldSteel_digitalized import get_worldsteel_original, WS_DIGITALIZED_PATH


def get_worldsteel_production_1900_2022():
    df = _get_worldsteel_production_original()
    df = _extrapolate_production_to_past(df)
    return df


def _extrapolate_production_to_past(df):
    df_world = _read_worldsteel_world_production_1900_1969()
    df_pct = df_world.iloc[:, :-1] / df_world.iloc[0, -1]

    df_1969 = df.iloc[:, :1]
    df_1969 = df_1969.rename(columns={1969: 'Production'})
    df_past = df_1969.dot(df_pct)

    df = pd.merge(df_past, df, left_index=True, right_index=True)

    return df


def _read_worldsteel_world_production_1900_1969():
    filename = 'world_production_1900-1979.xlsx'
    world_production_path = os.path.join(WS_DIGITALIZED_PATH, filename)
    df = pd.read_excel(world_production_path,
                       skiprows=3,
                       nrows=70)
    df = df.set_index('Year')
    df = df.transpose()
    return df


def _get_worldsteel_production_original():
    yearbook_production_filenames = ['production_1969-1979.xlsx',
                                     'production_1980-1989.xlsx',
                                     'production_1990-1999.xlsx',
                                     'production_2000-2009.xlsx']
    df = get_worldsteel_original(yearbook_production_filenames,
                                 database_filename='P01_crude_2023-10-23.xlsx',
                                 skiprows=2,
                                 nrows=97,
                                 usecols='A,I:U')
    return df


def _test():
    from src.read_data.load_data import load_production
    df = load_production(country_specific=False, production_source='WorldSteel', recalculate=True)
    print(df)


if __name__ == "__main__":
    _test()
