import numpy as np
import pandas as pd
import os
import sys
import pickle
import csv
from ODYM.odym.modules import ODYM_Classes as msc
from src.tools.config import cfg
from src.model.model_tools import get_dsm_data, get_stock_data_country_specific_areas, calc_change_timeline
from src.model.load_dsms import load_dsms
from src.model.calc_trade import get_trade, get_scrap_trade, _recalculate_scrap_trade_based_on_scrap_availability


#  constants

ENV_PID = 0
BOF_PID = 1
EAF_PID = 2
FORM_PID = 3
FABR_PID = 4
USE_PID = 5
SCRAP_PID = 6
RECYCLE_PID = 7
WASTE_PID = 8


def load_simson_model(country_specific=False, recalculate=cfg.recalculate_data) -> msc.MFAsystem:
    file_name_end = 'countries' if country_specific else f'{cfg.region_data_source}_regions'
    file_name = f'main_model_{file_name_end}.p'
    file_path = os.path.join(cfg.data_path, 'models', file_name)
    do_load_existing = os.path.exists(file_path) and not recalculate
    if do_load_existing:
        model = pickle.load(open(file_path, "rb"))
    else:
        model = create_base_model(country_specific, recalculate)
        pickle.dump(model, open(file_path, "wb"))
    return model


def create_base_model(country_specific, recalculate):
    dsms = load_dsms(country_specific, recalculate)
    model, balance_message = create_model(country_specific, dsms)
    print(balance_message)
    return model


def create_model(country_specific, dsms, scrap_share_in_production=None):
    n_regions = len(dsms)
    n_scenarions = len(dsms[0][0])
    max_scrap_share_in_production = np.ones([cfg.n_years, n_regions, n_scenarions]) * cfg.max_scrap_share_production_base_model
    if scrap_share_in_production is not None:
        max_scrap_share_in_production[cfg.econ_start_index:, :] = scrap_share_in_production
    # load data
    areas = get_stock_data_country_specific_areas(country_specific)
    main_model = set_up_model(areas)
    stocks, inflows, outflows = get_dsm_data(dsms)
    # Load model
    initiate_model(main_model)

    # compute stocks and flows
    compute_flows(main_model, country_specific, inflows, outflows,
                  max_scrap_share_in_production)
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
    add_process('BF/BOF Production', BOF_PID)
    add_process('EAF Production', EAF_PID)
    add_process('Forming', FORM_PID)
    add_process('Fabrication', FABR_PID)
    add_process('Using', USE_PID)
    add_process('End of Life', SCRAP_PID)
    add_process('Recycling', RECYCLE_PID)
    add_process('Waste', WASTE_PID)


def initiate_parameters(main_model):
    parameter_dict = {}

    wittig_path = os.path.join(cfg.data_path, 'original', 'Wittig', 'Wittig_matrix.csv')
    with open(wittig_path) as csv_file:
        wittig_reader = csv.reader(csv_file, delimiter=',')
        wittig_list = list(wittig_reader)
        use_recycling_params = [[float(num) for num in line[1:-1]] for line in wittig_list[1:]]
        recycling_usable_params = [float(line[-1]) for line in wittig_list[1:]]

    cullen_path = os.path.join(cfg.data_path, 'original', 'cullen', 'cullen_fabrication_yield_matrix.csv')
    with open(cullen_path) as csv_file:
        cullen_reader = csv.reader(csv_file, delimiter=',')
        cullen_list = list(cullen_reader)
        fabrication_yield = [float(line[1]) for line in cullen_list[1:]]

    parameter_dict['Fabrication_Yield'] = msc.Parameter(Name='Fabrication_Yield', ID=0,
                                                        P_Res=FABR_PID, MetaData=None, Indices='g',
                                                        Values=np.array(fabrication_yield), Unit='1')

    parameter_dict['Use-EOL_Distribution'] = msc.Parameter(Name='End-of-Life_Distribution', ID=1, P_Res=USE_PID,
                                                           MetaData=None, Indices='gw',
                                                           Values=np.array(use_recycling_params).transpose(), Unit='1')

    parameter_dict['EOL-Recycle_Distribution'] = msc.Parameter(Name='EOL-Recycle_Distribution', ID=2,
                                                               P_Res=SCRAP_PID,
                                                               MetaData=None, Indices='w',
                                                               Values=np.array(recycling_usable_params), Unit='1')

    main_model.ParameterDict = parameter_dict


