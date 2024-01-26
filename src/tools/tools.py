from matplotlib import pyplot as plt
import os
import numpy as np
import pandas as pd
import pickle
from src.tools.config import cfg


# decorator
def load_or_recalculate(recalculate_function):
    def load_or_recalculate_wrapper(*args, **kwargs):
        base_name = recalculate_function.__name__.replace('load_','')
        # type = base_name.split("___")[0]
        file_path = os.path.join(cfg.data_path, 'processed', f'{base_name}.pickle')
        try_reload = cfg.try_reload[base_name] if base_name in cfg.try_reload else False
        if try_reload and os.path.exists(file_path):
            print(f"Load {base_name} from pickle file")
            data = pickle.load(open(file_path, 'rb'))
        else:
            print(f"Recalculate {base_name}")
            data = recalculate_function(*args, **kwargs)
            pickle.dump(data, open(file_path, "wb"))
        return data
    return load_or_recalculate_wrapper


def show_and_save(filename_base: str = None):
    if cfg.do_save_figs:
        plt.savefig(cfg.data_path + f"/output/{filename_base}.png")
    if cfg.do_show_figs:
        plt.show()


def fill_missing_values_linear(df: pd.DataFrame):
    years = cfg.years
    index_cols = [c for c in cfg.aspects if c in df.columns and c != 'Time']
    if 'country' in df.columns:
        index_cols.append('country')

    def interpolate_single(df: pd.DataFrame):
        df = df \
            .query('Time in @years') \
            .merge(pd.DataFrame.from_dict({'Time': years}),
                on='Time',
                how='right') \
            .sort_values(by='Time') \
            .interpolate(axis=0, limit_direction='both')
        for ic in index_cols:
            df[ic] = df[ic].fillna(method='ffill').fillna(method='bfill')
        return df

    if index_cols:
        df = df \
            .groupby(by=index_cols) \
            .apply(lambda group: interpolate_single(group)) \
            .reset_index(drop=True)
    else:
        df = interpolate_single(df)
    return df


def transform_per_capita_df(df: pd.DataFrame=None, total_from_per_capita=False):
    if 'country' in df.columns:
        df_pop = cfg.data.df_pop_countries
        regi_col = 'country'
    else:
        df_pop = cfg.data.df_pop
        regi_col = 'Region'

    df = df.copy()
    df = df.merge(df_pop.rename(columns={'value': 'pop'}),
                how='left',
                on=['Time', regi_col])
    if total_from_per_capita:
        df['value'] = df['value'] * df['pop']
    else:  # get per capita from total data
        df['value'] = df['value'] / df['pop']
    return df.drop(columns='pop')


def transform_per_capita_np(arr: np.array=None, total_from_per_capita=False, stock_dims = 'trc'):
    pop_arr = cfg.data.np_pop[:arr.shape[0],:] #enable both historic and all
    if total_from_per_capita:
        arr_out = np.einsum(f'{stock_dims},tr->{stock_dims}', arr, pop_arr)
    else:  # get per capita from total data
        arr_out = np.einsum(f'{stock_dims},tr->{stock_dims}', arr, 1./pop_arr)
    return arr_out


def group_country_data_to_regions(df_by_country: pd.DataFrame, is_per_capita=False):

    if is_per_capita:
        df_by_country = transform_per_capita_df(df_by_country, total_from_per_capita=True)

    df_regions = cfg.data.df_region_mapping

    df = df_by_country \
        .merge(df_regions,
               on='country',
               how='inner')
    index_cols = [c for c in cfg.aspects if c in df.columns]
    value_cols = [c for c in df.columns if c not in index_cols and c != 'country']
    df = df \
        .groupby(by=index_cols) \
        .agg({v: 'sum' for v in value_cols}) \
        .reset_index()

    if is_per_capita:
        df = transform_per_capita_df(df, total_from_per_capita=False)

    return df


def get_np_from_df(df_in: pd.DataFrame, return_index_letters = False):
    df = df_in.copy()
    aspects = [a for a in cfg.aspects if a in df.columns]
    value_cols = np.setdiff1d(df.columns, aspects)
    df.set_index(list(aspects), inplace=True)
    df = df.sort_values(by=list(aspects))

    # check for sparsity
    if df.index.has_duplicates:
        raise Exception("Double entry in df!")
    shape_out = df.index.shape if len(aspects) == 1 else df.index.levshape
    if np.prod(shape_out) != df.index.size:
        raise Exception("Dataframe is missing values!")

    if np.any(value_cols != 'value'):
        out = {vc: df[vc].values.reshape(shape_out) for vc in value_cols}
    else:
        out = df["value"].values.reshape(shape_out)

    if return_index_letters:
        return out, ''.join(cfg.index_letters[a] for a in aspects)
    else:
        return out


def get_dsm_data(dsms, func):
    array_out = np.array([[func(dsm) for dsm in row] for row in dsms])
    array_out = np.moveaxis(array_out, -1, 0)
    return array_out
