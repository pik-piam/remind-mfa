import numpy as np
from ODYM.odym.modules.ODYM_Classes import Stock
from src.odym_extension.SimsonValueClasses import DictVariableCreator
from src.odym_extension.SimsonMFASystem import SimsonMFASystem

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
    dict(name='in_use_stock',              process_index=processes.index('use'),          stock_type=0, indices='t,e,r,m,g'),
    dict(name='in_use_stock_inflow',       process_index=processes.index('use'),          stock_type=1, indices='t,e,r,m,g'),
    dict(name='in_use_stock_outflow',      process_index=processes.index('use'),          stock_type=2, indices='t,e,r,m,g'),
    dict(name='atmospheric_stock',         process_index=processes.index('atmosphere'),   stock_type=0, indices='t,e,r'    ),
    dict(name='atmospheric_stock_inflow',  process_index=processes.index('atmosphere'),   stock_type=1, indices='t,e,r'    ),
    dict(name='atmospheric_stock_outflow', process_index=processes.index('atmosphere'),   stock_type=2, indices='t,e,r'    ),
    dict(name='landfill_stock',            process_index=processes.index('landfill'),     stock_type=0, indices='t,e,r,m'  ),
    dict(name='landfill_stock_inflow',     process_index=processes.index('landfill'),     stock_type=1, indices='t,e,r,m'  ),
    dict(name='uncontrolled_stock',        process_index=processes.index('uncontrolled'), stock_type=0, indices='t,e,r,m'  ),
    dict(name='uncontrolled_stock_inflow', process_index=processes.index('uncontrolled'), stock_type=1, indices='t,e,r,m'  )
]

flows = [
    dict(start='sysenv',       end='virginfoss',   indices='t,e,r,m'),
    dict(start='sysenv',       end='virginbio',    indices='t,e,r,m'),
    dict(start='sysenv',       end='virgindaccu',  indices='t,e,r,m'),
    dict(start='sysenv',       end='virginccu',    indices='t,e,r,m'),
    dict(start='atmosphere',   end='virginbio',    indices='t,e,r'),
    dict(start='atmosphere',   end='virgindaccu',  indices='t,e,r'),
    dict(start='virginfoss',   end='virgin',       indices='t,e,r,m'),
    dict(start='virginbio',    end='virgin',       indices='t,e,r,m'),
    dict(start='virgindaccu',  end='virgin',       indices='t,e,r,m'),
    dict(start='virginccu',    end='virgin',       indices='t,e,r,m'),
    dict(start='virgin',       end='fabrication',  indices='t,e,r,m'),
    dict(start='fabrication',  end='use',          indices='t,e,r,m,g'),
    dict(start='use',          end='eol',          indices='t,e,r,m,g'),
    dict(start='eol',          end='reclmech',     indices='t,e,r,m'),
    dict(start='eol',          end='reclchem',     indices='t,e,r,m'),
    dict(start='eol',          end='reclsolv',     indices='t,e,r,m'),
    dict(start='eol',          end='uncontrolled', indices='t,e,r,m'),
    dict(start='eol',          end='landfill',     indices='t,e,r,m'),
    dict(start='eol',          end='incineration', indices='t,e,r,m'),
    dict(start='reclmech',     end='recl',         indices='t,e,r,m'),
    dict(start='reclchem',     end='recl',         indices='t,e,r,m'),
    dict(start='reclsolv',     end='recl',         indices='t,e,r,m'),
    dict(start='recl',         end='fabrication',  indices='t,e,r,m'),
    dict(start='reclmech',     end='uncontrolled', indices='t,e,r,m'),
    dict(start='reclmech',     end='incineration', indices='t,e,r,m'),
    dict(start='incineration', end='emission',     indices='t,e,r'),
    dict(start='emission',     end='captured',     indices='t,e,r'),
    dict(start='emission',     end='atmosphere',   indices='t,e,r'),
    dict(start='captured',     end='virginccu',    indices='t,e,r')
]


prms = [
    # EOL rates
    dict(name='mechanical_recycling_rate',       process='eol', indices='t,m'),
    dict(name='chemical_recycling_rate',         process='eol', indices='t,m'),
    dict(name='solvent_recycling_rate',          process='eol', indices='t,m'),
    dict(name='incineration_rate',               process='eol', indices='t,m'),
    dict(name='uncontrolled_losses_rate',        process='eol', indices='t,m'),
    # virgin production rates
    dict(name='bio_production_rate',             process='virgin', indices='t,m'),
    dict(name='daccu_production_rate',           process='virgin', indices='t,m'),
    # recycling losses
    dict(name='mechanical_recycling_yield',      process='reclmech', indices='t,m'),
    dict(name='reclmech_loss_uncontrolled_rate', process='reclmech', indices='t,m'),
    # other
    dict(name='material_shares_in_goods',        process='fabrication', indices='m,g'),
    dict(name='emission_capture_rate',           process='emission', indices='t'),
    dict(name='carbon_content_materials',        process='use', indices='e,m'),
]


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
