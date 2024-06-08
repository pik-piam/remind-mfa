from matplotlib import pyplot as plt
import os
import numpy as np
import pandas as pd
import pickle
from src.tools.config import cfg


def show_and_save(filename_base: str = None):
    if cfg.do_save_figs:
        plt.savefig(cfg.data_path + f"/output/{filename_base}.png")
    if cfg.do_show_figs:
        plt.show()


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
