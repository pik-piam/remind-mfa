class DictVariableCreator():

    def __init__(self, dict):
        self.__dict__['dict'] = dict

    def __getattr__(self, name):
        return self.__dict__['dict'][name].Values

    def __setattr__(self, name, item):
        self.__dict__['dict'][name].Values[...] = item





