import csv
import os
from src.tools.config import cfg


def get_region_to_countries_dict():
    with open(os.path.join(cfg.data_path, 'processed', 'REMINDRegions.csv')) as csv_file:
        regions = csv.reader(csv_file, delimiter=',')
        regions = list(regions)
    region_dict = {}
    with open(os.path.join(cfg.data_path, 'original', 'Mueller', 'Mueller_countries.csv')) as csv_file:
        mueller_countries = csv.reader(csv_file, delimiter=',')
        mueller_countries = list(mueller_countries)
        mueller_iso = []
        for mueller_line in mueller_countries:
            mueller_iso.append(mueller_line[1])
    for region in regions:
        finalcountries = []
        for country in region[1:]:
            if country in mueller_iso:
                finalcountries.append(country)
        region_dict[region[0]] = finalcountries
    return region_dict


if __name__ == '__main__':
    cfg.customize()
    data = get_region_to_countries_dict()
    for i in data.keys():
        print(i)
        print(data[i])
