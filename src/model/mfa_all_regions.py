import numpy as np
import pandas as pd
import os
import sys
import pickle
import csv
import src.read_data.read_REMIND_regions as remind
import src.model.load_DSMs as dynamic_stock_models
import src.read_data.read_WorldSteel_trade as worldsteel_trade
from src.tools.config import cfg
from ODYM.odym.modules import ODYM_Classes as msc  # import the ODYM class file


#  constants
USING_CATEGORIES = ['Transport', 'Machinery', 'Construction', 'Products']
RECYCLING_CATEGORIES = ['CD', 'MSW', 'WEEE', 'ELV', 'IEW', 'INEW', 'Dis', 'NotCol']
REGIONS = ['CAZ', 'CHA', 'EUR', 'IND', 'JPN', 'LAM', 'MEA', 'NEU', 'OAS', 'REF', 'SSA', 'USA']

# Indices
ENV_PID = 0
PROD_PID = 1
FIN_PID = 2
SCRAP_PID = 3
USE_PID = 4
RECYCLE_PID = 5
WASTE_PID = 6


def load_dmfa_systems() -> msc.MFAsystem:
    """
    Loads dictionary of DMFA systems either from file or by recalculating it.
    :param recalculate: bool
    :return: dict[region]=MFA_system
    """
    # load data and dynamic stock models

    file_path = os.path.join(cfg.data_path, 'models', "main_model.p")
    do_load_existing = os.path.exists(file_path) and not cfg.recalculate_data
    if do_load_existing:
        model = pickle.load(open(file_path, "rb"))
    else:
        model = create_model()
        pickle.dump(model, open(file_path, "wb"))
    return model


def create_model():
    """
    Creates dictionary of DMFA systems based on region names.
    :return: Dictionary of DMFA systems.
    """

    # initiate model, load data
    main_model = initiate_model()
    dsm_dict = dynamic_stock_models.load()
    trade_dict = None
    if cfg.include_trade:
        trade_dict = worldsteel_trade.load_world_steel_trade()

    # compute stocks and flows
    for region_idx, region in enumerate(REGIONS):
        main_model = compute_flows(main_model, region_idx, dsm_dict[region], trade_dict[region])
        main_model = compute_stocks(main_model, region_idx, dsm_dict[region])

    return main_model


