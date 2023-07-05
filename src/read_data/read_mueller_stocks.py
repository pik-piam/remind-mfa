import csv
import os
import numpy as np
import pandas as pd
from src.read_data.read_REMIND_regions import get_region_to_countries_dict
import src.read_data.read_UN_population as pop
from src.curve.predict_steel import predict
import src.read_data.read_IMF_gdp as gdp
from src.tools.tools import Years
from src.tools.config import cfg


PRODUCT_CATEGORIES = ['Transport', 'Machinery', 'Construction', 'Products']
NON_REGIONS = PRODUCT_CATEGORIES + ['Total']


def load_mueller_stocks():
    if os.path.exists(os.path.join(cfg.data_path, 'processed', 'mueller_stocks.csv')) and not cfg.recalculate_data:
        with open(os.path.join(cfg.data_path, 'processed', 'mueller_stocks.csv')) as csv_file:
            steel_dict = {}
            categories = ['Transport', 'Machinery', 'Construction', 'Products', 'Total']
            mueller_reader = csv.reader(csv_file, delimiter=',')
            mueller_reader = list(mueller_reader)

            for line in mueller_reader:
                line_data = np.zeros(201, dtype='f4')
                for i, num in enumerate(line[-201:]):
                    line_data[i] = float(num)
                region = line[0]
                country = line[1]
                category = line[2]
                if region in categories:
                    steel_dict[region] = line_data
                    continue
                if region not in steel_dict.keys():
                    steel_dict[region] = {}
                if country in categories:
                    steel_dict[region][country] = line_data
                    continue
                if country not in steel_dict[region].keys():
                    steel_dict[region][country] = {}
                steel_dict[region][country][category] = line_data

            return steel_dict

    else:
        aggregate_data = aggregate()
        categories = ['Transport', 'Machinery', 'Construction', 'Products', 'Total']
        with open(os.path.join(cfg.data_path, 'processed', 'mueller_stocks.csv'), 'w', newline='') as file:
            writer = csv.writer(file)
            for region in aggregate_data.keys():
                if region in categories:
                    writer.writerow([region] + list(aggregate_data[region]))
                else:
                    for country in aggregate_data[region].keys():
                        if country in categories:
                            writer.writerow([region, country] + list(aggregate_data[region][country]))
                        else:
                            for category in aggregate_data[region][country].keys():
                                writer.writerow([region, country, category] +
                                                list(aggregate_data[region][country][category]))
        return aggregate_data


def aggregate():
    steel_dict = split()
    categories = ['Transport', 'Machinery', 'Construction', 'Products']
    pop_dict = pop.load()
    regions = get_region_to_countries_dict()

    # Load values in stencil

    final = {}

    countries = steel_dict.keys()
    for region in regions.keys():
        final[region] = {}
        for country in regions[region]:
            if country in countries:
                final[region][country] = steel_dict[country]

    # Aggregate values for regions

    world_total = np.zeros(201, dtype='f4')
    for category in categories:
        final[category] = np.zeros(201, dtype='f4')
    for region in final.keys():
        if region not in categories:
            region_total = np.zeros(201, dtype='f4')
            for category in categories:
                category_total = np.zeros(201, dtype='f4')
                for country in final[region].keys():
                    if country not in categories:
                        category_total += final[region][country][category] * pop_dict[region][country]
                region_total += category_total
                final[category] += category_total
                final[region][category] = np.divide(category_total, pop_dict[region]['Total'])
            world_total += region_total
            final[region]['Total'] = np.divide(region_total, pop_dict[region]['Total'])
    world_total = np.divide(world_total, pop_dict['Total'])
    final['Total'] = world_total
    for category in categories:
        final[category] = np.divide(final[category], pop_dict['Total'])

    return final


