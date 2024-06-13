import os
import numpy as np
from copy import copy
from src.tools.config import cfg


class Dimension(object):

    def __init__(self, name: str, dim_letter: str = None, do_load: bool = False, dtype: type = None, filename: str = None, items: list = None):
        self.name = name
        if dim_letter:
            self.letter = dim_letter
        assert not (do_load and items), "You can't both load and set items"
        if items:
            self.set_items(items)
        if do_load:
            self.load_items(dtype, filename)

    def set_items(self, items: list):
        self.items = items

    def load_items(self, dtype=str, filename: str = None):
        filename = filename if filename else self.name
        path = os.path.join(cfg.data_path, 'input', 'dimensions', f"{filename}.csv")
        data = np.loadtxt(path, dtype=dtype, delimiter=';').tolist()
        data = data if isinstance(data, list) else [data]
        self.set_items(data)

    @property
    def len(self):
        assert self.items, "Items not loaded yet"
        return len(self.items)

    def index(self, item):
        return self.items.index(item)



class DimensionSet(object):

        def __init__(self, defdicts: list=None, dimensions: list=None, do_load: bool = False):
            assert bool(defdicts) != bool(dimensions), "Either defdicts or dimensions must be provided"
            if dimensions is not None:
                self._list = dimensions
            elif defdicts is not None:
                self._list = [Dimension(do_load=do_load, **defdict) for defdict in defdicts]

        @property
        def _dict(self):
            """contains both mappings
            letter --> dim object and
            name --> dim object
            """
            return {dim.name: dim for dim in self._list} | {dim.letter: dim for dim in self._list}

        def __getitem__(self, key):
            return self._dict[key]

        def __iter__(self):
            return iter(self._list)

        def size(self, key: str):
            return self._dict[key].len

        def shape(self, keys: tuple = None):
            keys = keys if keys else self.letters
            return tuple(self.size(key) for key in keys)

        def get_subset(self, dims: list):
            subset = copy(self)
            subset._list = [self._dict[dim_key] for dim_key in dims]
            return subset

        @property
        def names(self):
            return tuple([dim.name for dim in self._list])

        @property
        def letters(self):
            return tuple([dim.letter for dim in self._list])

        @property
        def string(self):
            return "".join(self.letters)

        def index(self, key):
            return [d.letter for d in self._list].index(key)
