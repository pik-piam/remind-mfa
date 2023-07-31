import os
import pandas as pd
from src.tools.config import cfg
from src.tools.split_data_into_subregions import split_areas_by_gdp
from src.tools.tools import fill_missing_values_linear


def get_worldsteel_use():
    df_use = _read_worldsteel_original_use()
    df_iso3 = _read_worldsteel_iso3_map()
    df_use = _clean_worldsteel_data(df_use, df_iso3,
                                    ['Joint Serbia and Montenegro', 'South African C.U. (1)', 'Belgium-Luxembourg'])
    return df_use


def get_worldsteel_production():
    df_production = _read_worldsteel_original_production()
    df_iso3 = _read_worldsteel_iso3_map()
    df_production = _clean_worldsteel_data(df_production, df_iso3, ['Joint Serbia and Montenegro'])
    return df_production


def get_worldsteel_scrap_exports():
    df_scrap_exports = _read_worldsteel_original_scrap_exports()
    df_iso3 = _read_worldsteel_scrap_iso3_map()
    df_scrap_exports = pd.merge(df_iso3, df_scrap_exports, on='country_name')
    df_scrap_exports = df_scrap_exports.drop(columns=['country_name'])
    df_scrap_exports = df_scrap_exports.set_index('country')

    df_scrap_exports *= 1000

    return df_scrap_exports


def get_worldsteel_scrap_imports():
    df_scrap_imports = _read_worldsteel_original_scrap_imports()
    df_iso3 = _read_worldsteel_scrap_iso3_map()
    df_scrap_imports = pd.merge(df_iso3, df_scrap_imports, on='country_name')
    df_scrap_imports = df_scrap_imports.drop(columns=['country_name'])
    df_scrap_imports = df_scrap_imports.set_index('country')

    df_scrap_imports *= 1000

    return df_scrap_imports


def _clean_worldsteel_data(df: pd.DataFrame, df_iso3: pd.DataFrame, areas_to_split: list):
    df = df.set_index('country_name')
    df = _merge_worldsteel_serbia_montenegro(df)
    df = pd.merge(df_iso3, df, left_on='country_name', right_index=True)
    df = df.drop(columns=['country_name'])
    df = df.set_index('country')
    df = split_areas_by_gdp(areas_to_split, df, df_iso3)
    df = df.replace('...', pd.NA)
    df = fill_missing_values_linear(df)
    return df


def _merge_worldsteel_serbia_montenegro(df_original):
    serbia_data = df_original.loc['Serbia']
    montenegro_data = df_original.loc['Montenegro']
    serbia_and_montenegro_data = df_original.loc['Serbia and Montenegro']
    fryugoslavia_data = df_original.loc['F.R. Yugoslavia']

    df_original = df_original.drop(index=['Serbia', 'Montenegro', 'Serbia and Montenegro', 'F.R. Yugoslavia'])

    joint_data = serbia_data + montenegro_data
    joint_data = joint_data.add(serbia_and_montenegro_data, fill_value=0)
    joint_data = joint_data.add(fryugoslavia_data, fill_value=0)

    df_original.loc['Joint Serbia and Montenegro'] = joint_data

    return df_original


def _read_worldsteel_original_scrap_exports():
    scrap_path = os.path.join(cfg.data_path, 'original', 'worldsteel', 'Scrap_Trade_2018-2017.xlsx')
    df_scrap_exports = pd.read_excel(
        io=scrap_path,
        engine='openpyxl',
        sheet_name='Exports of Scrap')
    return df_scrap_exports


def _read_worldsteel_original_scrap_imports():
    scrap_path = os.path.join(cfg.data_path, 'original', 'worldsteel', 'Scrap_Trade_2018-2017.xlsx')
    df_scrap_imports = pd.read_excel(
        io=scrap_path,
        engine='openpyxl',
        sheet_name='Imports of Scrap')
    return df_scrap_imports


