import csv
import os
import numpy as np
import pandas as pd
from src.model.load_DSMs import load as load_dsms
from src.tools.config import cfg
from src.tools.split_data_into_subregions import split_areas_by_gdp


def load_world_steel_trade():
    categories = ['Trade', 'Imports', 'Exports', 'Scrap_Trade', 'Scrap_Imports', 'Scrap_Exports']
    if os.path.exists(os.path.join(cfg.data_path, 'processed', 'WorldSteel_trade.csv')) and not cfg.recalculate_data:
        with open(os.path.join(cfg.data_path, 'processed', 'WorldSteel_trade.csv')) as csv_file:
            trade_reader = csv.reader(csv_file, delimiter=',')
            trade_reader = list(trade_reader)
            trade_dict = {}
            for region_dates in trade_reader:
                region = region_dates[0]
                if region not in trade_dict.keys():
                    trade_dict[region] = {}
                category = region_dates[1]
                trade_data = region_dates[2:]
                trade_values = np.zeros(201, dtype='f4')
                for i in range(201):
                    trade_values[i] = float(trade_data[i])
                trade_dict[region][category] = trade_values
            return trade_dict
    else:
        trade_data = load_all_trade()
        with open(os.path.join(cfg.data_path, 'processed', 'WorldSteel_trade.csv'), 'w', newline='') as file:
            writer = csv.writer(file)
            for region in trade_data.keys():
                for category in categories:
                    writer.writerow([region, category] + list(trade_data[region][category]))
        return trade_data


def load_all_trade():
    """
    Add scrap trade.
    :return:
    """
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
        imports  = scrap_trade_params[region][3]
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
    """
    Load Trade data from the World Steel Association Yearbook. Calculate trade share in base year 2017
    through production and use. Project that share onto past and future and then balance imports and exports
    according to Michaja Pehl method. Data from yearbook is mapped onto REMIND regions.
    :return: dict[region][Trade/Imports/Exports]=list for 1900-2100
    """
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


def read_worldsteel_original():
    """
    Read data from Steel statistical yearbook, calculate Imports, Exports and Trade Share form Production and Use.
    TODO Unfisnished, need to decide how to implement trade
    :return:
    """
    with open(os.path.join(cfg.data_path, 'original', 'World_Steel', 'WorldSteel_countries.csv')) as csv_file:
        iso_countries = csv.reader(csv_file, delimiter=',')
        iso_countries = list(iso_countries)
    production_raw = pd.read_excel(os.path.join(cfg.data_path, 'original', 'World_Steel',
                                                "Steel_Statistical_Yearbook_combined.xlsx"),
                                   sheet_name='Total Production of Crude Steel', engine='openpyxl', usecols='A:AC')
    use_raw = pd.read_excel(os.path.join(cfg.data_path, 'original', 'World_Steel',
                                         "Steel_Statistical_Yearbook_combined.xlsx"),
                            sheet_name='Apparent Steel Use (Crude Steel', engine='openpyxl', usecols='A:AC')
    trade_dict = {}

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

def get_worldsteel_production_and_use():
    df_production, df_use = _read_worldsteel_original_production_and_use()
    df_iso3_map = _read_worldsteel_iso3_map()

    prod = set(df_production['country_name'])
    use = set(df_use['country_name'])
    iso = set(df_iso3_map['country_name'])

    print(prod.difference(iso))
    print(use.difference(iso))

    df_production = pd.merge(df_iso3_map, df_production, on='country_name')

    areas_to_normalize = ['Czechoslovakia']
    split_areas_by_gdp(df_production, areas_to_normalize, df_iso3_map)

    #return df_production, df_use
    return None, None


def _read_worldsteel_iso3_map():
    iso3_map_path = os.path.join(cfg.data_path, 'original', 'worldsteel', 'WorldSteel_countries.csv')
    df = pd.read_csv(iso3_map_path)
    return df

def _read_worldsteel_original_production_and_use():
    df_production = pd.read_excel(os.path.join(cfg.data_path, 'original', 'worldsteel',
                                                "Steel_Statistical_Yearbook_combined.ods"),
                                   sheet_name='Total Production of Crude Steel', engine='odf', usecols='A:AC')
    df_production = df_production.rename(columns={'country':'country_name'})
    df_use = pd.read_excel(os.path.join(cfg.data_path, 'original', 'worldsteel',
                                         "Steel_Statistical_Yearbook_combined.ods"),
                            sheet_name='Apparent Steel Use (Crude Steel Equivalent)', engine='odf', usecols='A:AC')
    df_use = df_use.rename(columns={'country': 'country_name'})
    return df_production, df_use

if __name__ == "__main__":
    production, use = get_worldsteel_production_and_use()
    print(production)
    print(use)
    # print(data)
