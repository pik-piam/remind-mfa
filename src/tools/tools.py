from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
from src.read_data.read_REMIND_regions import get_region_to_countries_df
from src.tools.config import cfg


def show_and_save(filename_base: str = None):
    if cfg.do_save_figs:
        plt.savefig(cfg.data_path+f"/output/{filename_base}.png")
    if cfg.do_show_figs:
        plt.show()


def read_processed_data(path):
    df = pd.read_csv(path)
    df = df.set_index(list(df.columns)[0])
    df = _csv_read_change_years_to_int(df)

    return df


def _csv_read_change_years_to_int(df):
    columns = df.columns
    start_year_idx = 0
    str_columns = []
    while True:
        try:
            start_year = int(columns[start_year_idx])
            break
        except ValueError:
            str_columns.append(columns[start_year_idx])
            start_year_idx += 1
            if start_year_idx > 10:
                raise RuntimeError('Problem reading csv file: year columns seem to be formatted wrongly.')
    end_year = int(columns[-1])
    new_columns = list(range(start_year, end_year + 1))
    df.columns = pd.Index(str_columns + new_columns)
    return df


def fill_missing_values_linear(df):
    df = df.apply(pd.to_numeric)
    df = df.reindex(columns=cfg.years)
    df = df.interpolate(axis=1)
    return df


def transform_per_capita(df, total_from_per_capita, country_specific):
    # un_pop files need to be imported here to avoid circular import error
    from src.read_data.read_UN_population import load_un_pop
    if country_specific:
        df_pop = load_un_pop(country_specific=True)
    else:  # region specific
        df_pop = load_un_pop(country_specific=False)
    columns_to_use = df.columns.intersection(df_pop.columns)

    if total_from_per_capita:
        df.loc[:, columns_to_use] *= df_pop.loc[:, columns_to_use]
    else:  # get per capita from total data
        df.loc[:, columns_to_use] /= df_pop.loc[:, columns_to_use]
    return df


def group_country_data_to_regions(df_by_country, is_per_capita, group_by_subcategories=False):
    if is_per_capita:
        df_by_country = transform_per_capita(df_by_country, total_from_per_capita=True, country_specific=True)
    df_by_country = df_by_country.reset_index()
    regions = get_region_to_countries_df()
    df = pd.merge(regions, df_by_country, on='country')
    if not group_by_subcategories:
        df = df.groupby('region').sum(numeric_only=False)

    else:  # group_by_subcategories
        df = df.groupby(['region', 'category']).sum(numeric_only=False)
    df = df.drop(columns=['country'])

    if is_per_capita:
        df = transform_per_capita(df, total_from_per_capita=False, country_specific=False)

    return df

def get_steel_category_total(df_stock, region_data=True):
    scope = 'region'
    if not region_data:
        scope = 'country'
    df_stock = df_stock.reset_index()
    gk_stock = df_stock.groupby(scope)
    df_stock_totals = gk_stock.sum()

    return df_stock_totals



class Years:

    def __init__(self, start_year, end_year, first_year_in_data):
        self.calendar = np.arange(start_year, end_year + 1)
        self.ids = self.calendar - first_year_in_data
