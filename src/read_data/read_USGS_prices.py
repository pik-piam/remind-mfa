import csv
import os
import numpy as np
import pandas as pd
from src.tools.config import cfg


def load():
    if os.path.exists(os.path.join(cfg.data_path, 'processed', 'USGS_price.csv')) and not cfg.recalculate_data:
        with open(os.path.join(cfg.data_path, 'processed', 'USGS_price.csv')) as csv_file:
            price_reader = csv.reader(csv_file, delimiter=',')
            price_reader = list(price_reader)
            price_dict = {}
            steel_prices = []
            scrap_prices = []
            for price_dates in price_reader:
                steel_prices.append(float(price_dates[1]))
                scrap_prices.append(float(price_dates[2]))
            price_dict['Steel'] = np.array(steel_prices)
            price_dict['Scrap'] = np.array(scrap_prices)
            return price_dict
    else:
        price_dict = extend()
        with open(os.path.join(cfg.data_path, 'processed', 'USGS_price.csv'), 'w', newline='') as file:
            writer = csv.writer(file)
            for i in range(201):
                writer.writerow([1900+i, price_dict['Steel'][i], price_dict['Scrap'][i]])
        return price_dict

def extend():
    price_dict = read_usgs_original()

    # simple assumption: scrap price stays constant before 1934 and after 2019,
    # steel price stays constant after 2010

    scrap_pre_1934 = [price_dict['Scrap_Relative'][0]]*34
    scrap_post_2019 = [price_dict['Scrap_Relative'][-1]]*81
    steel_post_2010 = [price_dict['Steel_Relative'][-1]]*90

    new_price_dict = {}
    new_price_dict['Steel'] = np.array(list(price_dict['Steel_Relative']) + steel_post_2010)
    new_price_dict['Scrap'] = np.array(scrap_pre_1934 + list(price_dict['Scrap_Relative']) + scrap_post_2019)

    return new_price_dict


def read_usgs_original():
    steel_data = pd.read_excel(os.path.join(cfg.data_path, 'original', 'US_Geological_Survey', "ds140-iron-steel-2019.xlsx"),
                            engine='openpyxl', sheet_name='Steel',
                            usecols=['Unnamed: 8', 'Unnamed: 9'])

    scrap_data = pd.read_excel(
        os.path.join(cfg.data_path, 'original', 'US_Geological_Survey', "ds140-iron-steel-scrap-2019.xlsx"),
        engine='openpyxl', sheet_name='Iron and Steel Scrap',
        usecols=['Unnamed: 6', 'Unnamed: 7'])

    raw_steel_total = []
    raw_steel_98 = []
    raw_scrap_total = []
    raw_scrap_98 = []

    for i in range(5,116):
        raw_steel_total.append(steel_data['Unnamed: 8'][i])
        raw_steel_98.append(steel_data['Unnamed: 9'][i])

    for i in range(4,90):
        raw_scrap_total.append(scrap_data['Unnamed: 6'][i])
        raw_scrap_98.append(scrap_data['Unnamed: 7'][i])

    price_dict = {}
    price_dict['Steel_Absolute'] = np.array(raw_steel_total)
    price_dict['Steel_Relative'] = np.array(raw_steel_98)
    price_dict['Scrap_Absolute'] = np.array(raw_scrap_total)
    price_dict['Scrap_Relative'] = np.array(raw_scrap_98)

    return price_dict


if __name__ == "__main__":
    cfg.customize()
    data = load()
    print(data)