def initiate_flows(main_model):
    def init_flow(name, from_id, to_id, indices):
        flow = msc.Flow(Name=name, P_Start=from_id, P_End=to_id, Indices=indices, Values=None)
        main_model.FlowDict['F_' + str(from_id) + '_' + str(to_id)] = flow

    init_flow('Iron Ore Production - BF/BOF Production', ENV_PID, BOF_PID, 't,e,r,s')
    init_flow('Recycling - BF/BOF Production', RECYCLE_PID, BOF_PID, 't,e,r,s')
    init_flow('BF/BOF Production - Forming', BOF_PID, FORM_PID, 't,e,r,s')
    init_flow('Recycling - EAF Production', RECYCLE_PID, EAF_PID, 't,e,r,s')
    init_flow('EAF Production - Forming', EAF_PID, FORM_PID, 't,e,r,s')

    init_flow('Forming - Fabrication', FORM_PID, FABR_PID, 't,e,r,s')
    init_flow('Forming - Scrap', FORM_PID, SCRAP_PID, 't,e,r,w,s')
    init_flow('Fabrication - Using', FABR_PID, USE_PID, 't,e,r,g,s')
    init_flow('Fabrication - Scrap', FABR_PID, SCRAP_PID, 't,e,r,w,s')

    init_flow('Using - Reuse', USE_PID, USE_PID, 't,e,r,g,s')
    init_flow('Using - Scrap', USE_PID, SCRAP_PID, 't,e,r,g,w,s')
    init_flow('Using - Environment', USE_PID, ENV_PID, 't,e,r,g,w,s')
    init_flow('Scrap - Recyling', SCRAP_PID, RECYCLE_PID, 't,e,r,s')
    init_flow('Scrap - Scrap Waste', SCRAP_PID, WASTE_PID, 't,e,r,s')

    init_flow('Imports', ENV_PID, FABR_PID, 't,e,r,s')
    init_flow('Exports', FABR_PID, ENV_PID, 't,e,r,s')
    init_flow('Scrap_Imports', ENV_PID, SCRAP_PID, 't,e,r,w,s')
    init_flow('Scrap_Exports', SCRAP_PID, ENV_PID, 't,e,r,w,s')


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


def compute_flows(model, country_specific,
                  inflows, outflows, max_scrap_share_in_production):

    use_eol_distribution, eol_recycle_distribution, fabrication_yield = _get_params(model)

    reuse = None
    if cfg.do_change_reuse:
        # one is substracted as one was added to multiply scenario and category reuse changes
        reuse_factor_timeline = calc_change_timeline(cfg.reuse_factor, cfg.reuse_change_base_year) - 1
        reuse = np.einsum('trgs,tgs->trgs', outflows, reuse_factor_timeline)
        inflows -= reuse
        outflows -= reuse

    inverse_fabrication_yield = 1 / fabrication_yield
    fabrication_by_category = np.einsum('trgs,g->trgs', inflows, inverse_fabrication_yield)
    fabrication = np.sum(fabrication_by_category, axis=2)
    demand = np.sum(inflows, axis=2)
    fabrication_scrap = fabrication - demand

    imports, exports = get_trade(country_specific=country_specific, fabrication_demand=fabrication.transpose())

    forming_fabrication = fabrication - imports + exports
    production = forming_fabrication * (1 / cfg.forming_yield)
    forming_scrap = production - forming_fabrication

    outflows_by_waste = np.einsum('trgs,gw->trgws', outflows, use_eol_distribution)
    use_eol = np.zeros_like(outflows_by_waste)
    use_env = np.zeros_like(outflows_by_waste)

    dis_idx = cfg.recycling_categories.index('Dis')
    use_eol[:, :, :, :dis_idx, :] = outflows_by_waste[:, :, :, :dis_idx, :]
    use_env[:, :, :, dis_idx:, :] = outflows_by_waste[:, :, :, dis_idx:, :]
    eol_scrap = np.sum(use_eol, axis=2)

    available_scrap = eol_scrap.copy()
    available_scrap[:, :, cfg.recycling_categories.index('Form'), :] = forming_scrap
    available_scrap[:, :, cfg.recycling_categories.index('Fabr'), :] = fabrication_scrap

    scrap_imports, scrap_exports = get_scrap_trade(country_specific=country_specific, production=production.transpose(),
                                                   available_scrap_by_category=available_scrap)
    # TODO: Delete, this omits scrap trade
    #scrap_imports[:] = 0
    #scrap_exports[:] = 0
    total_scrap = available_scrap + scrap_imports - scrap_exports

    max_scrap_in_production = production * max_scrap_share_in_production
    recyclable_scrap = np.einsum('trwe,w->trwe', total_scrap, eol_recycle_distribution)
    recyclable_scrap = np.sum(recyclable_scrap, axis=2)
    scrap_in_production = np.minimum(recyclable_scrap, max_scrap_in_production)

    scrap_share = np.divide(scrap_in_production, production,
                            out=np.zeros_like(scrap_in_production), where=production!=0)
    eaf_share_production = _calc_eaf_share_production(scrap_share)
    eaf_production = production * eaf_share_production
    bof_production = production - eaf_production
    max_scrap_in_bof = cfg.scrap_in_BOF_rate * bof_production
    scrap_in_bof = np.minimum(max_scrap_in_bof, scrap_in_production)
    iron_production = bof_production - scrap_in_bof

    scrap_in_production = scrap_in_bof + eaf_production
    waste = np.sum(total_scrap, axis=2) - scrap_in_production

    edit_flows(model, iron_production, scrap_in_bof, bof_production, eaf_production, forming_fabrication, forming_scrap,
               imports, exports, inflows, reuse, fabrication_scrap, use_eol, use_env, scrap_imports, scrap_exports,
               scrap_in_production, waste)

    return model


