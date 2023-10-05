import numpy as np
import pandas as pd
import os
import sys
import pickle
import csv
from ODYM.odym.modules import ODYM_Classes as msc
from src.tools.config import cfg
from src.model.model_tools import get_dsm_data, get_stock_data_country_specific_areas
from src.model.load_dsms import load_dsms
from src.model.calc_trade import get_all_trade

#  constants

#  Indices
ENV_PID = 0
PROD_PID = 1
FIN_PID = 2
RECYCLE_PID = 3
USE_PID = 4
EOL_PID = 5
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
    model, balance_message =  create_model(country_specific, dsms)
    print(balance_message)
    return model


def create_model(country_specific, dsms, scrap_share_in_production=None):
    n_regions = len(dsms)
    n_scenarions = len(dsms[0][0])
    max_scrap_share_in_production = np.ones([cfg.n_years, n_regions, n_scenarions]) * cfg.max_scrap_share_production
    calc_recovery_rate_from_scrap_share = False
    if scrap_share_in_production is not None:
        max_scrap_share_in_production[cfg.econ_start_index:, :] = scrap_share_in_production
        calc_recovery_rate_from_scrap_share = True
    # load data
    areas = get_stock_data_country_specific_areas(country_specific)
    trade_all_areas, scrap_trade_all_areas = get_all_trade(country_specific=country_specific, dsms=dsms)
    main_model = set_up_model(areas)
    stocks, inflows, outflows = get_dsm_data(dsms)

    # Load model
    initiate_model(main_model)

    # compute stocks and flows
    compute_flows(main_model, inflows, outflows,
                  trade_all_areas, scrap_trade_all_areas,
                  max_scrap_share_in_production, calc_recovery_rate_from_scrap_share)
    compute_stocks(main_model, stocks, inflows, outflows)

    # check model
    balance_message = mass_balance_plausible(main_model)

    return main_model, balance_message


def initiate_model(main_model):
    initiate_processes(main_model)
    initiate_parameters(main_model)
    initiate_flows(main_model)
    initiate_stocks(main_model)
    main_model.Initialize_FlowValues()
    main_model.Initialize_StockValues()
    check_consistency(main_model)


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
    add_process('Recycling', RECYCLE_PID)
    add_process('NewSteel', FIN_PID)
    add_process('Using', USE_PID)
    add_process('End of Life', EOL_PID)
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

    parameter_dict['Use-EOL_Distribution'] = msc.Parameter(Name='End-Use_Distribution', ID=0, P_Res=USE_PID,
                                                           MetaData=None, Indices='gw',
                                                           Values=np.array(use_recycling_params), Unit='1')

    parameter_dict['EOL-Recycle_Distribution'] = msc.Parameter(Name='Recycling-Waste_Distribution', ID=0,
                                                               P_Res=EOL_PID,
                                                               MetaData=None, Indices='w',
                                                               Values=np.array(recycling_usable_params), Unit='1')

    main_model.ParameterDict = parameter_dict


def initiate_flows(main_model):
    def add_flow(name, from_id, to_id, indices):
        flow = msc.Flow(Name=name, P_Start=from_id, P_End=to_id, Indices=indices, Values=None)
        main_model.FlowDict['F_' + str(from_id) + '_' + str(to_id)] = flow

    add_flow('Primary Production - Production', ENV_PID, PROD_PID, 't,e,r,s')
    add_flow('Recycling - Production', RECYCLE_PID, PROD_PID, 't,e,r,s')
    add_flow('Production - Final Steel', PROD_PID, FIN_PID, 't,e,r,s')

    add_flow('Final Steel - Using', FIN_PID, USE_PID, 't,e,r,g,s')
    add_flow('Using - End of LIfe', USE_PID, EOL_PID, 't,e,r,g,w,s')
    add_flow('Using - Environment', USE_PID, ENV_PID, 't,e,r,g,w,s')
    add_flow('End of Life - Recyling', EOL_PID, RECYCLE_PID, 't,e,r,s')
    add_flow('End of Life - Scrap Waste', EOL_PID, WASTE_PID, 't,e,r,s')

    if cfg.include_trade:
        add_flow('Imports', ENV_PID, FIN_PID, 't,e,r,s')
        add_flow('Exports', FIN_PID, ENV_PID, 't,e,r,s')
        add_flow('Scrap_Imports', ENV_PID, EOL_PID, 't,e,r,w,s')
        add_flow('Scrap_Exports', EOL_PID, ENV_PID, 't,e,r,w,s')


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
    add_stock(WASTE_PID, 'Waste', 't,e,r,s')


