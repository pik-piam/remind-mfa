from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
from src.tools.config import cfg


def show_and_save(filename_base: str = None):
    if cfg.do_save_figs:
        plt.savefig(cfg.data_path + f"/output/{filename_base}.png")
    if cfg.do_show_figs:
        plt.show()


def read_processed_data(path, is_yearly_data=True):
    df = pd.read_csv(path)
    df = df.set_index(list(df.columns)[0])
    if is_yearly_data:
        df = _make_year_column_names_integers(df)
    return df


def _make_year_column_names_integers(df):
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
                raise RuntimeError('Problem reading csv file: year columns seem to be formated wrongly.')
    end_year = int(columns[-1])
    new_columns = list(range(start_year, end_year + 1))
    df.columns = pd.Index(str_columns + new_columns)
    return df


def fill_missing_values_linear(df, start_year=cfg.start_year, end_year=cfg.end_year):
    years = np.arange(start_year, end_year + 1)
    df = df.apply(pd.to_numeric)
    df = df.reindex(columns=years)
    df = df.interpolate(axis=1, limit_direction='both')
    return df


def transform_per_capita(df, total_from_per_capita, country_specific):
    # un_pop files need to be imported here to avoid circular import error
    from src.read_data.load_data import load_pop
    df = df.copy()
    df = df.sort_index()
    pop_source = cfg.pop_data_source
    if isinstance(df.index, pd.MultiIndex):
        if df.index.names[1] == 'SSP':
            pop_source = 'KC-Lutz'

    df_pop = load_pop(pop_source=pop_source, country_specific=country_specific)
    columns_to_use = df.columns.intersection(df_pop.columns)

    if total_from_per_capita:
        df.loc[:, columns_to_use] *= df_pop.loc[:, columns_to_use]
    else:  # get per capita from total data
        df.loc[:, columns_to_use] /= df_pop.loc[:, columns_to_use]

    return df


def group_country_data_to_regions(df_by_country, is_per_capita, data_split_into_categories=False):
    from src.read_data.load_data import load_regions

    grouping_factor = 'region'
    if data_split_into_categories:
        country_index = df_by_country.index
        category_name = country_index.names[1]
        grouping_factor = ['region', category_name]
    if is_per_capita:
        df_by_country = transform_per_capita(df_by_country, total_from_per_capita=True, country_specific=True)
    df_by_country = df_by_country.reset_index()

    df_regions = load_regions()
    df = pd.merge(df_regions, df_by_country, on='country')

    df = df.groupby(grouping_factor).sum(numeric_only=False)
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


def get_np_from_df(df: pd.DataFrame, data_split_into_categories):
    df = df.sort_index()
    np_array = df.to_numpy()
    if data_split_into_categories:
        np_array = np_array.reshape(df.index.levshape + np_array.shape[-1:])
    return np_array


class Years:

    def __init__(self, start_year, end_year, first_year_in_data):
        self.calendar = np.arange(start_year, end_year + 1)
        self.ids = self.calendar - first_year_in_data