def _read_worldsteel_iso3_map():
    iso3_map_path = os.path.join(cfg.data_path, 'original', 'worldsteel', 'WorldSteel_countries.csv')
    df = pd.read_csv(iso3_map_path)
    return df


def _read_worldsteel_scrap_iso3_map():
    iso3_map_path = os.path.join(cfg.data_path, 'original', 'worldsteel', 'WorldSteel_scrap_countries.csv')
    df = pd.read_csv(iso3_map_path)
    return df


def _read_worldsteel_original_production():
    production_path = os.path.join(cfg.data_path, 'original', 'worldsteel', "Steel_Statistical_Yearbook_combined.ods")
    df_production = pd.read_excel(production_path,
                                  sheet_name='Total Production of Crude Steel',
                                  engine='odf',
                                  usecols='A:AC')
    df_production = df_production.rename(columns={'country': 'country_name'})

    return df_production


def _read_worldsteel_original_use():
    use_path = os.path.join(cfg.data_path, 'original', 'worldsteel',
                            "Steel_Statistical_Yearbook_combined.ods")
    df_use = pd.read_excel(use_path,
                           sheet_name='Apparent Steel Use (Crude Steel Equivalent)',
                           engine='odf',
                           usecols='A:AC')
    df_use = df_use.rename(columns={'country': 'country_name'})
    return df_use


def _test():
    scrap_imports = get_worldsteel_scrap_imports()
    scrap_exports = get_worldsteel_scrap_exports()
    print(scrap_imports)
    print(scrap_exports)

    return


if __name__ == "__main__":
    _test()

# Notes:


