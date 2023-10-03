import numpy as np
import pandas as pd
import os
import sys
import pickle
import csv
from ODYM.odym.modules import ODYM_Classes as msc  # import the ODYM class file
from src.tools.config import cfg
from src.model.model_tools import get_dsm_data, get_stock_data_country_specific_areas
from src.model.load_dsms import load_dsms
from src.model.calc_trade import get_all_trade

#  constants

#  Indices
ENV_PID = 0
PROD_PID = 1
FIN_PID = 2
SCRAP_PID = 3
USE_PID = 4
RECYCLE_PID = 5
WASTE_PID = 6


def load_simson_model(country_specific=False, recalculate=cfg.recalculate_data) -> msc.MFAsystem:
    file_name_end = 'countries' if country_specific else f'{cfg.region_data_source}_regions'
    file_name = f'main_model_{file_name_end}.p'
    file_path = os.path.join(cfg.data_path, 'models', file_name)
    do_load_existing = os.path.exists(file_path) and not recalculate
    if do_load_existing:
        model = pickle.load(open(file_path, "rb"))
    else:
        model = create_base_model(country_specific)
        pickle.dump(model, open(file_path, "wb"))
    return model


def create_base_model(country_specific):
    dsms = load_dsms(country_specific)
    return create_model(country_specific, dsms)


def create_model(country_specific, dsms, scrap_share_in_production=None):
    n_regions = len(dsms)
    n_scenarions = len(dsms[0][0])
    max_scrap_share_in_production = np.ones([cfg.n_years, n_regions, n_scenarions]) * cfg.max_scrap_share_production
    if scrap_share_in_production is not None:
        max_scrap_share_in_production[cfg.econ_base_year - cfg.start_year + 1:, :] = scrap_share_in_production
        # TODO change cfg file for starting index
    # load data
    areas = get_stock_data_country_specific_areas(country_specific)
    trade_all_areas, scrap_trade_all_areas = get_all_trade(country_specific=country_specific, dsms=dsms)
    main_model = set_up_model(areas)

    # Load model
    initiate_model(main_model)

    # compute stocks and flows
    compute_model(main_model, dsms, trade_all_areas, scrap_trade_all_areas, max_scrap_share_in_production)

    # check model
    mass_balance_plausible(main_model)

    return main_model


def initiate_model(main_model):
    initiate_processes(main_model)
    initiate_parameters(main_model)
    initiate_flows(main_model)
    initiate_stocks(main_model)
    main_model.Initialize_FlowValues()
    main_model.Initialize_StockValues()
    check_consistency(main_model)


def compute_model(main_model, dsms, trade_all_areas, scrap_trade_all_areas, max_scrap_share_in_production):
    stocks, inflows, outflows = get_dsm_data(dsms)
    compute_area_flows(main_model, inflows, outflows,
                       trade_all_areas, scrap_trade_all_areas,
                       max_scrap_share_in_production)
    compute_area_stocks(main_model, stocks, inflows, outflows)


def set_up_model(regions):
    model_classification = {'Time': msc.Classification(Name='Time', Dimension='Time', ID=1,
                                                       Items=cfg.years),
                            'Element': msc.Classification(Name='Elements', Dimension='Element', ID=2, Items=['Fe']),
                            'Region': msc.Classification(Name='Regions', Dimension='Region', ID=3, Items=regions),
                            'Good': msc.Classification(Name='Goods', Dimension='Material', ID=4,
                                                       Items=cfg.using_categories),
                            'Waste': msc.Classification(Name='Waste types', Dimension='Material', ID=5,
                                                        Items=cfg.recycling_categories),
                            'Scenario': msc.Classification(Name='Scenario', Dimension='Scenario', ID=6,
                                                           Items=cfg.scenarios)}
    model_time_start = cfg.start_year
    model_time_end = cfg.end_year
    index_table = pd.DataFrame({'Aspect': ['Time', 'Element', 'Region', 'Good', 'Waste', 'Scenario'],
                                'Description': ['Model aspect "Time"', 'Model aspect "Element"',
                                                'Model aspect "Region"', 'Model aspect "Good"',
                                                'Model aspect "Waste"', 'Model aspect "Scenario"'],
                                'Dimension': ['Time', 'Element', 'Region', 'Material', 'Material', 'Scenario'],
                                'Classification': [model_classification[Aspect] for Aspect in
                                                   ['Time', 'Element', 'Region', 'Good', 'Waste', 'Scenario']],
                                'IndexLetter': ['t', 'e', 'r', 'g', 'w', 's']})
    index_table.set_index('Aspect', inplace=True)

    main_model = msc.MFAsystem(Name='World Steel Economy',
                               Geogr_Scope='World',
                               Unit='t',
                               ProcessList=[],
                               FlowDict={},
                               StockDict={},
                               ParameterDict={},
                               Time_Start=model_time_start,
                               Time_End=model_time_end,
                               IndexTable=index_table,
                               Elements=index_table.loc['Element'].Classification.Items)

    return main_model


