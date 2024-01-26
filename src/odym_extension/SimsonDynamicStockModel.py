import numpy as np
from ODYM.odym.modules.dynamic_stock_model import DynamicStockModel


class SimsonDynamicStockModel(DynamicStockModel):
    # TODO: unfinished - decide whether to implement Multiple dimension possibility

    def compute_all_stock_driven(self):
        self.compute_stock_driven_model()
        self.compute_outflow_total()
        self.compute_stock_change()
        self.check_steel_stock_dsm()

    def compute_all_inflow_driven(self):
        self.compute_s_c_inflow_driven()
        self.compute_o_c_from_s_c()
        self.compute_stock_total()
        self.compute_outflow_total()
        self.check_steel_stock_dsm()

    def check_steel_stock_dsm(self):
        balance = self.check_stock_balance()
        balance = np.abs(balance).sum()
        if balance > 1:  # 1 tonne accuracy
            raise RuntimeError("Stock balance for dynamic stock model is too high: " + str(balance))
        elif balance > 0.001:
            print("Stock balance for model dynamic stock model is noteworthy: " + str(balance))

