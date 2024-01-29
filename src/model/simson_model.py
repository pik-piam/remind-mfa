import numpy as np
import pandas as pd
from ODYM.odym.modules.ODYM_Classes import MFAsystem, Classification, Process, Parameter, Flow, Stock
from src.tools.config import cfg
from src.tools.tools import get_dsm_data
from src.read_data.load_data import load_data, setup
from src.model.load_dsms import load_dsms

#  model definition
processes = ['System Environment',
             'Primary Production',
             'Fabrication',
             'Mechanical Recycling',
             'Use Phase',
             'End of Life',
             'Incineration']

pid = {p: id for id, p in enumerate(processes)}

stocks = [
    Stock(Name='In-Use Stock', P_Res=pid['Use Phase'], Type=0, Indices='t,e,r,g', Values=None)
]
add_change = {'In-Use Stock': True}

stock_dict = {stock.Name: stock for stock in stocks}
stock_change_dict = {
        name + ' Change': Stock(Name=name + ' Change', P_Res=stock.P_Res, Type=1, Indices=stock.Indices, Values=None)
    for name, stock in stock_dict.items() if add_change[name]}
stock_dict.update(stock_change_dict)

flows = [
    Flow(Name='primary_production_input',          P_Start=pid['System Environment'],   P_End=pid['Primary Production'],   Indices='t,e,r',   Values=None),
    Flow(Name='primary_production_output',         P_Start=pid['Primary Production'],   P_End=pid['Fabrication'],          Indices='t,e,r',   Values=None),
    Flow(Name='demand',                            P_Start=pid['Fabrication'],          P_End=pid['Use Phase'],            Indices='t,e,r',   Values=None),
    Flow(Name='outflow_by_element',                P_Start=pid['Use Phase'],            P_End=pid['End of Life'],          Indices='t,e,r,g', Values=None),
    Flow(Name='waste_incineration',                P_Start=pid['End of Life'],          P_End=pid['Incineration'],         Indices='t,e,r',   Values=None),
    Flow(Name='mechanical_recycling_input',        P_Start=pid['End of Life'],          P_End=pid['Mechanical Recycling'], Indices='t,e,r',   Values=None),
    Flow(Name='mechanical_recycling_output',       P_Start=pid['Mechanical Recycling'], P_End=pid['Fabrication'],          Indices='t,e,r',   Values=None),
    Flow(Name='mechanical_recycling_incineration', P_Start=pid['Mechanical Recycling'], P_End=pid['Incineration'],         Indices='t,e,r',   Values=None),
    Flow(Name='incineration_emissions',            P_Start=pid['Incineration'],         P_End=pid['System Environment'],   Indices='t,e,r',   Values=None)
]
flow_dict = {flow.Name: flow for flow in flows}
# incineration = waste_incineration + mechanical_recycling_incineration

# @load_or_recalculate #TODO
def load_simson_mfa():
    dsms = load_dsms()
    model = create_model(dsms)
    return model


def create_model(dsms):

    main_model = set_up_model()

    stock_values = get_dsm_data(dsms, lambda dsm: dsm.s)
    inflows = get_dsm_data(dsms, lambda dsm: dsm.i)
    outflows = get_dsm_data(dsms, lambda dsm: dsm.o)

    initiate_model(main_model)

    compute_flows(main_model, inflows, outflows)

    compute_stocks(main_model, stock_values, inflows, outflows)

    mass_balance_plausible(main_model)

    return main_model


def initiate_model(main_model: MFAsystem):
    # processes
    initiate_processes(main_model)
    # parameters
    initiate_parameters(main_model)
    # flows
    main_model.FlowDict = flow_dict
    main_model.Initialize_FlowValues()
    # stocks
    main_model.StockDict = stock_dict
    main_model.Initialize_StockValues()
    check_consistency(main_model)


def set_up_model():

    dimensions = {'Time': 'Time',
                  'Element': 'Element',
                  'Region': 'Region',
                  'Good': 'Material'}
    items = {'Time': cfg.years,
             'Element': cfg.elements,
             'Region': cfg.data.region_list,
             'Good': cfg.in_use_categories}

    def model_classification(id, aspect):
        return Classification(Name=aspect,
                              Dimension=dimensions[aspect],
                              ID=id,
                              Items=items[aspect])
    index_table = pd.DataFrame({'Aspect': cfg.aspects,
                                'Description': [f"Model aspect '{a}'" for a in cfg.aspects],
                                'Dimension': [dimensions[a] for a in cfg.aspects],
                                'Classification': [model_classification(i + 1, a) for i, a in enumerate(cfg.aspects)],
                                'IndexLetter': [cfg.index_letters[a] for a in cfg.aspects]})
    index_table.set_index('Aspect', inplace=True)

    main_model = MFAsystem(Name='World Plastics Economy',
                           Geogr_Scope='World',
                           Unit='t',
                           ProcessList=[],
                           FlowDict={},
                           StockDict={},
                           ParameterDict={},
                           Time_Start=cfg.start_year,
                           Time_End=cfg.end_year,
                           IndexTable=index_table,
                           Elements=index_table.loc['Element'].Classification.Items)

    return main_model


