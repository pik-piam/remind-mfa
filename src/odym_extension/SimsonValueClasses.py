from ODYM.odym.modules.ODYM_Classes import Process, Parameter, Flow, Stock
from src.read_data.load_data import load_data

class DictVariableCreator():

    def __init__(self, dict):
        self.__dict__['dict'] = dict

    def __getattr__(self, name):
        return self.__dict__['dict'][name].Values

    def __setattr__(self, name, item):
        self.__dict__['dict'][name].Values[...] = item


class FlowDef:
    def __init__(self, start, end, indices):
        self.start = start
        self.end = end
        self.indices = indices

    def to_flow(self, processes):
        name = self.start + "_2_" + self.end
        return name, Flow(Name=name, P_Start=processes.index(self.start), P_End=processes.index(self.end), Indices=self.indices, Values = None)


class PrmDef:
    def __init__(self, name, process, indices, name_to_load = None):
        self.name = name
        self.process = process
        self.indices = indices
        self.name_to_load = name_to_load if name_to_load else name

    def to_prm(self, id, processes):
        return self.name, Parameter(Name=self.name,
                                    ID = id,
                                    P_Res = processes.index(self.process),
                                    MetaData = None,
                                    Indices=self.indices,
                                    Values = load_data(self.name_to_load),
                                    Unit = '1')