def initiate_model():
    """
        Main part of the model! Computes an ODYM DMFA System based on a dynamic
        stock model and trade data. Processes, Flows and Stocks are defined,
        initiated and calculated based on parameters from the config file.
        :param model_dict: dynamic stock model
        :param region: region name (str)
        :return: DMFAsystem
        """

    # define MFA system

    model_classification = {'Time': msc.Classification(Name='Time', Dimension='Time', ID=1,
                                                       Items=list(np.arange(cfg.start_year, cfg.end_year))),
                            'Element': msc.Classification(Name='Elements', Dimension='Element', ID=2, Items=['Fe']),
                            'Region': msc.Classification(Name='Regions', Dimension='Region', ID=3, Items=REGIONS),
                            'Good': msc.Classification(Name='Goods', Dimension='Material', ID=4,
                                                       Items=USING_CATEGORIES),
                            'Waste': msc.Classification(Name='Waste types', Dimension='Material', ID=5,
                                                        Items=RECYCLING_CATEGORIES)}
    model_time_start = int(min(model_classification['Time'].Items))
    model_time_end = int(max(model_classification['Time'].Items))
    index_table = pd.DataFrame({'Aspect': ['Time', 'Element', 'Region', 'Good', 'Waste'],
                                'Description': ['Model aspect "Time"', 'Model aspect "Element"',
                                                'Model aspect "Region"', 'Model aspect "Good"',
                                                'Model aspect "Waste"'],
                                'Dimension': ['Time', 'Element', 'Region', 'Material', 'Material'],
                                'Classification': [model_classification[Aspect] for Aspect in
                                                   ['Time', 'Element', 'Region', 'Good', 'Waste']],
                                'IndexLetter': ['t', 'e', 'r', 'g', 'w']})
    index_table.set_index('Aspect', inplace=True)

    main_model = msc.MFAsystem(Name='World Steel Economy',
                               Geogr_Scope='World',
                               Unit='kt',
                               ProcessList=[],
                               FlowDict={},
                               StockDict={},
                               ParameterDict={},
                               Time_Start=model_time_start,
                               Time_End=model_time_end,
                               IndexTable=index_table,
                               Elements=index_table.loc['Element'].Classification.Items)

    # Define and initialize processes, parameters, flows and stocks

    # Processes

    main_model.ProcessList = []

    def add_process(name, p_id):
        main_model.ProcessList.append(msc.Process(Name=name, ID=p_id))

    add_process('Primary Production / Environment', ENV_PID)
    add_process('Production', PROD_PID)
    add_process('Usable Scrap', SCRAP_PID)
    add_process('NewSteel', FIN_PID)
    add_process('Using', USE_PID)
    add_process('Recycling', RECYCLE_PID)
    add_process('Waste', WASTE_PID)

    # Parameters

    # load parameter data

    parameter_dict = {}

    use_recycling_params = [[], [], [], []]
    recycling_usable_params = []
    with open(os.path.dirname(
            __file__) + '/../../data/original/Wittig/Wittig_matrix.csv') as csv_file:
        wittig_reader = csv.reader(csv_file, delimiter=',')
        wittig_list = list(wittig_reader)
        for line in wittig_list:
            for i, num in enumerate(line[1:-1]):
                use_recycling_params[i].append(float(num))
            recycling_usable_params.append(float(line[-1]))

    parameter_dict['End-Use_Distribution'] = msc.Parameter(Name='End-Use_Distribution', ID=0, P_Res=USE_PID,
                                                           MetaData=None, Indices='gw',
                                                           Values=np.array(use_recycling_params), Unit='1')

    parameter_dict['Recycling-Waste_Distribution'] = msc.Parameter(Name='Recycling-Waste_Distribution', ID=0,
                                                                   P_Res=RECYCLE_PID,
                                                                   MetaData=None, Indices='w',
                                                                   Values=np.array(recycling_usable_params), Unit='1')

    main_model.ParameterDict = parameter_dict

    # Flows

    def add_flow(name, from_id, to_id, indices):
        flow = msc.Flow(Name=name, P_Start=from_id, P_End=to_id, Indices=indices, Values=None)
        main_model.FlowDict['F_' + str(from_id) + '_' + str(to_id)] = flow

    add_flow('Primary Production - Production', ENV_PID, PROD_PID, 't,e,r')
    add_flow('Usable Scrap - Production', SCRAP_PID, PROD_PID, 't,e,r')
    add_flow('Production - Final Steel', PROD_PID, FIN_PID, 't,e,r')

    add_flow('Final Steel - Using', FIN_PID, USE_PID, 't,e,r,g')
    add_flow('Using - Recycling', USE_PID, RECYCLE_PID, 't,e,r,g,w')
    add_flow('Recycling - Usable Scrap', RECYCLE_PID, SCRAP_PID, 't,e,r,w')
    add_flow('Recycling - Waste', RECYCLE_PID, WASTE_PID, 't,e,r,w')

    if cfg.include_trade:
        add_flow('Imports', ENV_PID, FIN_PID, 't,e,r')
        add_flow('Exports', FIN_PID, ENV_PID, 't,e,r')

    if cfg.include_scrap_trade:
        add_flow('Scrap_Imports', ENV_PID, SCRAP_PID, 't,e,r')
        add_flow('Scrap_Exports', SCRAP_PID, ENV_PID, 't,e,r')

    # Stocks

    def add_stock(p_id, name, indices, add_change_stock=True):
        name = name + '_Stock'
        main_model.StockDict['S_' + str(p_id)] = msc.Stock(Name=name, P_Res=p_id, Type=0, Indices=indices,
                                                           Values=None)
        if add_change_stock:
            main_model.StockDict['dS_' + str(p_id)] = msc.Stock(
                Name=name + "_change",
                P_Res=p_id, Type=1,
                Indices=indices, Values=None)

    add_stock(USE_PID, 'In-Use', 't,e,r,g')
    add_stock(SCRAP_PID, 'Usable_Scrap', 't,e,r')
    add_stock(WASTE_PID, 'Waste', 't,e,r')

    # initialize, optional: perform consistency check

    main_model.Initialize_FlowValues()
    main_model.Initialize_StockValues()
    consistency = main_model.Consistency_Check()
    for consistencyCheck in consistency:
        if not consistencyCheck:
            raise RuntimeError("A consitency check failed: " + str(consistency))

    return main_model


