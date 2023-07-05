import pandas as pd
import csv
from src.tools.config import cfg


def load_country_names_and_codes():

    # TODO: load directly to df

    with open(cfg.data_path + '/original/Mueller/Mueller_countries.csv') as csv_file:
        mueller_countries = list(csv.reader(csv_file, delimiter=','))
        mueller_country_names = [c[0] for c in mueller_countries]
        mueller_country_codes = [c[1] for c in mueller_countries]

    # add country codes
    country_names_and_codes = pd.DataFrame.from_dict({'country': mueller_country_names,
                                                      'ccode': mueller_country_codes})
    return country_names_and_codes
