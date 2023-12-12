import numpy as np
from ODYM.odym.modules.ODYM_Classes import MFAsystem, Flow, Stock


class SimDiGraph_MFAsystem(MFAsystem):
    """
    An adoption of the ODYM MFA system where flows are defined by their start and end processes rather than
    their names. This means no two flows can start AND end at the same processes, but allows for more
    natural processing.
    """

    def init_flow(self, name, from_id, to_id, indices):
        flow = Flow(Name=name, P_Start=from_id, P_End=to_id, Indices=indices, Values=None)
        self.FlowDict['F_' + str(from_id) + '_' + str(to_id)] = flow

    def get_flow(self, from_id: int, to_id: int) -> Flow:
        return self.FlowDict['F_' + str(from_id) + '_' + str(to_id)]

    def get_flowV(self, from_id: int, to_id: int) -> np.ndarray:
        """
        Returns ndarray of flow values to read AND edit.
        :param from_id: Start process of flow.
        :param to_id: End process of flow
        :return:
        """
        return self.get_flow(from_id, to_id).Values

    def add_stock(self, p_id, name, indices, add_change_stock=True):
        name = name + '_stock'
        self.StockDict['S_' + str(p_id)] = Stock(Name=name,
                                                 P_Res=p_id,
                                                 Type=0,
                                                 Indices=indices,
                                                 Values=None)
        if add_change_stock:
            self.StockDict['dS_' + str(p_id)] = Stock(Name=name + "_change",
                                                      P_Res=p_id,
                                                      Type=1,
                                                      Indices=indices, Values=None)

    def get_stockV(self, p_id):
        return self.get_stock(p_id).Values

    def get_stock(self, p_id):
        return self.StockDict['S_' + str(p_id)]

    def get_stock_changeV(self, p_id):
        return self.StockDict['dS_' + str(p_id)].Values

    def calculate_stock_values_from_stock_change(self, p_id):
        stock_values = self.get_stock_changeV(p_id).cumsum(axis=0)
        self.get_stockV(p_id)[:] = stock_values
