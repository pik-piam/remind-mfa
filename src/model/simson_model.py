import numpy as np
import pandas as pd
from ODYM.odym.modules.ODYM_Classes import Classification, Process, Stock
from src.odym_extension.SimsonValueClasses import DictVariableCreator, PrmDef, FlowDef
from src.odym_extension.SimsonMFASystem import SimsonMFASystem
from src.tools.config import cfg
from src.tools.tools import get_dsm_data
from src.read_data.load_data import setup
from src.model.load_dsms import load_dsms
from src.visualisation.visualize import visualize_mfa_sankey
from src.export.export import export_to_dict

#  model definition
processes = ['sysenv',
             'virginfoss',
             'virginbio',
             'virgindaccu',
             'virginccu',
             'virgin',
             'fabrication',
             'recl',
             'reclmech',
             'reclchem',
             'reclsolv',
             'use',
             'eol',
             'incineration',
             'landfill',
             'uncontrolled',
             'emission',
             'captured',
             'atmosphere']

stocks = [
    Stock(Name='in_use_stock',              P_Res=processes.index('use'),          Type=0, Indices='t,e,r,m,g', Values=None),
    Stock(Name='in_use_stock_inflow',       P_Res=processes.index('use'),          Type=1, Indices='t,e,r,m,g', Values=None),
    Stock(Name='in_use_stock_outflow',      P_Res=processes.index('use'),          Type=2, Indices='t,e,r,m,g', Values=None),
    Stock(Name='atmospheric_stock',         P_Res=processes.index('atmosphere'),   Type=0, Indices='t,e,r',     Values=None),
    Stock(Name='atmospheric_stock_inflow',  P_Res=processes.index('atmosphere'),   Type=1, Indices='t,e,r',     Values=None),
    Stock(Name='atmospheric_stock_outflow', P_Res=processes.index('atmosphere'),   Type=2, Indices='t,e,r',     Values=None),
    Stock(Name='landfill_stock',            P_Res=processes.index('landfill'),     Type=0, Indices='t,e,r,m',   Values=None),
    Stock(Name='landfill_stock_inflow',     P_Res=processes.index('landfill'),     Type=1, Indices='t,e,r,m',   Values=None),
    Stock(Name='uncontrolled_stock',        P_Res=processes.index('uncontrolled'), Type=0, Indices='t,e,r,m',   Values=None),
    Stock(Name='uncontrolled_stock_inflow', P_Res=processes.index('uncontrolled'), Type=1, Indices='t,e,r,m',   Values=None)
]

flow_defs = [
    FlowDef(start='sysenv',       end='virginfoss',   indices='t,e,r,m'),
    FlowDef(start='sysenv',       end='virginbio',    indices='t,e,r,m'),
    FlowDef(start='sysenv',       end='virgindaccu',  indices='t,e,r,m'),
    FlowDef(start='sysenv',       end='virginccu',    indices='t,e,r,m'),
    FlowDef(start='atmosphere',   end='virginbio',    indices='t,e,r'),
    FlowDef(start='atmosphere',   end='virgindaccu',  indices='t,e,r'),
    FlowDef(start='virginfoss',   end='virgin',       indices='t,e,r,m'),
    FlowDef(start='virginbio',    end='virgin',       indices='t,e,r,m'),
    FlowDef(start='virgindaccu',  end='virgin',       indices='t,e,r,m'),
    FlowDef(start='virginccu',    end='virgin',       indices='t,e,r,m'),
    FlowDef(start='virgin',       end='fabrication',  indices='t,e,r,m'),
    FlowDef(start='fabrication',  end='use',          indices='t,e,r,m,g'),
    FlowDef(start='use',          end='eol',          indices='t,e,r,m,g'),
    FlowDef(start='eol',          end='reclmech',     indices='t,e,r,m'),
    FlowDef(start='eol',          end='reclchem',     indices='t,e,r,m'),
    FlowDef(start='eol',          end='reclsolv',     indices='t,e,r,m'),
    FlowDef(start='eol',          end='uncontrolled', indices='t,e,r,m'),
    FlowDef(start='eol',          end='landfill',     indices='t,e,r,m'),
    FlowDef(start='eol',          end='incineration', indices='t,e,r,m'),
    FlowDef(start='reclmech',     end='recl',         indices='t,e,r,m'),
    FlowDef(start='reclchem',     end='recl',         indices='t,e,r,m'),
    FlowDef(start='reclsolv',     end='recl',         indices='t,e,r,m'),
    FlowDef(start='recl',         end='fabrication',  indices='t,e,r,m'),
    FlowDef(start='reclmech',     end='uncontrolled', indices='t,e,r,m'),
    FlowDef(start='reclmech',     end='incineration', indices='t,e,r,m'),
    FlowDef(start='incineration', end='emission',     indices='t,e,r'),
    FlowDef(start='emission',     end='captured',     indices='t,e,r'),
    FlowDef(start='emission',     end='atmosphere',   indices='t,e,r'),
    FlowDef(start='captured',     end='virginccu',    indices='t,e,r')
]


