import os
from src.tools.config import cfg
import pandas as pd


def get_remind_regions():
    remind_data_path = os.path.join(cfg.data_path, 'original', 'remind', 'REMINDRegions.csv')
    df_remind = pd.read_csv(remind_data_path)
    df_remind.set_index('country', inplace=True)
    return df_remind


def get_remind_eu_regions():
    remind_eu_data_path = os.path.join(cfg.data_path, 'original', 'remind', 'REMIND_EU_Regions.csv')
    df_remind_eu = pd.read_csv(remind_eu_data_path)
    df_remind_eu.set_index('country', inplace=True)
    return df_remind_eu


if __name__ == '__main__':
    df = get_remind_regions()
    print(df)
