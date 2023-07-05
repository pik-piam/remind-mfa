import csv
import os
import numpy as np
import pandas as pd
import src.read_data.read_UN_population as pop
from src.read_data.read_REMIND_regions import get_region_to_countries_dict
from src.tools.config import cfg


YEARS = range(1900, 2101)


def load_imf_gdp():
    fname = os.path.join(cfg.data_path, 'processed', 'IMF_gdp.csv')
    if os.path.exists(fname) and not cfg.recalculate_data:
        with open(fname) as csv_file:
            regions = get_region_to_countries_dict()
            gdp_reader = csv.reader(csv_file, delimiter=',')
            gdp_reader = list(gdp_reader)
            gdp_dict = {}
            for region in regions.keys():
                gdp_dict[region] = {}
            for country_dates in gdp_reader:
                region = country_dates[0]
                if region == 'Total':
                    date = np.zeros(201, dtype='f4')
                    for i in range(201):
                        date[i] = float(country_dates[i + 1])
                    gdp_dict['Total'] = date
                    continue
                country = country_dates[1]
                date = np.zeros(201, dtype='f4')
                for i in range(201):
                    date[i] = float(country_dates[i + 2])
                gdp_dict[region][country] = date

            return gdp_dict
    else:
        gdp_data = aggregate()
        with open(fname, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Total'] + list(gdp_data['Total']))
            for region in gdp_data.keys():
                if region == 'Total':
                    continue
                region_data = gdp_data[region]
                for country in region_data.keys():
                    writer.writerow([region, country] + list(region_data[country]))
        return gdp_data


def aggregate():
    gdp_dict = extend()
    pop_dict = pop.load_un_pop()
    remind_dict = get_region_to_countries_dict()

    world_total = np.zeros(201, dtype='f4')
    final = {}
    for region in remind_dict.keys():
        region_total = np.zeros(201, dtype='f4')
        final[region] = {}
        for country in remind_dict[region]:
            if country in gdp_dict.keys():
                country_gdp = gdp_dict[country]
                final[region][country] = country_gdp
                country_pop = pop_dict[region][country]
                region_total += country_gdp * country_pop
        world_total += region_total
        region_total = np.divide(region_total, pop_dict[region]['Total'])
        final[region]["Total"] = region_total
    world_total = np.divide(world_total, pop_dict['Total'])
    final['Total'] = world_total

    return final


def extend():
    imf_data = read_imf_original()
    remind_dict = get_region_to_countries_dict()

    # extend to past based on OECD data
    # (here an array of average GDPpC values from 1900,1910...1950 for respective regions)
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

    for region in remind_dict.keys():
        # assume linear growth in each decade
        percentages = np.array(lin_values[region]) / lin_values[region][-1]
        for country in remind_dict[region]:
            if country in imf_data.keys():
                old_data = np.zeros(50, dtype='f4')
                index = -1
                current_data = imf_data[country]
                date1950 = current_data[0]
                current_value = date1950
                for decade in range(2, 7):  # data is calculated year by year BACKWARDS from 1950 on
                    decade_goal = percentages[-decade] * date1950
                    step = (current_value - decade_goal) / 10
                    for year in range(10):
                        current_value = current_value - step
                        old_data[index] = current_value
                        index -= 1
                new_date = np.append(old_data, current_data)
                imf_data[country] = new_date

    # extend to future based on IPCC assumptions
    lin_values = {'LAM': [2738.2, 4210.1, 6556.0, 9905.2, 14317.2, 19627.9, 26606.2, 36388.5, 47686.9, 60795.4],
                  'OAS': [873.7, 1553.2, 2837.7, 5139.5, 8819.4, 13804.2, 19837.3, 27431.3, 35626.4, 44069.4],
                  'SSA': [2378.6, 4378.7, 7868.6, 13380.5, 21343.7, 30936.4, 42882.5, 59159.7, 77741.4, 98993.7],
                  # according to South Africa
                  'EUR': [30131.7, 38187.4, 45863.7, 53609.2, 62283.6, 70840.8, 77152.1, 87018.1, 98251.1, 111071.1],
                  'NEU': [2378.6, 4378.7, 7868.6, 13380.5, 21343.7, 30936.4, 42882.5, 59159.7, 77741.4, 98993.7],
                  'MEA': [2738.2, 4210.1, 6556.0, 9905.2, 14317.2, 19627.9, 26606.2, 36388.5, 47686.9, 60795.4],
                  'REF': [2378.6, 4378.7, 7868.6, 13380.5, 21343.7, 30936.4, 42882.5, 59159.7, 77741.4, 98993.7],
                  'CAZ': [30131.7, 38187.4, 45863.7, 53609.2, 62283.6, 70840.8, 77152.1, 87018.1, 98251.1, 111071.1],
                  'CHA': [873.7, 1553.2, 2837.7, 5139.5, 8819.4, 13804.2, 19837.3, 27431.3, 35626.4, 44069.4],
                  'IND': [873.7, 1553.2, 2837.7, 5139.5, 8819.4, 13804.2, 19837.3, 27431.3, 35626.4, 44069.4],
                  'JPN': [30131.7, 38187.4, 45863.7, 53609.2, 62283.6, 70840.8, 77152.1, 87018.1, 98251.1, 111071.1],
                  'USA': [30131.7, 38187.4, 45863.7, 53609.2, 62283.6, 70840.8, 77152.1, 87018.1, 98251.1, 111071.1]}

    for region in remind_dict.keys():
        # assume linear growth in each decade
        percentages = np.array(lin_values[region]) / ((lin_values[region][1] + lin_values[region][0]) / 2)
        for country in remind_dict[region]:
            if country in imf_data.keys():
                future_data = np.zeros(85, dtype='f4')
                index = 0
                current_data = imf_data[country]
                date2015 = current_data[-1]
                current_value = date2015
                for decade in range(1, 10):  # data is calculated year by year BACKWARDS from 1950 on
                    decade_goal = percentages[decade] * date2015
                    step = (decade_goal - current_value) / 10
                    years_per_decade = 10
                    if decade == 1:  # just for 5 years (2015-2019)
                        step *= 2
                        years_per_decade = 5
                    for year in range(years_per_decade):
                        current_value = current_value + step
                        future_data[index] = current_value
                        index += 1
                new_date = np.append(current_data, future_data)
                imf_data[country] = new_date

    return imf_data


def read_imf_original():
    imf_raw = pd.read_excel(
        os.path.join(os.path.dirname(__file__), "../../data/original/IMF/", "GDPpC_210countries_1950-2015.xlsx"),
        engine='openpyxl', usecols=['Unnamed: 1', 'Unnamed: 2', 'Unnamed: 3', 'Unnamed: 5'])
    raw = []
    for i in range(2, len(imf_raw['Unnamed: 1'])):
        raw.append(
            [imf_raw['Unnamed: 1'][i], imf_raw['Unnamed: 2'][i], imf_raw['Unnamed: 3'][i], imf_raw['Unnamed: 5'][i]])

    with open(os.path.dirname(__file__) + '/../../data/original/Mueller/Mueller_countries.csv') as csv_file:
        mueller_countries = csv.reader(csv_file, delimiter=',')
        mueller_countries = list(mueller_countries)

    imf_dict = {}

    not_in_mueller_dict = []
    for i in raw:
        if i[0] in not_in_mueller_dict:
            continue
        if i[1] not in imf_dict.keys():  # create new dict entry
            # check if country is in mueller dict
            in_mueller_dict = False
            for j in mueller_countries[1:]:
                if i[1] == j[1]:
                    in_mueller_dict = True
                    imf_dict[i[1]] = []
                    break
            if not in_mueller_dict:
                not_in_mueller_dict.append(i[0])
                # print(i[0] + " not in mueller_dict")
                continue
        imf_dict[i[1]].append(float(i[3]))

    # make np.arrays
    for iso in imf_dict.keys():
        imf_dict[iso] = np.array(imf_dict[iso], dtype='f4')

    return imf_dict


def gdppc_dict_to_dfs(gdppc_dict: dict):
    gdppc_global = pd.DataFrame.from_dict({'GDP pC (USD 2005)': gdppc_dict.pop('Total'),
                                           'Year': YEARS})
    gdppc_regional = pd.concat([
        pd.DataFrame.from_dict({
            'region': [region for _ in YEARS],
            'GDP pC (USD 2005)': gdppc_reg['Total'],
            'Year': YEARS})
        for region, gdppc_reg in gdppc_dict.items()])
    return gdppc_global, gdppc_regional


if __name__ == "__main__":
    cfg.customize()
    data = load_imf_gdp()
    print(data)