def compute_flows(main_model, region_idx, region_dsm, region_trade):
    """
    load data, calculate values, implement MFA solution from chosen model
    :param main_model:
    :param regions:
    :return:
    """

    # Flows

    params = main_model.ParameterDict

    def get_flow(from_id, to_id):
        return main_model.FlowDict['F_' + str(from_id) + '_' + str(to_id)]

    fin_use_flow = get_flow(FIN_PID, USE_PID)
    for UID, using_category in enumerate(USING_CATEGORIES):
        values = region_dsm[using_category].i
        fin_use_flow.Values[:, 0, region_idx, UID] = values
    total_inflow_in_use_stock = np.sum(fin_use_flow.Values[:, 0, region_idx, :], axis=1)

    if not cfg.include_trade:
        get_flow(PROD_PID, FIN_PID).Values[:, 0, region_idx] = total_inflow_in_use_stock

    category_outflow = []
    for UID, using_category in enumerate(USING_CATEGORIES):
        category_outflow.append(region_dsm[using_category].o)

    get_flow(USE_PID, RECYCLE_PID).Values[:, 0, region_idx, :, :] = np.einsum('gt,gw->tgw', np.array(category_outflow),
                                                                              params['End-Use_Distribution'].Values)

    recycling_inflow = np.sum(get_flow(USE_PID, RECYCLE_PID).Values[:, 0, region_idx, :, :], axis=1)
    get_flow(RECYCLE_PID, SCRAP_PID).Values[:, 0, region_idx, :] = np.einsum('tw,w->tw', recycling_inflow, params[
        'Recycling-Waste_Distribution'].Values)
    get_flow(RECYCLE_PID, WASTE_PID).Values[:, 0, region_idx, :] = np.einsum('tw,w->tw', recycling_inflow, 1 - params[
        'Recycling-Waste_Distribution'].Values)

    total_production = total_inflow_in_use_stock
    if cfg.include_trade:
        imports = region_trade['Imports']
        exports = region_trade['Exports']
        get_flow(ENV_PID, FIN_PID).Values[:, 0, region_idx] = imports
        get_flow(FIN_PID, ENV_PID).Values[:, 0, region_idx] = exports
        total_production+= - imports + exports
        get_flow(PROD_PID, FIN_PID).Values[:, 0, region_idx] = total_production

    max_scrap_share_production = get_flow(PROD_PID, FIN_PID).Values[:, 0, region_idx]
        * cfg.max_scrap_share_production
    inflow_usable_scrap = np.sum(get_flow(RECYCLE_PID, SCRAP_PID).Values[:, 0, region_idx, :], axis=1)

    if cfg.include_scrap_trade:
        scrap_imports = region_trade['Scrap_Imports']
        scrap_exports = region_trade['Scrap_Exports']
        get_flow(ENV_PID, SCRAP_PID).Values[:, 0, region_idx] = scrap_imports
        get_flow(SCRAP_PID, ENV_PID).Values[:, 0, region_idx] = scrap_exports
        inflow_usable_scrap += scrap_imports-scrap_exports

    recyclable = np.zeros(cfg.n_years)
    usable_scrap_stock = 0
    for i in range(cfg.n_years):
        available_from_inflow = inflow_usable_scrap[i]
        max_scrap = max_scrap_share_production[i]
        if available_from_inflow > max_scrap:
            recyclable[i] = max_scrap
            usable_scrap_stock += available_from_inflow - max_scrap
        else:
            if available_from_inflow + usable_scrap_stock > max_scrap:
                recyclable[i] = max_scrap
                usable_scrap_stock -= max_scrap - available_from_inflow
            else:
                recyclable[i] = available_from_inflow + usable_scrap_stock
                usable_scrap_stock = 0

    get_flow(SCRAP_PID, PROD_PID).Values[:, 0, region_idx] = recyclable
    get_flow(ENV_PID, PROD_PID).Values[:, 0, region_idx] = total_production - recyclable

    return main_model


