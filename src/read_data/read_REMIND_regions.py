import os
from src.tools.config import cfg
import pandas as pd


def get_region_to_countries_df():
    remind_data_path = os.path.join(cfg.data_path, 'original', 'remind', 'REMINDRegions.csv')
    df = pd.read_csv(remind_data_path)
    df.set_index('country', inplace=True)
    return df


def get_region_to_countries_dict():
    df = get_region_to_countries_df()
    gk = df.groupby('region')
    regions_dict = gk['country'].apply(list).to_dict()
    return regions_dict


if __name__ == '__main__':
    df = get_region_to_countries_df()
    print(df)
    regions_dict = get_region_to_countries_dict()
    for region, countries in regions_dict.items():
        print(f"{region}: {countries}")
