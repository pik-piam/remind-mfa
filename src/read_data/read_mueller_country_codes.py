import pandas as pd
import os
from src.tools.config import cfg


def load_country_names_and_codes():
    mueller_countries_path = os.path.join(cfg.data_path, 'original', 'mueller', 'Mueller_countries.csv')
    df = pd.read_csv(mueller_countries_path)

    return df


if __name__ == '__main__':
    df = load_country_names_and_codes()
    print(df)
