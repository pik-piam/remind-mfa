from os.path import join
import yaml
import numpy as np


class Config:

    def __init__(self):
        """
        Initialize with defaults
        """
        self.data_path = 'data'
        self.recalculate_data = False
        self.include_scenarios = True

        self.do_show_figs = True
        self.do_save_figs = True

        self.start_year = 1900
        self.end_year = 2100

        self.curve_strategy = 'Pehl'  # Options: Pauliuk, Pehl
        self.steel_data_source = 'Mueller'  # Options: Mueller
        self.pop_data_source = 'UN'  # Options: UN, KC-Lutz (only for scenarios)
        self.gdp_data_source = 'IMF'  # Options: IMF, Koch-Leimbach (only for scenarios)
        self.trade_data_source = 'WorldSteel'  # Options: WorldSteel
        self.steel_price_data_source = 'USGS'  # Options: USGS
        self.scrap_price_data_source = 'USGS'  # Options: USGS
        self.region_data_source = 'REMIND'  # Options: REMIND, Pauliuk, REMIND_EU
        self.lifetime_data_source = 'Pauliuk'  # Options: Wittig, Pauliuk

        self.using_categories = ['Transport', 'Machinery', 'Construction', 'Product']
        self.recycling_categories = ['CD', 'MSW', 'WEEE', 'ELV', 'IEW', 'INEW', 'Form', 'Fabr', 'Dis', 'NotCol']
        self.categories_with_total = ['Transport', 'Machinery', 'Construction', 'Product', 'Total']
        self.scenarios = ['SSP1', 'SSP2', 'SSP3', 'SSP4', 'SSP5']

        self.exog_eaf_USD98 = 76

        # ADAPTABLE PARAMETER

        self.region_data_source = 'REMIND'  # Options: REMIND, Pauliuk, REMIND_EU

        self.simulation_name = 'SIMSON_Test_1'
        self.region_data_source = 'REMIND'  # Options: REMIND, Pauliuk, REMIND_EU

        self.max_scrap_share_production_base_model = 0.60
        self.scrap_in_BOF_rate = 0.22
        self.forming_yield = 0.937246

        # econ model configurations
        self.do_model_economy = True
        self.econ_base_year = 2008

        self.elasticity_steel = -0.2
        self.elasticity_scrap_recovery_rate = -1
        self.elasticity_dissassembly = -0.8

        self.r_free_recov = 0
        self.r_free_diss = 0

        self.steel_price_change_by_scenario = [0.5, 0.1, 0.2, 0, -0.3]
        # e.g. 0.5 or [50,10,20,0,-30] for all scenarios. 50 e.g. indicates a 50 % increase of the steel

        self.do_change_inflow = False
        self.inflow_change_base_year = 2023
        self.inflow_change_by_scenario = [-0.2, 0, 0.1, 0.2, 0.3]
        self.inflow_change_by_category = [-0.2, 0, 0, 0]

        self.do_change_reuse = False
        self.reuse_change_base_year = 2023
        self.reuse_change_by_category = [0, 0.2, 0, 0]
        self.reuse_change_by_scenario = 0
        # can be either expressed as float value for all categories or list with individual values

    def customize(self, config_dict: dict):
        name = config_dict['simulation_name']
        for prm_name, prm_value in config_dict.items():
            if prm_name not in self.__dict__:
                raise Exception(f'The custom parameter {prm_name} given in the configuration {name} '
                                'is not registered in the default config definition. '
                                'Maybe you misspelled it or did not add it to the defaults?')
            setattr(self, prm_name, prm_value)
        return self

    def generate_yml(self, fpath: str = 'yaml_test.yml'):
        with open(fpath, 'w') as f:
            yaml.dump(self.__dict__, f, sort_keys=False)

    @property
    def n_years(self):
        return self.end_year - self.start_year + 1

    @property
    def years(self):
        return np.arange(self.start_year, self.end_year + 1)

    @property
    def econ_start_index(self):
        return self.econ_base_year - self.start_year + 1

    def _price_change_list(self):
        if isinstance(self.steel_price_change_by_scenario, list):
            return self.steel_price_change_by_scenario
        else:
            return [self.steel_price_change_by_scenario] * len(cfg.scenarios)

    @property
    def price_change_factor(self):
        return 1 + np.array(self._price_change_list())

    def _inflow_change_category_list(self):
        if isinstance(self.inflow_change_by_category, list):
            return self.inflow_change_by_category
        else:
            return [self.inflow_change_by_category] * len(self.using_categories)

    def _inflow_change_scenario_list(self):
        if isinstance(self.inflow_change_by_scenario, list):
            return self.inflow_change_by_scenario
        else:
            return [self.inflow_change_by_scenario] * len(self.scenarios)

    @property
    def inflow_change_factor(self):
        return np.einsum('g,s->gs',
                         1 + np.array(self._inflow_change_category_list()),
                         1 + np.array(self._inflow_change_scenario_list()))

    def _reuse_change_category_list(self):
        if isinstance(self.reuse_change_by_category, list):
            return self.reuse_change_by_category
        else:
            return [self.reuse_change_by_category] * len(self.using_categories)

    def _reuse_change_scenario_list(self):
        if isinstance(self.reuse_change_by_scenario, list):
            return self.reuse_change_by_scenario
        else:
            return [self.reuse_change_by_scenario] * len(self.scenarios)

    @property
    def reuse_factor(self):
        factor = np.einsum('g,s->gs',
                           1 + np.array(self._reuse_change_category_list()),
                           1 + np.array(self._inflow_change_scenario_list()))
        return np.maximum(1, factor)
        # Reuse factor needs to be at least one, as it is deducted by one later and needs to be positive


cfg = Config()

if __name__ == '__main__':
    cfg.generate_yml()
