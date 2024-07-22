from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
from src.tools.config import cfg


def show_and_save(filename_base: str = None):
    if cfg.do_save_figs:
        plt.savefig(cfg.data_path + f"/output/{filename_base}.png")
    if cfg.do_show_figs:
        plt.show()


def get_np_from_df(df_in: pd.DataFrame, dims: tuple):
    df = df_in.copy()
    dim_columns = [d for d in dims if d in df.columns]
    value_cols = np.setdiff1d(df.columns, dim_columns)
    df.set_index(dim_columns, inplace=True)
    df = df.sort_values(by=dim_columns)

    # check for sparsity
    if df.index.has_duplicates:
        raise Exception("Double entry in df!")
    shape_out = df.index.shape if len(dim_columns) == 1 else df.index.levshape
    if np.prod(shape_out) != df.index.size:
        raise Exception("Dataframe is missing values!")

    if np.any(value_cols != 'value'):
        out = {vc: df[vc].values.reshape(shape_out) for vc in value_cols}
    else:
        out = df["value"].values.reshape(shape_out)
    return out
