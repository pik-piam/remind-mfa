import yaml
import numpy as np


class Config():

    def __init__(self):
        """
        Initialize with defaults
        """
        self.data_path = 'data'
        self.recalculate_data = False

        self.do_show_figs = True
        self.do_save_figs = True

        self.start_year = 1900
        self.end_year = 2100

        self.scrap_recovery_rate = 0.85
        self.max_scrap_share_production = 0.60

        self.constant_scrap_recovery_rate = True
        self.include_trade = True
        self.include_scrap_trade = True

        self.curve_strategy = 'Pauliuk'  # Options = Pauliuk, Pehl
        self.steel_data_source = 'Mueller'  # Options = Mueller
        self.lifetime_data_source = 'Wittig'  # Options = Wittig

        self.subcategories = ['Transport', 'Machinery', 'Construction', 'Product']
        self.categories = ['Transport', 'Machinery', 'Construction', 'Product','Total']

        self.distributions = {
            'transportation': 20,
            'machinery': 30,
            'construction': 75,
            'products': 15
        }

    def customize(self, fpath='config.yml'):
        with open(fpath, 'r') as f:
            config_dict = yaml.safe_load(f)
        for prm_name, prm_value in config_dict.items():
            if prm_name not in self.__dict__:
                raise Exception(f'There is no default for the parameter {prm_name} in the config.yml. '
                                'Maybe you misspelled it or didnt add it to the defaults?')
            setattr(self, prm_name, prm_value)

    @property
    def n_years(self):
        return self.end_year - self.start_year

    @property
    def years(self):
        return np.arange(self.start_year, self.end_year + 1)


cfg = Config()