def check_consistency(main_model):
    consistency = main_model.Consistency_Check()
    for consistencyCheck in consistency:
        if not consistencyCheck:
            raise RuntimeError("A consistency check failed: " + str(consistency))


def compute_flows(main_model, inflows, outflows, trade, scrap_trade,
                  scrap_share_in_production, calc_recovery_rate_from_scrap_share):
    def get_flow(from_id, to_id):
        return main_model.FlowDict['F_' + str(from_id) + '_' + str(to_id)].Values

    primary_flow = get_flow(ENV_PID, PROD_PID)
    secondary_flow = get_flow(RECYCLE_PID, PROD_PID)
    prod_fin_flow = get_flow(PROD_PID, FIN_PID)
    fin_use_flow = get_flow(FIN_PID, USE_PID)
    use_eol_flow = get_flow(USE_PID, EOL_PID)
    use_env_flow = get_flow(USE_PID, ENV_PID)
    eol_waste_flow = get_flow(EOL_PID, WASTE_PID)
    eol_recycle_flow = get_flow(EOL_PID, RECYCLE_PID)
    if cfg.include_trade:
        import_flow = get_flow(ENV_PID, FIN_PID)
        export_flow = get_flow(FIN_PID, ENV_PID)
        scrap_import_flow = get_flow(ENV_PID, EOL_PID)
        scrap_export_flow = get_flow(EOL_PID, ENV_PID)

    params = main_model.ParameterDict
    use_eol_distribution = params['Use-EOL_Distribution'].Values
    eol_recycle_distribution = params['EOL-Recycle_Distribution'].Values

    outflows_by_waste = np.einsum('trgs,gw->trgws', outflows, use_eol_distribution)

    production = np.sum(inflows, axis=2)
    if cfg.include_trade:
        import_flow[:, 0, :, :] = np.maximum(trade, 0).transpose()
        export_flow[:, 0, :, :] = -np.minimum(trade, 0).transpose()
        production += export_flow[:, 0, :, :] - import_flow[:, 0, :, :]

    prod_fin_flow[:, 0, :, :] = production
    fin_use_flow[:, 0, :, :, :] = inflows
    use_eol_flow[:, 0, :, :, :6, :] = outflows_by_waste[:, :, :, :6, :]  # Normal waste categories go to EOL
    use_env_flow[:, 0, :, :, 6:, :] = outflows_by_waste[:, :, :, 6:, :]  # Dis. and Not.Col go to environment
    eol_scrap = np.sum(use_eol_flow[:, 0, :, :, :, :], axis=2)

    if cfg.include_trade:
        scrap_imports, scrap_exports = _recalculate_scrap_trade_based_on_scrap_availability(scrap_trade, eol_scrap)
        scrap_import_flow[:, 0, :, :, :] = scrap_imports
        scrap_export_flow[:, 0, :, :, :] = scrap_exports
        eol_scrap += scrap_imports - scrap_exports

    max_scrap_in_production = prod_fin_flow[:, 0, :, :] * scrap_share_in_production
    if calc_recovery_rate_from_scrap_share:  # Econ model
        secondary_flow[:, 0, :, :] = max_scrap_in_production

    else:  # Base model
        recyclable_eol_scrap = np.swapaxes(eol_scrap, 2, 3) * eol_recycle_distribution
        recyclable_eol_scrap = np.sum(recyclable_eol_scrap, axis=3)
        secondary_flow[:, 0, :, :] = np.minimum(recyclable_eol_scrap, max_scrap_in_production)

    eol_recycle_flow[:] = secondary_flow[:]
    eol_waste_flow[:, 0, :, :] = np.sum(eol_scrap, axis=2) - eol_recycle_flow[:, 0, :, :]

    primary_flow[:] = prod_fin_flow - secondary_flow

    return main_model


