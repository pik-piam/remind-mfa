from matplotlib import pyplot as plt
import numpy as np
from src.tools.config import cfg


def show_and_save(filename_base: str = None):
    if cfg.do_save_figs:
        plt.savefig(f"data/output/{filename_base}.png")
    if cfg.do_show_figs:
        plt.show()


class Years():

    def __init__(self, start_year, end_year, first_year_in_data):
        self.calendar = np.arange(start_year, end_year + 1)
        self.ids = self.calendar - first_year_in_data