def initiate_processes(main_model):
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


def initiate_parameters(main_model):
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


def initiate_flows(main_model):
    def add_flow(name, from_id, to_id, indices):
        flow = msc.Flow(Name=name, P_Start=from_id, P_End=to_id, Indices=indices, Values=None)
        main_model.FlowDict['F_' + str(from_id) + '_' + str(to_id)] = flow

    add_flow('Primary Production - Production', ENV_PID, PROD_PID, 't,e,r,s')
    add_flow('Usable Scrap - Production', SCRAP_PID, PROD_PID, 't,e,r,s')
    add_flow('Production - Final Steel', PROD_PID, FIN_PID, 't,e,r,s')

    add_flow('Final Steel - Using', FIN_PID, USE_PID, 't,e,r,g,s')
    add_flow('Using - Recycling', USE_PID, RECYCLE_PID, 't,e,r,g,w,s')
    add_flow('Recycling - Usable Scrap', RECYCLE_PID, SCRAP_PID, 't,e,r,w,s')
    add_flow('Recycling - Waste', RECYCLE_PID, WASTE_PID, 't,e,r,w,s')

    if cfg.include_trade:
        add_flow('Imports', ENV_PID, FIN_PID, 't,e,r,s')
        add_flow('Exports', FIN_PID, ENV_PID, 't,e,r,s')
        add_flow('Scrap_Imports', ENV_PID, SCRAP_PID, 't,e,r,s')
        add_flow('Scrap_Exports', SCRAP_PID, ENV_PID, 't,e,r,s')


def initiate_stocks(main_model):
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

    add_stock(USE_PID, 'In-Use', 't,e,r,g,s')
    add_stock(SCRAP_PID, 'Usable_Scrap', 't,e,r,s')
    add_stock(WASTE_PID, 'Waste', 't,e,r,s')


def check_consistency(main_model):
    consistency = main_model.Consistency_Check()
    for consistencyCheck in consistency:
        if not consistencyCheck:
            raise RuntimeError("A consistency check failed: " + str(consistency))


def compute_area_flows(main_model, area_inflows, area_outflows, trade, scrap_trade,
                       scrap_share_in_production):
    params = main_model.ParameterDict

    def get_flow(from_id, to_id):
        return main_model.FlowDict['F_' + str(from_id) + '_' + str(to_id)]

    fin_use_flow = get_flow(FIN_PID, USE_PID)
    fin_use_flow.Values[:, 0, :, :] = area_inflows
    total_inflow_in_use_stock = np.sum(fin_use_flow.Values[:, 0, :, :], axis=2)

    if not cfg.include_trade:
        get_flow(PROD_PID, FIN_PID).Values[:, 0, :] = total_inflow_in_use_stock

    get_flow(USE_PID, RECYCLE_PID).Values[:, 0, :, :, :] = np.einsum('trgs,gw->trgws', area_outflows,
                                                                     params['End-Use_Distribution'].Values)

    recycling_inflow = np.sum(get_flow(USE_PID, RECYCLE_PID).Values[:, 0, :, :, :], axis=2)
    get_flow(RECYCLE_PID, SCRAP_PID).Values[:, 0, :, :] = np.einsum('trws,w->trws', recycling_inflow, params[
        'Recycling-Waste_Distribution'].Values)
    get_flow(RECYCLE_PID, WASTE_PID).Values[:, 0, :, :] = np.einsum('trws,w->trws', recycling_inflow, 1 - params[
        'Recycling-Waste_Distribution'].Values)

    total_production = total_inflow_in_use_stock
    if cfg.include_trade:
        imports = np.maximum(trade, 0).transpose()
        exports = -np.minimum(trade, 0).transpose()
        get_flow(ENV_PID, FIN_PID).Values[:, 0, :] = imports
        get_flow(FIN_PID, ENV_PID).Values[:, 0, :] = exports
        total_production += - imports + exports
        # total_production = np.maximum(0, total_production) TODO: irgendwas ist hier falsch, es sollte keine
        # TODO Diskrepanzen beim Trade geben können... außerdem müsste eigentlich der trade factor dann 100% sein...
        get_flow(PROD_PID, FIN_PID).Values[:, 0, :] = total_production

    max_scrap_in_production = get_flow(PROD_PID, FIN_PID).Values[:, 0, :] * scrap_share_in_production
    available_scrap = np.sum(get_flow(RECYCLE_PID, SCRAP_PID).Values[:, 0, :, :], axis=2)

    if cfg.include_trade:
        scrap_imports = np.maximum(scrap_trade, 0).transpose()
        scrap_exports = -np.minimum(scrap_trade, 0).transpose()
        get_flow(ENV_PID, SCRAP_PID).Values[:, 0, :] = scrap_imports
        get_flow(SCRAP_PID, ENV_PID).Values[:, 0, :] = scrap_exports
        available_scrap += scrap_imports - scrap_exports

    # TODO: Implement scrap stock?

    recyclable = np.minimum(available_scrap, max_scrap_in_production)

    get_flow(SCRAP_PID, PROD_PID).Values[:, 0, :] = recyclable
    get_flow(ENV_PID, PROD_PID).Values[:, 0, :] = total_production - recyclable

    return main_model