def split():
    # load data and supporting data
    dict = extend()

    pauliuk_frame = pd.read_excel(
        os.path.join(os.path.join(cfg.data_path, 'original', 'Pauliuk', 'Supplementary_Table_23.xlsx')),
                     engine='openpyxl', sheet_name='Supplementray_Table_23', usecols='A:E')
    pauliuk_frame = pauliuk_frame.values.tolist()
    sector_splits = pauliuk_frame[3:]

    with open(os.path.join(cfg.data_path, 'original', 'Mueller', 'Mueller_countries.csv')) as csv_file:
        mueller_countries = csv.reader(csv_file, delimiter=',')
        mueller_countries = list(mueller_countries)

    # perform splits for countries

    steel_dict = {}
    for countryCode in dict.keys():
        country_name = None
        for i in mueller_countries:
            if i[1] == countryCode:
                country_name = i[0]
                break
        if country_name is None:
            raise ValueError('Country name not found: ' + country_name)

        sector_coefficients = None
        for i in sector_splits:
            if i[0] == country_name:
                sector_coefficients = [float(i[1]), float(i[2]), float(i[3]), float(i[4])]
                break
        if country_name in ['France', 'Netherlands', 'Belgium-Luxembourg']:
            sector_coefficients = [0.3, 0.1, 0.47, 0.13]
        if country_name == "New Caledonia":  # assume same distribution as Solomon Islands due to geographical proximity
            sector_coefficients = [0.11, 0.32, 0.47, 0.1]
        if country_name == "Taiwan":
            # assume distribution average of China [0.11,0.32,0.47,0.1], South Korea [0.29,0.25,0.31,0.15]
            # and Japan [0.3,0.1,0.47,0.13]
            sector_coefficients = [0.23, 0.22, 0.42, 0.13]

        transport = np.zeros(201, dtype='f4')
        machinery = np.zeros(201, dtype='f4')
        construction = np.zeros(201, dtype='f4')
        products = np.zeros(201, dtype='f4')
        for i, date in enumerate(list(dict[countryCode])):
            transport[i] = date * sector_coefficients[0]
            machinery[i] = date * sector_coefficients[1]
            construction[i] = date * sector_coefficients[2]
            products[i] = date * sector_coefficients[3]
        category_dict = {'Transport': transport, 'Machinery': machinery, 'Construction': construction,
                         'Products': products, 'Total': dict[countryCode]}

        steel_dict[countryCode] = category_dict

    return steel_dict


def extend():
    remind_dict = get_region_to_countries_dict()
    steel_dict = normalize_mueller()

    with open(os.path.join(cfg.data_path, 'original', 'Mueller', 'Mueller_countries.csv')) as csv_file:
        mueller_countries = csv.reader(csv_file, delimiter=',')
        mueller_countries = list(mueller_countries)
        mueller_iso = []
        for i in mueller_countries:
            mueller_iso.append(i[1])

    # predict future

    pop_dict = pop.load_un_pop()
    gdp_dict = gdp.load_imf_gdp()

    for region in remind_dict.keys():
        countries = remind_dict[region]
        for country in countries:
            if country not in mueller_iso:
                continue
            else:
                if country not in gdp_dict[region].keys():
                    continue
                country_pop = pop_dict[region][country]
                country_gdp = gdp_dict[region][country]
                country_steel = steel_dict[country]
                steel_dict[country] = predict(country_steel, country_pop[50:], country_gdp[50:], region)

    # predict past

    lin_values = {'LAM': [1129, 1433, 1540, 1795, 1981, 2502],
                  'OAS': [597, 674, 662, 756, 749, 675],
                  'SSA': [937, 1151, 1282, 1413, 2145, 2535],  # according to South Africa
                  'EUR': [2912, 3172, 3070, 4006, 4472, 4518],
                  'NEU': [1273, 1433, 927, 1597, 2097, 2583],
                  'MEA': [997, 1090, 1182, 1274, 1367, 1495],
                  'REF': [1273, 1433, 927, 1597, 2097, 2583],
                  'CAZ': [4013, 4915, 5396, 6025, 6837, 9258],
                  'CHA': [607, 646, 383, 723, 689, 655],
                  'IND': [597, 674, 662, 756, 749, 675],
                  'JPN': [607, 646, 383, 723, 689, 655],
                  'USA': [4013, 4915, 5396, 6025, 6837, 9258]}
    final_dict = {}
    for region in remind_dict.keys():
        current_lin_values = lin_values[region]
        countries = remind_dict[region]
        for country in countries:
            if country not in mueller_iso:
                continue
            else:
                if country not in gdp_dict[region].keys():
                    continue
                data = steel_dict[country]
                last_date = data[0]
                date_1950 = last_date
                past_data = np.zeros(50, dtype='f4')
                for decade in range(5):
                    percent_aim_decade = (current_lin_values[-1] - current_lin_values[-(decade + 2)]) / \
                                         current_lin_values[-1]
                    aim_decade = date_1950 * (1 - percent_aim_decade)
                    step = (last_date - aim_decade) / 10
                    for year in range(1, 11):
                        index = decade * 10 + year
                        new_date = last_date - step
                        past_data[-index] = new_date
                        last_date = new_date
                final_dict[country] = np.append(past_data, data)

    return final_dict


