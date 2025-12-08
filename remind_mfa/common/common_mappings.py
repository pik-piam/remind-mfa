from functools import reduce


class Mapping():

    _own_mapping = {}

    def __init__(self):
        all_bases = self.__class__.__bases__
        dicts = [b._own_mapping for b in all_bases if issubclass(b, Mapping) and b != Mapping]
        self.dct = reduce(lambda a, b: a | b, dicts, {}) | self._own_mapping

    def __getitem__(self, key):
        return self.dct.get(key, key)



class CommonDimensionFiles(Mapping):

    _own_mapping = {
        "Time": "time_in_years",
        "Historic Time": "historic_years",
        "Region": "regions",
    }


class CommonDisplayNames(Mapping):

    _own_mapping = {
        # for markdown export
        "name": "Name",
        "letter": "Letter",
        "dim_letters": "Dimensions",
        "from_process_name": "Origin Process",
        "to_process_name": "Destination Process",
        "process_name": "Process",
        "subclass": "Stock Type",
        "lifetime_model_class": "Lifetime Model",
    }