def _recalculate_scrap_trade_based_on_scrap_availability(projected_scrap_trade, eol_scrap):
    available_scrap = np.sum(eol_scrap, axis=2)
    projected_scrap_trade = projected_scrap_trade.transpose()

    projected_exports = np.minimum(0, projected_scrap_trade)

    projected_exports = np.abs(projected_exports)
    factor = np.divide(available_scrap, projected_exports, out=np.ones(available_scrap.shape) * np.inf,
                       where=projected_exports != 0)
    factor2 = np.min(factor, axis=1)
    factor3 = np.expand_dims(factor2, axis=1)
    factor4 = factor3 * 0.999  # avoid slightly negative numbers
    new_trade = projected_scrap_trade * factor4

    total_scrap_imports = np.maximum(new_trade, 0)
    total_scrap_exports = np.minimum(new_trade, 0)

    available_scrap_expanded = np.expand_dims(available_scrap, axis=2)
    eol_by_scrap_category_percent = np.divide(eol_scrap, available_scrap_expanded, out=np.zeros_like(eol_scrap),
                                              where=available_scrap_expanded != 0)
    scrap_exports = eol_by_scrap_category_percent * np.expand_dims(total_scrap_exports, axis=2)

    scrap_exports_sum_areas = np.sum(scrap_exports, axis=1)
    scrap_exports_sum_categories = np.sum(scrap_exports_sum_areas, axis=1)
    scrap_exports_percent_by_category = scrap_exports_sum_areas / np.expand_dims(scrap_exports_sum_categories, axis=1)
    scrap_exports_percent_by_category = np.expand_dims(scrap_exports_percent_by_category, axis=1)
    total_scrap_imports = np.expand_dims(total_scrap_imports, axis=2)
    scrap_imports = total_scrap_imports * scrap_exports_percent_by_category

    return scrap_imports, scrap_exports


def compute_stocks(main_model, stocks, inflows, outflows):
    def get_flow(from_id, to_id):
        return main_model.FlowDict['F_' + str(from_id) + '_' + str(to_id)].Values

    def get_stock(p_id):
        return main_model.StockDict['S_' + str(p_id)].Values

    def get_stock_change(p_id):
        return main_model.StockDict['dS_' + str(p_id)].Values

    def calculate_stock_values_from_stock_change(p_id):
        stock_values = get_stock_change(p_id).cumsum(axis=0)
        get_stock(p_id)[:] = stock_values

    in_use_stock = get_stock(USE_PID)
    in_use_stock_change = get_stock_change(USE_PID)
    in_use_stock[:, 0, :, :] = stocks
    in_use_stock_change[:, 0, :, :] = inflows - outflows

    inflow_waste = get_flow(EOL_PID, WASTE_PID)
    get_stock_change(WASTE_PID)[:] = inflow_waste
    calculate_stock_values_from_stock_change(WASTE_PID)

    return main_model


def mass_balance_plausible(main_model):
    """
    Checks if a given mass balance is plausible.
    :return: True if the mass balance for all processes is below 1t of steel, False otherwise.
    """

    balance = main_model.MassBalance()
    for val in np.abs(balance).sum(axis=0).sum(axis=1):
        if val > 1:
            raise RuntimeError(
                "Error, Mass Balance summary below\n" + str(np.abs(balance).sum(axis=0).sum(axis=1)))
    return (f"Success - Model loaded and checked. \nBalance: {str(list(np.abs(balance).sum(axis=0).sum(axis=1)))}.\n")


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