def compute_area_stocks(main_model, stocks, inflows, outflows):
    def get_flow(from_id, to_id):
        return main_model.FlowDict['F_' + str(from_id) + '_' + str(to_id)]

    def get_stock(p_id):
        return main_model.StockDict['S_' + str(p_id)]

    def get_stock_change(p_id):
        return main_model.StockDict['dS_' + str(p_id)]

    def calculate_stock_values_from_stock_change(p_id):
        stock_values = main_model.StockDict['dS_' + str(p_id)].Values[:, 0, :].cumsum(axis=0)
        main_model.StockDict['S_' + str(p_id)].Values[:, 0, :] = stock_values

    in_use_stock = get_stock(USE_PID)
    in_use_stock_change = get_stock_change(USE_PID)
    in_use_stock.Values[:, 0, :, :] = stocks
    in_use_stock_change.Values[:, 0, :, :] = inflows - outflows

    inflow_waste = np.sum(get_flow(RECYCLE_PID, WASTE_PID).Values[:, 0, :, :], axis=2)
    get_stock_change(WASTE_PID).Values[:, 0, :] = inflow_waste
    calculate_stock_values_from_stock_change(WASTE_PID)

    inflow_usable_scrap = np.sum(get_flow(RECYCLE_PID, SCRAP_PID).Values[:, 0, :, :], axis=2)
    recyclable = get_flow(SCRAP_PID, PROD_PID).Values[:, 0, :]
    scrap_stock_change = inflow_usable_scrap - recyclable
    if cfg.include_trade:
        scrap_imports = get_flow(ENV_PID, SCRAP_PID).Values[:, 0, :]
        scrap_exports = get_flow(SCRAP_PID, ENV_PID).Values[:, 0, :]
        scrap_stock_change += scrap_imports - scrap_exports
    get_stock_change(SCRAP_PID).Values[:, 0, :] = scrap_stock_change
    calculate_stock_values_from_stock_change(SCRAP_PID)

    return main_model


def mass_balance_plausible(main_model):
    """
    Checks if a given mass balance is plausible.
    :return: True if the mass balance for all processes is below 1kg (0.001 t) of steel, False otherwise. TODO checkUNIT
    """

    balance = main_model.MassBalance()
    for val in np.abs(balance).sum(axis=0).sum(axis=1):
        if val > 10:
            raise RuntimeError(
                "Error, Mass Balance summary below\n" + str(np.abs(balance).sum(axis=0).sum(axis=1)))
    print(f"Success - Model loaded and checked. \nBalance: {str(list(np.abs(balance).sum(axis=0).sum(axis=1)))}. \n\n")
    return True


def main():
    """
    Recalculates the DMFA dict based on the dynamic stock models and trade_all_areas data.
    Checks the Mass Balance and raises a runtime error if the mass balance is too big.
    Prints success statements otherwise
    :return: None
    """
    load_simson_model(country_specific=False, recalculate=True)


if __name__ == "__main__":
    # overwrite config with values given in a config file,
    # if the path to this file is passed as the last argument of the function call.
    if sys.argv[-1].endswith('.yml'):
        cfg.customize(sys.argv[-1])
    main()
