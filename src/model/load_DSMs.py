from ODYM.odym.modules import dynamic_stock_model as dsm  # import the dynamic stock model library
import src.read_data.read_mueller_stocks as mueller
import src.read_data.read_UN_population as pop
import numpy as np
import pickle
import pandas as pd
import src.read_data.read_REMIND_regions as remind
from src.read_data.load_data import load_lifetimes
from src.tools.config import cfg
import csv
import os
from src.read_data.load_data import load_stocks, load_lifetimes


def load():
    """
    Loads dict of dynamic stock models either from file or recalculates and then stores them.
    :param recalculate:
    :return: dict[region][category]=dynamic_stock_model
    """
    categories = ['Transport', 'Machinery', 'Construction', 'Products', 'Total']
    if len(os.listdir(os.path.join(cfg.data_path, 'models', 'dynamic_stock_models'))) == 60 and not cfg.recalculate_data:
        models = {}
        for region in remind.get_region_to_countries_dict().keys():
            models[region] = {}
            for category in categories:
                filename = "dsm_" + region + "_" + category
                dsm_dict = pickle.load(open(os.path.join(cfg.data_path, 'models', 'dynamic_stock_models',
                                                         filename + ".p", "rb")))
                dsm_model = dsm_dict[filename]
                models[region][category] = dsm_model
        return models
    else:
        models = initiate_models()

        for region in models.keys():
            for category in categories:
                filename = "dsm_" + region + "_" + category
                pickle.dump({filename: models[region][category]},
                            open(os.path.join(cfg.data_path, 'models', 'dynamic_stock_models', filename + ".p"), "wb"))

        return models


def get_dsm_data(stock_data):
    mean, std_dev = load_lifetimes()
    dsms = [_create_dsm(stocks, mean[i], std_dev[i]) for i, stocks in enumerate(stock_data)]
    stocks = np.array([dsm.s for dsm in dsms]).transpose()
    inflows = np.array([dsm.i for dsm in dsms]).transpose()
    outflows = np.array([dsm.o for dsm in dsms]).transpose()

    return stocks, inflows, outflows


def _create_dsm(stocks, lifetime, st_dev):
    time = np.array(range(cfg.n_years))
    steel_stock_dsm = dsm.DynamicStockModel(t=time,
                                            s=stocks,
                                            lt={'Type': 'Normal', 'Mean': [lifetime],
                                                'StdDev': [st_dev]})

    steel_stock_dsm.compute_stock_driven_model()
    steel_stock_dsm.compute_outflow_total()
    steel_stock_dsm.compute_stock_change()

    return steel_stock_dsm

def initiate_models():
    """
    Calculates the dynamic stock models of all regions for all using_categories.
    Can choose which dataset to use based on parameters in config file.
    Steel and population datasets need to be complete, so a total needs to be available for all years past and future
    (1900-2100) and for steel also for the respective using_categories. Additionally, lifetime (and it's SD)
    values are used to calculate outflow from steel stock.
    :return: dict[region][category]=dynamic_stock_model
    :return:
    """

    # load data

    regions = remind.get_region_to_countries_dict()
    pop_data = pop.load_un_pop()
    steel_data = None
    if cfg.steel_data_source == "Mueller":
        steel_data = mueller.load_mueller_stocks()
    categories = ['Transport', 'Machinery', 'Construction', 'Products', 'Total']

    # get total data from per capita data

    for region in steel_data.keys():
        if region in categories:
            steel_data[region] *= pop_data['Total']
            continue
        else:
            for category in categories:
                steel_data[region][category] *= pop_data[region]['Total']

    # get lifetimes

    lifetimes = None
    if cfg.lifetime_data_source == "Wittig":
        with open(os.path.join(cfg.data_path, 'original', 'Wittig', 'Wittig_lifetimes.csv')) as csv_file:
            wittig_reader = csv.reader(csv_file, delimiter=',')
            wittig_lifetimes = list(wittig_reader)
        lifetimes = {}
        for category in categories:
            for line in wittig_lifetimes:
                if line[0] == category:
                    lifetimes[category] = line[1:]

    # initiate models

    models = {}
    time = np.array(range(cfg.n_years))

    for region in regions.keys():
        models[region] = {}
        for category in categories:
            steel_stock_dsm = dsm.DynamicStockModel(t=time, s=steel_data[region][category],
                                                    lt={'Type': 'Normal', 'Mean': [float(lifetimes[category][0])],
                                                        'StdDev': [float(lifetimes[category][1])]})
            steel_stock_dsm.compute_stock_driven_model()
            steel_stock_dsm.compute_outflow_total()
            steel_stock_dsm.compute_stock_change()
            models[region][category] = steel_stock_dsm

    return models


def main():
    """
    Recalculates dynamic stock models from steel and population data for all REMIND regions.
    Both datasets need to be complete, so a total needs to be available for all years past and future
    (1900-2100) and for steel also for the respective using_categories. Additionally, lifetime (and it's SD)
    values are used to calculate outflow from steel stock.
    :return: dict[region][category]=dynamic_stock_model
    """
    models = load()
    for region in models.keys():
        for category in models[region].keys():
            model = models[region][category]
            Balance = model.check_stock_balance()
            Balance = np.abs(Balance).sum()
            if Balance > 1:  # 1 tonne accuracy
                raise RuntimeError("Stock balance for model " + region + " " + category + " is too high: " + str(Balance))
            elif Balance > 0.001:
                print("Stock balance for model " + region + " " + category + " is noteworthy: " + str(Balance))


if __name__ == '__main__':
    cfg.customize()
    main()
