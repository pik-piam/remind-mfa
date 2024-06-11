class Config:

    def __init__(self):

        # general config
        self.simulation_name = 'SIMSON_Test_1'

        self.do_show_figs = True
        self.do_save_figs = True

        # data sources
        self.data_path = 'data'

        # model customization
        self.curve_strategy = 'GDP_regression'

        self.do_visualize = {
            'stock_prediction': False,
            'future_production': False,
            'sankey': True
        }

        self.model_class = 'plastics'

cfg = Config()
