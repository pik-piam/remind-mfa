from src.read_data.read_WorldSteel_digitalized import read_worldsteel_database_file
from src.tools.country_mapping import map_iso3_codes, split_joint_country_data, join_split_country_data


def get_world_steel_indirect_imports_2001_2019():
    df = _get_world_steel_indirect_trade_2001_2019('I02_indirect_imports_2023-10-23.xlsx')
    return df


def get_world_steel_indirect_exports_2001_2019():
    df = _get_world_steel_indirect_trade_2001_2019('I01_indirect_exports_2023-10-23.xlsx')
    return df


def _get_world_steel_indirect_trade_2001_2019(filename):
    df = read_worldsteel_database_file(filename,
                                       skiprows=2,
                                       nrows=71,
                                       usecols='A:T')
    df = map_iso3_codes(df, 'Country')
    df = split_joint_country_data(df)
    df = join_split_country_data(df)
    return df


def _test():
    df_imports = get_world_steel_indirect_imports_2001_2019()
    df_exports = get_world_steel_indirect_exports_2001_2019()
    print(df_imports)
    print(df_exports)


if __name__ == '__main__':
    _test()
