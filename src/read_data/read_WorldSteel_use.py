from src.read_data.read_WorldSteel_digitalized import get_worldsteel_original


def get_world_steel_use_1970_2021():
    yearbook_use_filenames = ['app_steel_use_70s.xlsx',
                              'app_steel_use_80s.xlsx',
                              'app_steel_use_90s.xlsx',
                              'app_steel_use_00s.xlsx']
    df = get_worldsteel_original(yearbook_use_filenames,
                                 database_filename='U01_use_2023-10-23.xlsx',
                                 skiprows=2,
                                 nrows=122,
                                 usecols='A,J:U')
    return df


def _test():
    from src.read_data.load_data import load_use_1970_2021
    df = load_use_1970_2021(country_specific=False, use_source='WorldSteel', recalculate=True)
    print(df)
    return


if __name__ == "__main__":
    _test()
