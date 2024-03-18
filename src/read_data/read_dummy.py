import pandas as pd
from src.tools.config import cfg
import os

def get_dummy_mechanical_recycling_rates():
    df_materials = pd.DataFrame.from_dict({'Material': cfg.materials})
    df_goods = pd.DataFrame.from_dict({'Good': cfg.in_use_categories})
    df = df_materials.merge(df_goods, how='cross')
    df['value'] = 0.6

    filepath = os.path.join(cfg.data_path, 'original', 'excel', 'data.xlsx')
    with pd.ExcelWriter(filepath) as writer:
        df.to_excel(writer, sheet_name='mechanical_recycling_rate')
    return df

def get_dummy_mechanical_recycling_yields():
    df = pd.DataFrame.from_dict({'Material': cfg.materials})
    df['value'] = 0.8

    filepath = os.path.join(cfg.data_path, 'original', 'excel', 'data.xlsx')
    with pd.ExcelWriter(filepath, mode='a') as writer:
        df.to_excel(writer, sheet_name='mechanical_recycling_yield')
    return df

