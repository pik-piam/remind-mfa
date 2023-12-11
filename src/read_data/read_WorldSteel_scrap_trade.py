from src.read_data.read_WorldSteel_digitalized import get_worldsteel_original


def get_world_steel_scrap_exports_1970_2022():
    yearbook_scrap_import_filenames = ['scrap_exports_70s.xlsx',
                                       'scrap_exports_80s.xlsx',
                                       'scrap_exports_90s.xlsx',
                                       'scrap_exports_00s.xlsx']
    df = get_worldsteel_original(yearbook_scrap_import_filenames,
                                 database_filename='T17_exports_scrap-2023-10-23.xlsx',
                                 skiprows=2,
                                 nrows=122,
                                 usecols='A,J:U')
    return df


def get_world_steel_scrap_imports_1970_2022():
    yearbook_scrap_import_filenames = ['scrap_imports_70s.xlsx',
                                       'scrap_imports_80s.xlsx',
                                       'scrap_imports_90s.xlsx',
                                       'scrap_imports_00s.xlsx']
    df = get_worldsteel_original(yearbook_scrap_import_filenames,
                                 database_filename='T18_imports_scrap-2023-10-23.xlsx',
                                 skiprows=2,
                                 nrows=122,
                                 usecols='A,J:U')
    return df


def _test():
    from src.read_data.load_data import load_scrap_trade_1971_2022
    df_im, df_ex = load_scrap_trade_1971_2022(country_specific=False,
                                              scrap_trade_source='WorldSteel',
                                              recalculate=True)
    print(df_im)
    print(df_ex)
    return


if __name__ == "__main__":
    _test()
