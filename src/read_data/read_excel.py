import pandas as pd
import os
from src.tools.config import cfg
from src.tools.tools import fill_missing_values_linear


def get_excel_daccu_production_rate():
    return get_data('daccu_production_rate')

def get_excel_bio_production_rate():
    return get_data('bio_production_rate')

def get_excel_uncontrolled_losses_rate():
    return get_data('uncontrolled_losses_rate')

def get_excel_incineration_rate():
    return get_data('incineration_rate')

def get_excel_mechanical_recycling_rate():
    return get_data('mechanical_recycling_rate')

def get_excel_chemical_recycling_rate():
    return get_data('chemical_recycling_rate')

def get_excel_solvent_recycling_rate():
    return get_data('solvent_recycling_rate')

def get_excel_mechanical_recycling_yield():
    return get_data('mechanical_recycling_yield')

def get_excel_reclmech_loss_uncontrolled_rate():
    return get_data('reclmech_loss_uncontrolled_rate')

def get_excel_emission_capture_rate():
    return get_data('emission_capture_rate')

def get_excel_carbon_content_materials():
    df = get_data('carbon_content_materials', interpolate_years=False)
    df = df.join(pd.DataFrame.from_dict({'Element': cfg.elements}), how='cross')
    df.loc[df['Element'] != 'C','value'] = 1.- df.loc[df['Element'] != 'C','value']
    return df

def get_data(sheet_name, interpolate_years = True):
    filepath = os.path.join(cfg.data_path, 'original', 'excel', 'data.xlsx')
    df = pd.read_excel(filepath, sheet_name = sheet_name)
    if interpolate_years:
        df = fill_missing_values_linear(df)
    return df
