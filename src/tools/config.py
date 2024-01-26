from os.path import join
from typing import Any
import yaml
import numpy as np
# from src.read_data.load_data import load_region_mapping, load_pop



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

        # general config
        self.simulation_name = 'SIMSON_Test_1'
        self.try_reload = {
            'setup': True,
            'dsms': True#,
            # 'historic_stocks': True,
            # 'gdp': True
        }
        self.include_gdp_and_pop_scenarios_in_prediction = True

        self.do_show_figs = True
        self.do_save_figs = True

        # data sources
        self.data_path = 'data'
        self.data_sources = {
            'pop': 'UN',  # Options: UN, KC-Lutz (only for scenarios)
            'gdp': 'remind',  # Options: IMF, Koch-Leimbach (only for scenarios)
            'production': 'geyer',  # Options: geyer
            'lifetime': 'geyer',  # Options: geyer
            'regions': 'World',  # Options: REMIND, World, REMIND_EU
            'good_and_element_shares': 'geyer',  # Options: geyer
            'mechanical_recycling_rates': 'dummy',
            'mechanical_recycling_yields': 'dummy'
        }

        self.do_visualize = {
            'stock_prediction': False,
            'future_production': False
        }

        # indices / scope
        self.aspects = ['Time', 'Element', 'Region', 'Good']
        self.index_letters = {'Time': 't',
                              'Element': 'e',
                              'Region': 'r',
                              'Good': 'g'}
        self.start_year = 1950
        self.end_year = 2100
        self.last_historic_year = 2015

        self.elements = sorted(['PE', 'PP', 'PS', 'PVC', 'PET', 'PUR', 'Other'])
        self.in_use_categories = sorted(['Transportation', 'Packaging', 'Building and Construction', 'Other Uses'])
        self.scenario = 'SSP2'

        self.n_elements = len(self.elements)
        self.n_use_categories = len(self.in_use_categories)

        # model customization
        self.curve_strategy = 'Duerrwaechter'  # Options: Duerrwaechter
        self.default_lifetime_sd_pct_of_mean = 0.3

        # Init attributes
        self.data = SetupDataContainer()


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
    def historic_years(self):
        return np.arange(self.start_year, self.last_historic_year + 1)

    @property
    def future_years(self):
        return np.arange(self.last_historic_year + 1, self.end_year + 1)

    @property
    def n_historic_years(self):
        return self.last_historic_year - self.start_year + 1

    @property
    def i_historic(self):
        return np.arange(self.n_historic_years)

    @property
    def i_future(self):
        return np.arange(self.n_historic_years, self.n_years)

    @property
    def n_regions(self):
        return self.data.region_list.shape[0]

    # @property
    # def econ_start_index(self):
    #     return self.econ_base_year - self.start_year + 1

    # def _price_change_list(self):
    #     if isinstance(self.steel_price_change_by_scenario, list):
    #         return self.steel_price_change_by_scenario
    #     else:
    #         return [self.steel_price_change_by_scenario] * len(cfg.scenarios)

    # @property
    # def price_change_factor(self):
    #     return 1 + np.array(self._price_change_list())

    # def _inflow_change_category_list(self):
    #     if isinstance(self.inflow_change_by_category, list):
    #         return self.inflow_change_by_category
    #     else:
    #         return [self.inflow_change_by_category] * len(self.in_use_categories)

    # def _inflow_change_scenario_list(self):
    #     if isinstance(self.inflow_change_by_scenario, list):
    #         return self.inflow_change_by_scenario
    #     else:
    #         return [self.inflow_change_by_scenario] * len(self.scenarios)

    # @property
    # def inflow_change_factor(self) -> np.ndarray:
    #     return np.einsum('g,s->gs',
    #                      1 + np.array(self._inflow_change_category_list()),
    #                      1 + np.array(self._inflow_change_scenario_list()))

    # def _reuse_change_category_list(self) -> list:
    #     if isinstance(self.reuse_change_by_category, list):
    #         return self.reuse_change_by_category
    #     else:
    #         return [self.reuse_change_by_category] * len(self.in_use_categories)

    # def _reuse_change_scenario_list(self) -> list:
    #     if isinstance(self.reuse_change_by_scenario, list):
    #         return self.reuse_change_by_scenario
    #     else:
    #         return [self.reuse_change_by_scenario] * len(self.scenarios)

    # @property
    # def reuse_factor(self) -> np.ndarray:
    #     factor = np.einsum('g,s->gs',
    #                        1 + np.array(self._reuse_change_category_list()),
    #                        1 + np.array(self._inflow_change_scenario_list()))
    #     return np.maximum(1, factor)
    #     # Reuse factor needs to be at least one, as it is deducted by one later and needs to be positive


class SetupDataContainer():

    def __init__(self) -> None:
        self.df_region_mapping = None
        self.region_list = None

        self.df_pop = None
        self.df_pop_countries = None

        # self.df_gdp = None
        # self.df_gdp_countries = None
        # sdc_self.df_gdppc = None

        self.np_pop = None
        self.np_gdp = None

    def __getattribute__(self, __name: str) -> Any:
        # if not loaded, call setup
        attr = super().__getattribute__(__name)
        if attr is None:
            raise Exception("Setup no yet called, call setup() at start of program")
        else:
            return attr


# class SourceConfiguration():

#     def __init__(self, read_func, regions, percapita=False, objtype='pd'):
#         self.read_func  = read_func
#         self.regions    = regions
#         self.percapita  = percapita
#         self.objtype    = objtype


cfg = Config()

# source_config_dict = {}
# loaded_data = {}

if __name__ == '__main__':
    cfg.generate_yml()
