import numpy as np
import pandas as pd
from ODYM.odym.modules.ODYM_Classes import Classification, Process, Stock, Flow, Parameter
from src.odym_extension.SimsonMFASystem import SimsonMFASystem
from src.tools.config import cfg
from src.tools.tools import get_dsm_data
from src.read_data.load_data import load_data
from src.model.load_dsms import load_dsms
from src.visualisation.visualize import visualize_mfa_sankey
from src.export.export import export_to_dict


def load_simson_mfa():
    dsms = load_dsms()
    model = create_model(dsms)
    return model


def create_model(dsms):

    main_model = set_up_model()

    use_stock_values = get_dsm_data(dsms, lambda dsm: dsm.s)
    use_stock_inflows = get_dsm_data(dsms, lambda dsm: dsm.i)
    use_stock_outflows = get_dsm_data(dsms, lambda dsm: dsm.o)

    initiate_model(main_model)

    cfg.model_def.compute_flows(main_model, use_stock_inflows, use_stock_outflows)

    cfg.model_def.compute_stocks(main_model, use_stock_values)

    mass_balance_plausible(main_model)

    return main_model


def initiate_model(model: SimsonMFASystem):
    initiate_processes(model)
    initiate_parameters(model)
    initiate_flows(model)
    initiate_stocks(model)
    check_consistency(model)


def set_up_model():

    def model_classification(id, aspect):
        return Classification(Name=aspect,
                              Dimension=cfg.odym_dimensions[aspect],
                              ID=id,
                              Items=cfg.items[aspect])

    index_table = pd.DataFrame({'Aspect': cfg.aspects,
                                'Description': [f"Model aspect '{a}'" for a in cfg.aspects],
                                'Dimension': [cfg.odym_dimensions[a] for a in cfg.aspects],
                                'Classification': [model_classification(i + 1, a) for i, a in enumerate(cfg.aspects)],
                                'IndexLetter': [cfg.index_letters[a] for a in cfg.aspects]})
    index_table.set_index('Aspect', inplace=True)

    main_model = SimsonMFASystem(Name='World Plastics Economy',
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



def check_consistency(main_model: SimsonMFASystem):
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


def mass_balance_plausible(main_model: SimsonMFASystem):
    """
    Checks if a given mass balance is plausible.
    :return: True if the mass balance for all processes is below 1t of steel, False otherwise.
    """

    print("Checking mass balance...")
    # returns array with dim [t, process, e]
    balance = main_model.MassBalance()
    error_sum_by_process = np.abs(balance).sum(axis=(0,2))
    id_failed = error_sum_by_process > 1.
    names_failed = [n for id, n in enumerate(cfg.model_def.processes) if id_failed[id]]
    if names_failed:
            raise RuntimeError(f"Error, Mass Balance fails for processes {', '.join(names_failed)}")
    else:
        print("Success - Mass balance consistent!")
    return


def initiate_processes(model):
    model.ProcessList = [Process(Name=name,
                                 ID=id
                                 ) for id, name in enumerate(cfg.model_def.processes)]


def initiate_flows(model):
    flows = [Flow(Name=def_dict["start"] + "_2_" + def_dict["end"],
                  P_Start=cfg.model_def.processes.index(def_dict["start"]),
                  P_End=cfg.model_def.processes.index(def_dict["end"]),
                  Indices=def_dict["indices"],
                  Values = None
                  ) for def_dict in cfg.model_def.flows]
    model.FlowDict = {f.Name: f for f in flows}
    model.Initialize_FlowValues()


def initiate_parameters(model):
    parameters = [Parameter(Name=def_dict["name"],
                            ID = i,
                            P_Res = cfg.model_def.processes.index(def_dict["process"]),
                            MetaData = None,
                            Indices=def_dict["indices"],
                            Values = load_data(def_dict["name"]),
                            Unit = '1'
                            ) for i, def_dict in enumerate(cfg.model_def.prms)]
    model.ParameterDict = {p.Name: p for p in parameters}
    # correct values
    msg = model.ParameterDict['material_shares_in_goods']
    msg.Values[...] = msg.Values / np.sum(msg.Values, axis=0, keepdims=True)


def initiate_stocks(model):
    stocks = [Stock(Name=def_dict["name"],
                    P_Res=def_dict["process_index"],
                    Type=def_dict["stock_type"],
                    Indices=def_dict["indices"],
                    Values=None
                    ) for def_dict in cfg.model_def.stocks]
    model.StockDict = {s.Name: s for s in stocks}
    model.Initialize_StockValues()


if __name__ == "__main__":
    mfa = load_simson_mfa()
    if cfg.do_visualize['sankey']:
        visualize_mfa_sankey(mfa)
    export_to_dict(mfa, 'data/output/mfa.pickle')
