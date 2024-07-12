import os
import numpy as np
import pandas as pd
from src.tools.config import cfg


def read_data_to_df(type: str, name: str):
    if type == 'dataset':
        path = os.path.join(cfg.data_path, 'input', 'datasets', f"{name}.csv")
    else:
        raise RuntimeError(f"Invalid type {type}.")
    data = pd.read_csv(path)
    return data


def read_data_to_list(type: str, filename: str, dtype: type):
    if type == 'dimension':
        path = os.path.join(cfg.data_path, 'input', 'dimensions', f"{filename}.csv")
    else:
        raise RuntimeError(f"Invalid type {type}.")
    data = np.loadtxt(path, dtype=dtype, delimiter=';').tolist()
    # catch size one lists, which are transformed to scalar by np.ndarray.tolist()
    data = data if isinstance(data, list) else [data]
    return data