def normalize_mueller():
    """
    Steel data for aggregate countries in Mueller data need to be split into REMIND countries,
    e.g. Czechoslovakia into Czech Republic and Slovakia. Here, the share of the GDP of a country is used
    to calculate the country specific steel stocks.
    :return: dict where dict[iso3_code_of_country]=np.array(steel stock per capita of that country for the years
    1950-2008)
    """

    steel_dict = read_mueller_originial()
    todo = [['BEL', 'LUX'], ['CZE', 'SVK'], ['BIH', 'HRV', 'MKD', 'MNE', 'SVN', 'SRB'],
            ['ARM', 'AZE', 'BLR', 'EST', 'GEO', 'KAZ', 'KGZ', 'LTU', 'LVA', 'MDA', 'RUS', 'TJK', 'TKM', 'UKR', 'UZB']]

    pop_dict = pop.load_un_pop()
    gdp_dict = gdp.load_imf_gdp()

    for mix in todo:
        # get GDPs of respective countries (GDPpC * population)

        gdps = []
        stocks = []
        pops = []
        for country in mix:
            current_region = None
            for region in pop_dict.keys():
                if region == "Total":
                    continue
                if country in pop_dict[region].keys():
                    current_region = region
            country_pop = pop_dict[current_region][country][50:109]
            pops.append(country_pop)
            country_gdp_pc = gdp_dict[current_region][country][50:109]
            country_gdp = country_gdp_pc * country_pop  # to get total GDP data
            gdps.append(country_gdp)
            stocks.append(steel_dict[country] * country_pop)  # same for steel stock per capita

        total_gdp = np.zeros(59)
        for i in gdps:
            total_gdp += i

        total_stocks = np.zeros(59, dtype='f4')
        for i in stocks:
            total_stocks += i

        percentages = []
        for i in gdps:
            percentages.append(np.divide(i, total_gdp))

        for i in range(len(mix)):
            steel_dict[mix[i]] = np.divide(stocks[i] * percentages[i], pops[i])
    return steel_dict


def read_mueller_originial():
    with open(os.path.join(cfg.data_path, 'original', 'Mueller', 'Mueller_countries.csv')) as csv_file:
        mueller_countries = csv.reader(csv_file, delimiter=',')
        mueller_countries = list(mueller_countries)

    mueller_frame = pd.read_excel(os.path.join(cfg.data_path, 'original', 'Mueller',
                                               "Mueller_2013_CarbonEmissions_InfrastructureDevelopment_SI2.xlsx"),
                                  engine='openpyxl', sheet_name='steel stock per cap med', usecols='A:BH')
    mueller_frame = mueller_frame.values.tolist()
    mueller = mueller_frame[2:]

    data = []

    for j in mueller:
        for i in mueller_countries[1:]:  # only use countries that are in mueller countries list (e.g. not Antarctica)
            if i[0] == j[0]:
                data.append([i[1]] + j)

    dict = {}

    for countryData in data:
        country_code = countryData[0]
        country_date = np.zeros(59, dtype='f4')
        for i, date in enumerate(countryData[2:]):
            date = float(date)
            if date < 0:  # Optional: don't allow negative values
                date = 0
            country_date[i] = date
        dict[country_code] = country_date

    return dict


def transform_dict_to_dfs(stocks_dict: dict, years: Years):

    df_global = pd.DataFrame.from_dict({
        'stock_pc': stocks_dict['Total'][years.ids],
        'region': ['World' for _ in years.ids],
        'Year': years.calendar
    })

    df_regional = pd.concat([
        pd.DataFrame.from_dict({
            'stock_pc': stocks['Total'][years.ids],
            'region': [region for _ in years.ids],
            'Year': years.calendar
        }) for region, stocks in stocks_dict.items() if region not in NON_REGIONS])

    return df_global, df_regional


if __name__ == "__main__":
    cfg.customize()
    data = load_mueller_stocks()
    for region in data.keys():
        if region not in NON_REGIONS:
            print('\n' + region + '\n')
            for country in data[region].keys():
                if country not in NON_REGIONS:
                    print(country)
                    print(data[region][country]['Transport'][-5:])