prm_defs = [
    # EOL rates
    PrmDef(name='mechanical_recycling_rate', process='eol', indices='t,m'),
    PrmDef(name='chemical_recycling_rate', process='eol', indices='t,m'),
    PrmDef(name='solvent_recycling_rate', process='eol', indices='t,m'),
    PrmDef(name='incineration_rate', process='eol', indices='t,m'),
    PrmDef(name='uncontrolled_losses_rate', process='eol', indices='t,m'),
    # virgin production rates
    PrmDef(name='bio_production_rate', process='virgin', indices='t,m'),
    PrmDef(name='daccu_production_rate', process='virgin', indices='t,m'),
    # recycling losses
    PrmDef(name='mechanical_recycling_yield', process='reclmech', indices='t,m'),
    PrmDef(name='reclmech_loss_uncontrolled_rate', process='reclmech', indices='t,m'),
    # other
    PrmDef(name='material_shares_in_goods', process='fabrication', indices='m,g', name_to_load='good_and_material_shares'),
    PrmDef(name='emission_capture_rate', process='emission', indices='t'),
    PrmDef(name='carbon_content_materials', process='use', indices='e,m'),
]


# @load_or_recalculate #TODO
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

    compute_flows(main_model, use_stock_inflows, use_stock_outflows)

    compute_stocks(main_model, use_stock_values)

    mass_balance_plausible(main_model)

    return main_model


def initiate_model(main_model: SimsonMFASystem):

    # processes
    main_model.ProcessList = [Process(Name=name, ID=id) for id, name in enumerate(processes)]

    # parameters
    main_model.ParameterDict = dict(prm_def.to_prm(i, processes) for i, prm_def in enumerate(prm_defs))
    # correct values
    msg = main_model.ParameterDict['material_shares_in_goods']
    msg.Values[...] = msg.Values / np.sum(msg.Values, axis=0, keepdims=True)

    # flows
    main_model.FlowDict = dict(flow_def.to_flow(processes) for flow_def in flow_defs)
    main_model.Initialize_FlowValues()

    # stocks
    main_model.StockDict = {stock.Name: stock for stock in stocks}
    main_model.Initialize_StockValues()

    check_consistency(main_model)


def set_up_model():

    cfg.init_items_dict()

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


def compute_flows(model: SimsonMFASystem, use_inflows: np.ndarray, use_outflows: np.ndarray):

    prms = DictVariableCreator(model.ParameterDict)
    f = DictVariableCreator(model.FlowDict)

    fabrication_2_use = np.einsum('trg,mg->trmg', use_inflows, prms.material_shares_in_goods)
    f.fabrication_2_use = np.einsum('trmg,em->termg', fabrication_2_use, prms.carbon_content_materials)

    use_2_eol = np.einsum('trg,mg->trmg', use_outflows, prms.material_shares_in_goods)
    f.use_2_eol = np.einsum('trmg,em->termg', use_2_eol, prms.carbon_content_materials)

    f.eol_2_reclmech = np.einsum('termg,tm->term', f.use_2_eol, prms.mechanical_recycling_rate)
    f.reclmech_2_recl = np.einsum('term,tm->term', f.eol_2_reclmech, prms.mechanical_recycling_yield)
    reclmech_loss = f.eol_2_reclmech - f.reclmech_2_recl
    f.reclmech_2_uncontrolled = np.einsum('term,tm->term', reclmech_loss, prms.reclmech_loss_uncontrolled_rate)
    f.reclmech_2_incineration = reclmech_loss - f.reclmech_2_uncontrolled

    f.eol_2_reclchem = np.einsum('termg,tm->term', f.use_2_eol, prms.chemical_recycling_rate)
    f.reclchem_2_recl = f.eol_2_reclchem

    f.eol_2_reclsolv = np.einsum('termg,tm->term', f.use_2_eol, prms.solvent_recycling_rate)
    f.reclsolv_2_recl = f.eol_2_reclsolv

    f.eol_2_incineration = np.einsum('termg,tm->term', f.use_2_eol, prms.incineration_rate)
    f.eol_2_uncontrolled = np.einsum('termg,tm->term', f.use_2_eol, prms.uncontrolled_losses_rate)

    f.eol_2_landfill = np.einsum('termg->term', f.use_2_eol) - f.eol_2_reclmech - f.eol_2_reclchem - f.eol_2_reclsolv - f.eol_2_incineration - f.eol_2_uncontrolled

    f.incineration_2_emission = np.einsum('term->ter', f.eol_2_incineration + f.reclmech_2_incineration)

    f.emission_2_captured = np.einsum('ter,t->ter', f.incineration_2_emission, prms.emission_capture_rate)
    f.emission_2_atmosphere = f.incineration_2_emission - f.emission_2_captured
    f.captured_2_virginccu = f.emission_2_captured

    f.recl_2_fabrication = f.reclmech_2_recl + f.reclchem_2_recl + f.reclsolv_2_recl
    f.virgin_2_fabrication = np.einsum('termg->term', f.fabrication_2_use) - f.recl_2_fabrication

    f.virgindaccu_2_virgin = np.einsum('term,tm->term', f.virgin_2_fabrication, prms.daccu_production_rate)
    f.virginbio_2_virgin = np.einsum('term,tm->term', f.virgin_2_fabrication, prms.bio_production_rate)

    virgin_2_fabrication_total = np.einsum('term->ter', f.virgin_2_fabrication)
    virgin_material_shares = np.einsum('term,ter->term', f.virgin_2_fabrication, 1. / virgin_2_fabrication_total)
    captured_2_virginccu_by_mat = np.einsum('ter,term->term', f.captured_2_virginccu, virgin_material_shares)

    f.virginccu_2_virgin[model.slice_id('term', e='C')] = captured_2_virginccu_by_mat[model.slice_id('term', e='C')]
    ratio_nonc_to_c = prms.carbon_content_materials[model.slice_id('em', e='Other Elements')] / prms.carbon_content_materials[model.slice_id('em', e='C')]
    f.virginccu_2_virgin[model.slice_id('term', e='Other Elements')] = np.einsum('trm,m->trm', f.virginccu_2_virgin[model.slice_id('term', e='C')], ratio_nonc_to_c)

    f.virginfoss_2_virgin = f.virgin_2_fabrication - f.virgindaccu_2_virgin - f.virginbio_2_virgin - f.virginccu_2_virgin

    f.sysenv_2_virginfoss = f.virginfoss_2_virgin
    f.atmosphere_2_virginbio = np.einsum('term->ter', f.virginbio_2_virgin)
    f.atmosphere_2_virgindaccu = np.einsum('term->ter', f.virgindaccu_2_virgin)
    f.sysenv_2_virginccu = f.virginccu_2_virgin - captured_2_virginccu_by_mat

    # non-C atmosphere & captured has no meaning & is equivalent to sysenv

    return


