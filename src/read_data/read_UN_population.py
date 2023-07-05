import csv
import os
import yaml
import numpy as np
import pandas as pd
from src.read_data.read_REMIND_regions import get_region_to_countries_dict
from src.tools.config import cfg


def load_un_pop():
    if os.path.exists(os.path.join(cfg.data_path, 'processed', 'UN_pop.csv')) and not cfg.recalculate_data:
        with open(os.path.join(cfg.data_path, 'processed', 'UN_pop.csv')) as csv_file:
            regions = get_region_to_countries_dict()
            pop_reader = csv.reader(csv_file, delimiter=',')
            pop_reader = list(pop_reader)
            pop_dict = {}
            for region in regions.keys():
                pop_dict[region] = {}
            for country_dates in pop_reader:
                region = country_dates[0]
                if region == 'Total':
                    date = np.zeros(201, dtype='f4')
                    for i in range(201):
                        date[i] = float(country_dates[i + 1])
                    pop_dict['Total'] = date
                    continue
                country = country_dates[1]
                date = np.zeros(201, dtype='f4')
                for i in range(201):
                    date[i] = float(country_dates[i + 2])
                pop_dict[region][country] = date

            return pop_dict

    else:
        pop_data = aggregate()
        with open(os.path.join(cfg.data_path, 'processed', 'UN_pop.csv'), 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Total'] + list(pop_data['Total']))
            for region in pop_data.keys():
                if region == 'Total':
                    continue
                region_data = pop_data[region]
                for country in region_data.keys():
                    writer.writerow([region, country] + list(region_data[country]))
        return pop_data


def aggregate():
    regions = get_region_to_countries_dict()
    pop_data = extend()
    pop_dict = {}
    world_pop = np.zeros(201, dtype='f4')
    for region in regions.keys():
        pop_dict[region] = {}
        region_pop = np.zeros(201, dtype='f4')
        for country in regions[region]:
            pop_dict[region][country] = pop_data[country]
            region_pop += pop_data[country]
        pop_dict[region]['Total'] = region_pop
        world_pop += region_pop
    pop_dict['Total'] = world_pop

    return pop_dict


def extend():
    pop_dict = read_pop_originial()
    lin_values = [1650, 1750, 1860, 2070, 2300, 2557]
    for country in pop_dict.keys():
        country_pop_past = np.zeros(50, dtype='f4')
        country_pop_future = pop_dict[country]
        last_value = country_pop_future[0]
        country_pop_1950 = last_value
        index = -1
        for decade in range(5):
            percent_new_aim = (lin_values[-1] - lin_values[-(decade + 2)]) / lin_values[-1]
            new_aim = country_pop_1950 * (1 - percent_new_aim)
            step = (last_value - new_aim) / 10
            for year in range(1, 11):
                new_value = last_value - step
                last_value = new_value
                country_pop_past[index] = new_value
                index -= 1
        pop_dict[country] = np.append(country_pop_past, country_pop_future)
    return pop_dict


def read_pop_originial():
    # population 1950-2021

    with open(os.path.join(cfg.data_path, 'original', 'Mueller', 'Mueller_countries.csv')) as csv_file:
        mueller_countries = csv.reader(csv_file, delimiter=',')
        mueller_countries = list(mueller_countries)
        mueller_iso = []
        for i in mueller_countries:
            mueller_iso.append(i[1])

    pop_old = pd.read_excel(os.path.join(cfg.data_path, 'original', 'UN', "UN_Population_1950-2021.xlsx"),
                            engine='openpyxl', sheet_name='Estimates',
                            usecols=['Unnamed: 2', 'Unnamed: 5', 'Unnamed: 10', 'Unnamed: 11'])

    pop_old.to_csv()

    # population predictions 2022-2100

    pop_new = pd.read_excel(os.path.join(cfg.data_path, 'original', 'UN', "UN_Population_2022-2100.xlsx"),
                            engine='openpyxl', sheet_name='Median', usecols="C,F,K:CK")

    pop_new.to_csv()

    pop_dict = {}
    for i in mueller_iso:
        pop_dict[i] = []

    for i in range(2, len(pop_old['Unnamed: 2'])):
        iso = pop_old['Unnamed: 5'][i]
        if iso in mueller_iso:
            pop_dict[iso].append(str(1000 * float(pop_old['Unnamed: 11'][i])))
    for i in range(2, len(pop_new['Unnamed: 2'])):
        for j in range(79):
            year_column_string = 'Unnamed: ' + str(j + 10)
            country_iso = pop_new['Unnamed: 5'][i]
            if country_iso in mueller_iso:
                pop_dict[country_iso].append(str(1000 * float(pop_new[year_column_string][i])))

    for country in mueller_iso:
        if len(pop_dict[country]) < 151:
            pop_dict.pop(country, None)

    # make np.arrays
    for iso in pop_dict.keys():
        pop_dict[iso] = np.array(pop_dict[iso], dtype='f4')

    return pop_dict


if __name__ == "__main__":
    cfg.customize()
    data = load_un_pop()
    for r in data.keys():
        if r == 'Total':
            continue
        for c in data[r].keys():
            # print(data[r][c][:5])
            print(r + c)
            continue
