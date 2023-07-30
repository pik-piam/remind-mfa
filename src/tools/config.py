import os
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
        self.include_trade = False
        self.include_scrap_trade = False

        self.curve_strategy = 'Pauliuk'  # Options: Pauliuk, Pehl

        self.steel_data_source = 'Mueller'  # Options: Mueller
        self.pop_data_source = 'UN'  # Options: UN
        self.gdp_data_source = 'IMF'  # Options: IMF
        self.trade_data_source = 'WorldSteel'  # Options: WorldSteel
        self.steel_price_data_source = 'USGS'  # Options: USGS
        self.scrap_price_data_source = 'USGS'  # Options: USGS
        self.region_data_source = 'REMIND'  # Options: REMIND, Pauliuk, REMIND_EU
        self.lifetime_data_source = 'Wittig'  # Options: Wittig

        self.using_categories = ['Transport', 'Machinery', 'Construction', 'Product']
        self.recycling_categories = ['CD', 'MSW', 'WEEE', 'ELV', 'IEW', 'INEW', 'Dis', 'NotCol']
        self.categories_with_total = ['Transport', 'Machinery', 'Construction', 'Product', 'Total']

        self.distributions = {
            'transportation': 20,
            'machinery': 30,
            'construction': 75,
            'products': 15
        }

    def customize(self, fpath: str):
        with open(fpath, 'r') as f:
            config_dict = yaml.safe_load(f)
        for prm_name, prm_value in config_dict.items():
            if prm_name not in self.__dict__:
                raise Exception(f'The custom parameter {prm_name} given in the file {os.path.basename(fpath)} '
                                'is not registered in the default config definition. '
                                'Maybe you misspelled it or did not add it to the defaults?')
            setattr(self, prm_name, prm_value)

    def generate_yml(self, fpath: str = 'custom_config.yml'):
        with open(fpath, 'w') as f:
            yaml.dump(self.__dict__, f, sort_keys=False)

    @property
    def n_years(self):
        return self.end_year - self.start_year + 1

    @property
    def years(self):
        return np.arange(self.start_year, self.end_year + 1)


cfg = Config()

if __name__ == '__main__':
    cfg.generate_yml()
