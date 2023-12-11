import os
from src.tools.config import cfg
import pandas as pd


def get_pauliuk_regions():
    remind_data_path = os.path.join(cfg.data_path, 'original', 'Pauliuk', 'Pauliuk_Regions.csv')
    df = pd.read_csv(remind_data_path)
    df.set_index('country', inplace=True)
    return df


if __name__ == '__main__':
    from src.read_data.load_data import load_regions

    df = load_regions(region_source='Pauliuk')
    print(df)
    print(df['region'].unique())
