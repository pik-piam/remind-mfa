import os
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

        # general config
        self.simulation_name = 'SIMSON_Test_1'

        self.do_show_figs = True
        self.do_save_figs = True

        # data sources
        self.data_path = 'data'

        # model customization
        self.curve_strategy = 'Duerrwaechter'  # Options: Duerrwaechter

        self.do_visualize = {
            'stock_prediction': False,
            'future_production': False,
            'sankey': True
        }

        # indices / scope
        self.aspects = ['Time', 'Element', 'Region', 'Material', 'Good']
        self.index_letters = {'Time': 't',
                              'Element': 'e',
                              'Region': 'r',
                              'Material': 'm',
                              'Good': 'g'}

        self.years = self.load_aspect('years', dtype=int)
        self.n_years = len(self.years)
        self.historic_years= self.load_aspect('historic_years', dtype=int)
        self.n_historic_years = len(self.historic_years)
        self.future_years = [y for y in self.years if y not in self.historic_years]
        self.i_historic = np.arange(self.n_historic_years)
        self.i_future = np.arange(self.n_historic_years, self.n_years)
        self.start_year = self.years[0]
        self.end_year = self.years[-1]

        self.regions = self.load_aspect('regions')
        self.n_regions = len(self.regions)
        self.elements = self.load_aspect('elements')
        self.n_elements = len(self.elements)
        self.materials = self.load_aspect('materials')
        self.n_materials = len(self.materials)
        self.in_use_categories = self.load_aspect('in_use_categories')
        self.n_use_categories = len(self.in_use_categories)

        # TODO: check interaction with self.data and clean up
        self.odym_dimensions = {'Time': 'Time',
                           'Element': 'Element',
                           'Material': 'Material',
                           'Region': 'Region',
                           'Good': 'Material'}

        self.items = {'Time': self.years,
                      'Element': self.elements,
                      'Material': self.materials,
                      'Region': self.regions,
                      'Good': self.in_use_categories}

    def y_id(self, year):
        return self.years.index(year)

    def load_aspect(self, type, dtype=str):
        path = os.path.join(self.data_path, 'transfer', 'aspects', f"{type}.csv")
        data = np.loadtxt(path, dtype=dtype, delimiter=';').tolist()
        data = data if isinstance(data, list) else [data]
        return data


cfg = Config()
