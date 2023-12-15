from os.path import join
import yaml
import numpy as np


class Config:
    """
    Class of SIMSON configurations. Contains both general configurations like SSP scenarios
    and product categories to use as well as adaptable parameters like steel price change.
    A common instance of this class ('cfg') is used by most other files, its attributes can be
    adapted with the 'customize' method.
    """

    def __init__(self):
        """
        Creates instance of config class with default parameters. These can :func:`print`
        modified through :py:func:`src.tools.config.Config#customize` method.
        """
        self.data_path = 'data'
        self.recalculate_data = False
        self.include_gdp_and_pop_scenarios_in_prediction = True

        self.do_show_figs = True
        self.do_save_figs = True

        self.start_year = 1900
        self.end_year = 2100

        self.curve_strategy = 'Pauliuk'  # Options: Pauliuk, Pehl, Duerrwaechter
        self.steel_data_source = 'IEDatabase'  # Options: Mueller, IEDatabase
        self.pop_data_source = 'UN'  # Options: UN, KC-Lutz (only for scenarios)
        self.gdp_data_source = 'IMF'  # Options: IMF, Koch-Leimbach (only for scenarios)
        self.trade_data_source = 'WorldSteel'  # Options: WorldSteel
        self.steel_price_data_source = 'USGS'  # Options: USGS
        self.scrap_price_data_source = 'USGS'  # Options: USGS
        self.production_data_source = 'WorldSteel'  # Options: WorldSteel
        self.use_data_source = 'WorldSteel'  # Options: WorldSteel
        self.scrap_trade_data_source = 'WorldSteel'  # Options: WorldSteel
        self.indirect_trade_source = 'WorldSteel'  # Options: WorldSteel
        self.lifetime_data_source = 'Wittig'  # Options: Wittig, Pauliuk

        self.in_use_categories = ['Transport', 'Machinery', 'Construction', 'Products']
        self.recycling_categories = ['CD', 'MSW', 'WEEE', 'ELV', 'IEW', 'INEW', 'Form', 'Fabr', 'Dis', 'NotCol']
        self.scenarios = ['SSP1', 'SSP2', 'SSP3', 'SSP4', 'SSP5']

        self.n_use_categories = len(self.in_use_categories)
        self.n_recycle_categories = len(self.recycling_categories)
        self.n_scenarios = len(self.scenarios)

        self.exog_eaf_USD98 = 76
        self.default_lifetime_sd_pct_of_mean = 0.3
        # ADAPTABLE PARAMETERS

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
        """
        Function to change attributes of config instance. Allows functionality to change
        the config instance all other files are referring to during runtime.

        :param config_dict: A dictionary containing the attribute names as keys and adabted values as values.
        :return:
        """
        name = config_dict['simulation_name']
        for prm_name, prm_value in config_dict.items():
            if prm_name not in self.__dict__:
                raise Exception(f'The custom parameter {prm_name} given in the configuration {name} '
                                'is not registered in the default config definition. '
                                'Maybe you misspelled it or did not add it to the defaults?')
            setattr(self, prm_name, prm_value)
        return self

    def generate_yml(self, filename: str = 'yaml_test.yml'):
        """
        Generates and saves yaml file with current config file settings in
        simulation/interface/yaml folder. Filename is given as parameter,
        if it doesn't have '.yml'/'.yaml' ending, '.yml' is appended.

        :param filename: Name of yaml file, with or without '.yml'/'.yaml' ending.
        :return:
        """
        filename = f'{filename}.yml' if filename[-4:] not in ['.yml', 'yaml'] else filename
        filepath = join('simulation', 'interface', 'yaml', filename)
        with open(filepath, 'w') as f:
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
            return [self.inflow_change_by_category] * len(self.in_use_categories)

    def _inflow_change_scenario_list(self):
        if isinstance(self.inflow_change_by_scenario, list):
            return self.inflow_change_by_scenario
        else:
            return [self.inflow_change_by_scenario] * len(self.scenarios)

    @property
    def inflow_change_factor(self) -> np.ndarray:
        return np.einsum('g,s->gs',
                         1 + np.array(self._inflow_change_category_list()),
                         1 + np.array(self._inflow_change_scenario_list()))

    def _reuse_change_category_list(self) -> list:
        if isinstance(self.reuse_change_by_category, list):
            return self.reuse_change_by_category
        else:
            return [self.reuse_change_by_category] * len(self.in_use_categories)

    def _reuse_change_scenario_list(self) -> list:
        if isinstance(self.reuse_change_by_scenario, list):
            return self.reuse_change_by_scenario
        else:
            return [self.reuse_change_by_scenario] * len(self.scenarios)

    @property
    def reuse_factor(self) -> np.ndarray:
        factor = np.einsum('g,s->gs',
                           1 + np.array(self._reuse_change_category_list()),
                           1 + np.array(self._inflow_change_scenario_list()))
        return np.maximum(1, factor)
        # Reuse factor needs to be at least one, as it is deducted by one later and needs to be positive


cfg = Config()

if __name__ == '__main__':
    cfg.generate_yml()
