from src.tools.config import Config


class Excel_Config(Config):

    def __init__(self):
        super(Excel_Config, self).__init__()
        # ADAPTABLE PARAMS

        self.steel_price_change_all_scenarios = 0
        self.do_change_price_by_scenario = True
        self.steel_price_change_ssp1 = 0.5
        self.steel_price_change_ssp2 = 0.1
        self.steel_price_change_ssp3 = 0.2
        self.steel_price_change_ssp4 = 0
        self.steel_price_change_ssp5 = -0.3

        self.do_change_inflow = True
        self.inflow_change_base_year = 2023

        self.inflow_change_all_scenarios = 0
        self.do_change_inflow_by_scenario = True
        self.inflow_change_ssp1 = -0.2
        self.inflow_change_ssp2 = -0
        self.inflow_change_ssp3 = 0.1
        self.inflow_change_ssp4 = 0.2
        self.inflow_change_ssp5 = 0.3

        self.inflow_change_all_categories = 0
        self.do_change_inflow_by_category = True
        self.inflow_change_transport = -0.2
        self.inflow_change_machinery = 0
        self.inflow_change_construction = 0
        self.inflow_change_products = 0

        self.do_include_reuse = True
        self.reuse_base_year = 2023

        self.reuse_change_all_scenarios = 0
        self.do_change_reuse_by_scenario = True
        self.reuse_change_ssp1 = 0.2
        self.reuse_change_ssp2 = 0.1
        self.reuse_change_ssp3 = 0
        self.reuse_change_ssp4 = 0
        self.reuse_change_ssp5 = 0

        self.reuse_change_all_categories = 0
        self.do_change_reuse_by_category = True
        self.reuse_change_transport = 0
        self.reuse_change_machinery = 0
        self.reuse_change_construction = 0.2
        self.reuse_change_products = 0

    def _price_change_list(self):
        if self.do_change_price_by_scenario:
            return [
                self.steel_price_change_ssp1,
                self.steel_price_change_ssp2,
                self.steel_price_change_ssp3,
                self.steel_price_change_ssp4,
                self.steel_price_change_ssp5
            ]
        else:
            return [self.steel_price_change_all_scenarios]

    def _inflow_change_category_list(self):
        if self.do_change_inflow_by_category:
            return [
                self.inflow_change_transport,
                self.inflow_change_machinery,
                self.inflow_change_construction,
                self.inflow_change_products
            ]
        else:
            return [self.inflow_change_all_categories]

    def _inflow_change_scenario_list(self):
        if self.do_change_inflow_by_scenario:
            return [
                self.inflow_change_ssp1,
                self.inflow_change_ssp2,
                self.inflow_change_ssp3,
                self.inflow_change_ssp4,
                self.inflow_change_ssp5
            ]
        else:
            return [self.inflow_change_all_scenarios]

    def _reuse_change_category_list(self):
        if self.do_change_reuse_by_category:
            return [
                self.reuse_change_transport,
                self.reuse_change_machinery,
                self.reuse_change_construction,
                self.reuse_change_products
            ]
        else:
            return [self.reuse_change_all_categories]

    def _reuse_change_scenario_list(self):
        if self.do_change_reuse_by_scenario:
            return [
                self.reuse_change_ssp1,
                self.reuse_change_ssp2,
                self.reuse_change_ssp3,
                self.reuse_change_ssp4,
                self.reuse_change_ssp5
            ]
        else:
            return [self.reuse_change_all_scenarios]


cfg = Excel_Config()

if __name__ == '__main__':
    cfg.generate_yml()
