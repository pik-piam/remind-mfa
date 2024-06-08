import os
import numpy as np
import pandas as pd
from src.tools.config import cfg
from src.tools.tools import get_np_from_df


def load_data(type):
    path = os.path.join(cfg.data_path, 'transfer', 'data', f"{type}.csv")
    data = pd.read_csv(path)
    data = get_np_from_df(data)
    return data