def initiate_processes(main_model: MFAsystem):
    main_model.ProcessList = [Process(Name=name, ID=id) for name, id in pid.items()]
    return


def initiate_parameters(main_model: MFAsystem):

    shares = load_data('good_and_element_shares')
    share_of_goods = np.sum(shares, axis = 0, keepdims=True)
    element_shares_in_goods = shares / share_of_goods

    recycling_rates = load_data('mechanical_recycling_rates')

    recycling_yields = load_data('mechanical_recycling_yields')

    main_model.ParameterDict = {
        'Element_Shares_in_Goods':     Parameter(Name='Element_Shares_in_Goods',
                                                ID=0,
                                                P_Res=pid['Fabrication'],
                                                MetaData=None,
                                                Indices='e,g',
                                                Values=element_shares_in_goods,
                                                Unit='1'),
        'Mechanical_Recycling_Rate':  Parameter(Name='Mechanical_Recycling_Rate',
                                                ID=1,
                                                P_Res=pid['Use Phase'],
                                                MetaData=None,
                                                Indices='e,g',
                                                Values=recycling_rates,
                                                Unit='1'),
        'Mechanical_Recycling_Yield': Parameter(Name='Mechanical_Recycling_Rate',
                                                ID=2,
                                                P_Res=pid['Mechanical Recycling'],
                                                MetaData=None,
                                                Indices='e',
                                                Values=recycling_yields,
                                                Unit='1')
    }
    return


def check_consistency(main_model: MFAsystem):
    """
    Uses ODYM consistency checks to see if model dimensions and structure are well
    defined. Raises RuntimeError if not.

    :param main_model: The MFA System
    :return:
    """
    consistency = main_model.Consistency_Check()
    for consistencyCheck in consistency:
        if not consistencyCheck:
            raise RuntimeError("A consistency check failed: " + str(consistency))


def compute_flows(model: MFAsystem, use_inflows: np.ndarray, use_outflows: np.ndarray):

    element_shares_in_goods, mechanical_recycling_rate, mechanical_recycling_yield = _get_params(model)

    demand = np.einsum('trg,eg->ter', use_inflows, element_shares_in_goods)

    outflow_by_element = np.einsum('trg,eg->terg', use_outflows, element_shares_in_goods)

    mechanical_recycling_input = np.einsum('terg,eg->ter', outflow_by_element, mechanical_recycling_rate)

    waste_incineration = np.sum(outflow_by_element, axis=3) - mechanical_recycling_input

    mechanical_recycling_output = np.einsum('ter,e->ter', mechanical_recycling_input, mechanical_recycling_yield)

    mechanical_recycling_incineration = mechanical_recycling_input - mechanical_recycling_output

    primary_production_output = demand - mechanical_recycling_output

    primary_production_input = primary_production_output

    incineration = waste_incineration + mechanical_recycling_incineration

    edit_flows(model,
               {'demand': demand,
                'outflow_by_element': outflow_by_element,
                'mechanical_recycling_input': mechanical_recycling_input,
                'waste_incineration': waste_incineration,
                'mechanical_recycling_output': mechanical_recycling_output,
                'mechanical_recycling_incineration': mechanical_recycling_incineration,
                'primary_production_output': primary_production_output,
                'primary_production_input': primary_production_input,
                'incineration_emissions': incineration})

    return model


def edit_flows(model: MFAsystem, flow_dict):
    for flow_name, flow_value in flow_dict.items():
        model.FlowDict[flow_name].Values[...] = flow_value


def _get_params(model: MFAsystem):
    params = model.ParameterDict
    element_shares_in_goods = params['Element_Shares_in_Goods'].Values
    mechanical_recycling_rate = params['Mechanical_Recycling_Rate'].Values
    mechanical_recycling_yield = params['Mechanical_Recycling_Yield'].Values
    return element_shares_in_goods, mechanical_recycling_rate, mechanical_recycling_yield


def compute_stocks(model: MFAsystem, stock_values, inflows, outflows):
    element_shares_in_goods, _, _ = _get_params(model)
    stocks_by_element = np.einsum('trg,eg->terg', stock_values, element_shares_in_goods)
    model.StockDict['In-Use Stock'].Values = stocks_by_element
    change_by_element = np.einsum('trg,eg->terg', inflows - outflows, element_shares_in_goods)
    model.StockDict['In-Use Stock Change'].Values = change_by_element

    return model


def mass_balance_plausible(main_model: MFAsystem):
    """
    Checks if a given mass balance is plausible.
    :return: True if the mass balance for all processes is below 1t of steel, False otherwise.
    """

    print("Checking mass balance...")
    # returns array with dim [t, process, e]
    balance = main_model.MassBalance()
    error_sum_by_process = np.abs(balance).sum(axis=(0,2))
    id_failed = error_sum_by_process > 1.
    names_failed = [n for n, id in pid.items() if id_failed[id]]
    if names_failed:
            raise RuntimeError(f"Error, Mass Balance fails for processes {', '.join(names_failed)}")
    else:
        print("Success - Mass balance consistent!")
    return


if __name__ == "__main__":
    setup()
    load_simson_mfa()