"""def load_all_trade():
    trade_dict = load_normal_trade()
    dynamic_models = load_dsms()

    scrap_trade_params = {'LAM': 1000 * [43396 + 115761 - 81612 - 13614, 42715 + 162388 - 109664 - 18450,
                                         20908 + 1049 - 15016 - 4409, 801 + 8594 - 4636 - 2115],
                          'OAS': 1000 * [1164070 - 831728 - 22438 - 101455 - 104661,
                                         1126426 - 767530 - 2344 - 21182 - 100892 - 70100 + 349,
                                         14971 - 2230 - 1380 - 8208 - 104 + 63,
                                         31581 + 108 - 2326 - 309 - 2919 - 232 - 5365],
                          'SSA': 1000 * [15053 - 650 - 6870 - 422 - 5 - 550 - 50,
                                         38035 - 6459 - 551 - 10890 - 1539 - 135 - 3367 - 337 - 921,
                                         1382 - 26 - 20, 67 + 25],
                          'EUR': 1000 * [168305, 178119, 48396, 31894],
                          'NEU': 1000 * [42203, 45268, 2068, 22047],
                          'MEA': 1000 * [34475 + 650 + 6870 + 422 + 5 + 550 + 50,
                                         58018 + 6459 + 551 + 10890 + 1539 + 135 + 3367 + 337 + 921,
                                         1954 + 26 + 20, 1094 + 2035 + 350],
                          'REF': 1000 * [100933, 59302, 5787, 2458],
                          'CAZ': 1000 * [5985 + 13614, 7425 - 349 + 18450, 2615 - 63 + 4409, 108 - 49 + 2115],
                          'CHA': 1000 * [115761 + 81621, 767530 + 2344 + 21182,
                                         2230 + 1380 + 104, 2326 + 309 + 2919],
                          'IND': 1000 * [101455, 100892, 0, 5365],
                          'JPN': 1000 * [104661, 70100, 8208, 232],
                          'USA': 1000 * [81612, 109664, 15016, 4636]}

    net_scrap_trade = np.zeros(201, dtype='f4')
    sum_scrap_trade = np.zeros(201, dtype='f4')
    categories = ['Transport', 'Machinery', 'Construction', 'Products']
    for region in scrap_trade_params.keys():
        production = scrap_trade_params[region][0]
        exports = scrap_trade_params[region][2]
        imports = scrap_trade_params[region][3]
        scrap_trade_share = (imports - exports) / production
        region_dsm_dict = dynamic_models[region]
        use = np.zeros(201, dtype='f4')
        for category in categories:
            use += region_dsm_dict[category].i
        trade = trade_dict[region]['Trade']
        production = use - trade
        scrap_trade = production * scrap_trade_share
        trade_dict[region]["Scrap_Trade"] = scrap_trade
        net_scrap_trade += scrap_trade
        sum_scrap_trade += abs(scrap_trade)
    scrap_factor = np.divide(net_scrap_trade, sum_scrap_trade)
    for region in trade_dict.keys():
        region_dict = trade_dict[region]
        scrap_trade = region_dict['Scrap_Trade']
        new_scrap_trade = np.zeros(201, dtype='f4')
        for i, value in enumerate(scrap_trade):
            new_scrap_trade[i] = value * (1 - np.sign(value) * (scrap_factor[i]))
        region_dict['Scrap_Trade'] = new_scrap_trade
        region_dict['Scrap_Imports'] = np.maximum(0, new_scrap_trade)
        region_dict['Scrap_Exports'] = np.abs(np.minimum(0, new_scrap_trade))
    return trade_dict


def load_normal_trade():
    dynamic_models = load_dsms()

    # data according to Steel Statistical Yearbook, World Steel Association for 2017, region data adapted to fit remind
    # regions (e.g. LAM data = South America data + North America data - US+Canada data)
    # for all lists of regions, list[0]=production of crude steel, list[1]= apparent steel use (crude steel equivalent)
    trade_params = {'LAM': 1000 * [43396 + 115761 - 81612 - 13614, 42715 + 162388 - 109664 - 18450,
                                   20908 + 1049 - 15016 - 4409, 801 + 8594 - 4636 - 2115],
                    'OAS': 1000 * [1164070 - 831728 - 22438 - 101455 - 104661,
                                   1126426 - 767530 - 2344 - 21182 - 100892 - 70100 + 349,
                                   14971 - 2230 - 1380 - 8208 - 104 + 63,
                                   31581 + 108 - 2326 - 309 - 2919 - 232 - 5365],
                    'SSA': 1000 * [15053 - 650 - 6870 - 422 - 5 - 550 - 50,
                                   38035 - 6459 - 551 - 10890 - 1539 - 135 - 3367 - 337 - 921,
                                   1382 - 26 - 20, 67 + 25],
                    'EUR': 1000 * [168305, 178119, 48396, 31894],
                    'NEU': 1000 * [42203, 45268, 2068, 22047],
                    'MEA': 1000 * [34475 + 650 + 6870 + 422 + 5 + 550 + 50,
                                   58018 + 6459 + 551 + 10890 + 1539 + 135 + 3367 + 337 + 921,
                                   1954 + 26 + 20, 1094 + 2035 + 350],
                    'REF': 1000 * [100933, 59302, 5787, 2458],
                    'CAZ': 1000 * [5985 + 13614, 7425 - 349 + 18450, 2615 - 63 + 4409, 108 - 49 + 2115],
                    'CHA': 1000 * [115761 + 81621, 767530 + 2344 + 21182,
                                   2230 + 1380 + 104, 2326 + 309 + 2919],
                    'IND': 1000 * [101455, 100892, 0, 5365],
                    'JPN': 1000 * [104661, 70100, 8208, 232],
                    'USA': 1000 * [81612, 109664, 15016, 4636]}
    trade_dict = {}
    net_trade = np.zeros(201, dtype='f4')
    sum_trade = np.zeros(201, dtype='f4')
    categories = ['Transport', 'Machinery', 'Construction', 'Products']
    for region in trade_params.keys():
        production = trade_params[region][0]
        apparent_use = trade_params[region][1]
        trade_share = (apparent_use - production) / apparent_use
        region_dsm_dict = dynamic_models[region]
        use = np.zeros(201, dtype='f4')
        for category in categories:
            use += region_dsm_dict[category].i
        trade = use * trade_share
        trade_dict[region] = trade
        net_trade += trade
        sum_trade += abs(trade)
    factor = np.divide(net_trade, sum_trade)
    sum_trade = np.zeros(201, dtype='f4')
    for region in trade_dict.keys():
        region_dict = {}
        trade = trade_dict[region]
        new_trade = np.zeros(201, dtype='f4')
        for i, value in enumerate(trade):
            new_trade[i] = value * (1 - np.sign(value) * (factor[i]))
        sum_trade += new_trade
        region_dict['Trade'] = new_trade
        region_dict['Imports'] = np.maximum(0, new_trade)
        region_dict['Exports'] = np.abs(np.minimum(0, new_trade))
        trade_dict[region] = region_dict
    return trade_dict
    
    


    # read production data
    for r in range(0, len(production_raw['country'])):
        country_name = production_raw['country'][r]
        country_iso = None
        country_list = np.zeros(28)
        for i in iso_countries:
            if country_name == i[0]:
                country_iso = i[1]
                break
        if country_iso is None:
            continue
        for c in range(28):
            year_column_string = 1991 + c
            date = production_raw[year_column_string][r]
            if date == '...' or date == '' or date == 'nan' or date is None:
                date = 0
            date = float(date)
            if date != date:
                date = 0
            country_list[c] = float(date) * 1000  # get tonnes from kt
        trade_dict[country_iso] = {'Production': country_list}

    # read use data
    for r in range(0, len(use_raw['country'])):
        country_name = use_raw['country'][r]
        country_iso = None
        country_list = np.zeros(28)
        for i in iso_countries:
            if country_name[:len(i[0])] == i[0]:
                country_iso = i[1]
                break
        for c in range(28):
            year_column_string = 1991 + c
            date = use_raw[year_column_string][r]
            if date == '...' or date == '' or date == 'nan' or date is None:
                date = 0
            date = float(date)
            if date != date:
                date = 0
            country_list[c] = float(date) * 1000  # get tonnes from kt
        if country_iso in trade_dict.keys():
            trade_dict[country_iso]['Use'] = country_list
    for key in list(trade_dict.keys()).copy():
        if 'Use' not in trade_dict[key].keys():
            trade_dict.pop(key)
    totalimports = np.zeros(28)
    totalexports = np.zeros(28)
    for country in trade_dict.keys():
        country_dict = trade_dict[country]
        country_dict['Imports'] = np.maximum(0, country_dict['Use'] - country_dict['Production'])
        country_dict['Exports'] = np.maximum(0, country_dict['Production'] - country_dict['Use'])
        totalimports += country_dict['Imports']
        totalexports += country_dict['Exports']
        import_share = np.zeros(28)
        export_share = np.zeros(28)
        for i in range(28):
            if country_dict['Use'][i] == 0:
                # in case that 'Use' was zero, if there was production it is all assumed to be exported whereas if
                # there wasn't any production, all is assumed to be inmported
                if country_dict['Production'][i] == 0:
                    import_share[i] = 1
                    export_share[i] = 0
                else:
                    import_share[i] = 0
                    export_share[i] = 1
            else:
                import_share[i] = (country_dict['Imports'][i] + country_dict['Exports'][i]) / country_dict['Use'][i]

        country_dict['TradeShare'] = import_share
        if True:
            print(country)
            # print(country_dict['Imports'][-5:])
            # print(country_dict['Exports'][-5:])
            # print(country_dict['Use'][-5:])
            # print(country_dict['Production'][-5:])
            print(country_dict['TradeShare'][-5:])
    print("hey")
    print(totalimports)
    print(totalexports)
    print(totalimports - totalexports)
    print(len(trade_dict.keys()))

    return trade_dict    
    """