def compute_stocks(model: SimsonMFASystem, stock_values):
    prms = DictVariableCreator(model.ParameterDict)
    stocks = DictVariableCreator(model.StockDict)
    flows = DictVariableCreator(model.FlowDict)
    stocks_by_material = np.einsum('trg,mg->trmg', stock_values, prms.material_shares_in_goods)
    stocks.in_use_stock = np.einsum('trmg,em->termg', stocks_by_material, prms.carbon_content_materials)
    stocks.in_use_stock_inflow = flows.fabrication_2_use
    stocks.in_use_stock_outflow = flows.use_2_eol
    stocks.landfill_stock_inflow = flows.eol_2_landfill
    stocks.landfill_stock = stocks.landfill_stock_inflow.cumsum(axis=0)
    stocks.uncontrolled_stock_inflow = flows.eol_2_uncontrolled + flows.reclmech_2_uncontrolled
    stocks.uncontrolled_stock = stocks.uncontrolled_stock_inflow.cumsum(axis=0)
    stocks.atmospheric_stock_inflow = flows.emission_2_atmosphere
    stocks.atmospheric_stock_outflow = flows.atmosphere_2_virgindaccu + flows.atmosphere_2_virginbio
    stocks.atmospheric_stock = stocks.atmospheric_stock_inflow.cumsum(axis=0) - stocks.atmospheric_stock_outflow.cumsum(axis=0)
    return


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
    names_failed = [n for id, n in enumerate(processes) if id_failed[id]]
    if names_failed:
            raise RuntimeError(f"Error, Mass Balance fails for processes {', '.join(names_failed)}")
    else:
        print("Success - Mass balance consistent!")
    return


if __name__ == "__main__":
    setup()
    mfa = load_simson_mfa()
    if cfg.do_visualize['sankey']:
        visualize_mfa_sankey(mfa)
    export_to_dict(mfa, 'data/output/mfa.pickle')


    # # incineration_output__from_polymers__material_shares:
    #            CO2     other_gas
    #   C        1       0
    #   other_el 0       1

    # # spec_incineration_atmosphere:
    # C_out:
    #             C_in    Other_el_in
    #   CO2       0       0
    #   other_gas 0       0
    # other_el_out:
    #             C_in    Other_el_in
    #   CO2       32/12   0
    #   other_gas 0       0
    # incineration_output__from_polymers = np.einsum('term,ea->tera', incineration_input_polymers, incineration_output__from_polymers__material_shares)
    # # this is needed to calculate the amount of CO2 generated, not just the amount of C
    # incineration_output__from_atmosphere = np.einsum('tera,eEa->tEra', incineration_output__from_polymers, spec_incineration_atmosphere)
    # incineration_output_total = incineration_output__from_polymers + incineration_output__from_atmosphere