def compute_stocks(main_model, region_idx, region_dsm):
    # Stocks
    # In-use stocks
    def get_flow(from_id, to_id):
        return main_model.FlowDict['F_' + str(from_id) + '_' + str(to_id)]

    def get_stock(p_id):
        return main_model.StockDict['S_' + str(p_id)]

    def get_stock_change(p_id):
        return main_model.StockDict['dS_' + str(p_id)]

    def calculate_stock_values_from_stock_change(p_id):
        stock_values = main_model.StockDict['dS_' + str(p_id)].Values[:, 0, region_idx].cumsum(axis=0)
        main_model.StockDict['S_' + str(p_id)].Values[:, 0, region_idx] = stock_values

    in_use_stock = get_stock(USE_PID)
    in_use_stock_change = get_stock_change(USE_PID)
    for UID, category in enumerate(USING_CATEGORIES):
        category_model = region_dsm[category]
        in_use_stock.Values[:, 0, region_idx, UID] = category_model.s
        in_use_stock_change.Values[:, 0, region_idx, UID] = category_model.i - category_model.o

    inflow_waste = np.sum(get_flow(RECYCLE_PID, WASTE_PID).Values[:, 0, region_idx, :], axis=1)
    get_stock_change(WASTE_PID).Values[:, 0, region_idx] = inflow_waste
    calculate_stock_values_from_stock_change(WASTE_PID)
    inflow_usable_scrap = np.sum(get_flow(RECYCLE_PID, SCRAP_PID).Values[:, 0, region_idx, :], axis=1)
    recyclable = get_flow(SCRAP_PID, PROD_PID).Values[:, 0, region_idx]
    get_stock_change(SCRAP_PID).Values[:, 0, region_idx] = inflow_usable_scrap - recyclable
    calculate_stock_values_from_stock_change(SCRAP_PID)

    return main_model


def mass_balance_plausible(balance):
    """
    Checks if a given mass balance is plausible.
    :param balance: Mass Balance from Dyn_MFA_System.
    :return: True if the mass balance for all processes is below 1kg (0.001 t) of steel, False otherwise.
    """

    for val in np.abs(balance).sum(axis=0).sum(axis=1):
        if val > 1000: # account for a ton accuracy
            print(list(np.abs(balance).sum(axis=0)))
            return False
    return True


def main():
    """
    Recalculates the DMFA dict based on the dynamic stock models and trade data.
    Checks the Mass Balance and raises a runtime error if the mass balance is too big.
    Prints success statements otherwise
    :return: None
    """
    main_model = load_dmfa_systems()
    bal = main_model.MassBalance()
    if mass_balance_plausible(bal):
        print("Success - Model loaded and checked. \nBalance: " + str(list(np.abs(bal).sum(axis=0).sum(axis=1))))
    else:
        raise RuntimeError(
            "Error, Mass Balance summary below\n" + str(np.abs(bal).sum(axis=0).sum(axis=1)))


if __name__ == "__main__":
    # overwrite config with valus given in a config file,
    # if the path to this file is passed as the last argument of the function call.
    if sys.argv[-1].endswith('.yml'):
        cfg.customize(sys.argv[-1])
    main()