def edit_flows(model, iron_production, scrap_in_bof, bof_production, eaf_production, forming_fabrication, forming_scrap,
               imports, exports, inflows, reuse, fabrication_scrap, use_eol, use_env, scrap_imports, scrap_exports,
               scrap_in_production, waste):
    def get_flow(from_id, to_id):
        return model.FlowDict['F_' + str(from_id) + '_' + str(to_id)].Values

    get_flow(ENV_PID, BOF_PID)[:, 0] = iron_production
    get_flow(RECYCLE_PID, BOF_PID)[:, 0] = scrap_in_bof
    get_flow(BOF_PID, FORM_PID)[:, 0] = bof_production
    get_flow(RECYCLE_PID, EAF_PID)[:, 0] = eaf_production
    get_flow(EAF_PID, FORM_PID)[:, 0] = eaf_production
    get_flow(FORM_PID, FABR_PID)[:, 0] = forming_fabrication
    get_flow(FORM_PID, SCRAP_PID)[:, 0, :, cfg.recycling_categories.index('Form')] = forming_scrap
    get_flow(ENV_PID, FABR_PID)[:, 0] = imports
    get_flow(FABR_PID, ENV_PID)[:, 0] = exports
    get_flow(FABR_PID, USE_PID)[:, 0] = inflows
    get_flow(FABR_PID, SCRAP_PID)[:, 0, :, cfg.recycling_categories.index('Fabr')] = fabrication_scrap
    if reuse is not None:
        get_flow(USE_PID, USE_PID)[:,0] = reuse
    get_flow(USE_PID, SCRAP_PID)[:, 0] = use_eol
    get_flow(USE_PID, ENV_PID)[:, 0] = use_env
    get_flow(ENV_PID, SCRAP_PID)[:, 0] = scrap_imports
    get_flow(SCRAP_PID, ENV_PID)[:, 0] = scrap_exports
    get_flow(SCRAP_PID, RECYCLE_PID)[:, 0] = scrap_in_production
    get_flow(SCRAP_PID, WASTE_PID)[:, 0] = waste


def _get_params(model):
    params = model.ParameterDict
    use_eol_distribution = params['Use-EOL_Distribution'].Values
    eol_recycle_distribution = params['EOL-Recycle_Distribution'].Values
    fabrication_yield = params['Fabrication_Yield'].Values

    return use_eol_distribution, eol_recycle_distribution, fabrication_yield


def get_flow(model, from_id, to_id):
    return model.FlowDict['F_' + str(from_id) + '_' + str(to_id)].Values


def _calc_eaf_share_production(scrap_share):
    eaf_share_production = (scrap_share - cfg.scrap_in_BOF_rate) / (1 - cfg.scrap_in_BOF_rate)
    eaf_share_production[eaf_share_production<=0] = 0
    return eaf_share_production


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

    inflow_waste = get_flow(SCRAP_PID, WASTE_PID)
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
    return f"Success - Model loaded and checked. \nBalance: {str(list(np.abs(balance).sum(axis=0).sum(axis=1)))}.\n"


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
