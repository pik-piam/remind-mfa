import pandas as pd
from src.tools.config import cfg

def get_dummy_mechanical_recycling_rates():
    df_elements = pd.DataFrame.from_dict({'Element': cfg.elements})
    df_goods = pd.DataFrame.from_dict({'Good': cfg.in_use_categories})
    df = df_elements.merge(df_goods, how='cross')
    df['value'] = 0.6
    return df

def get_dummy_mechanical_recycling_yields():
    df = pd.DataFrame.from_dict({'Element': cfg.elements})
    df['value'] = 0.8
    return df

