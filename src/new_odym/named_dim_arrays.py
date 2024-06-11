import os
import numpy as np
from src.tools.config import cfg
import pandas as pd
from src.tools.tools import get_np_from_df
from src.new_odym.dimensions import DimensionSet


class NamedDimArray(object):

    def __init__(self, name: str, dim_letters: tuple):
        """ Basic initialisation of Obj."""
        self.name   = name # object name
        assert type(dim_letters) == tuple, "dim_letters must be a tuple"
        self._dim_letters = dim_letters
        self.dims = None
        self.values = None

    def connect_to_dimensions(self, parent_alldims: DimensionSet):
        self.dims = parent_alldims.get_subset(self._dim_letters) # object name
        self.init_values()

    def init_values(self):
        self.values = np.zeros(self.dims.shape())

    def load_values(self):
        data = self.load_data()
        self.set_values(data)

    def load_data(self):
        path = os.path.join(cfg.data_path, 'transfer', 'data', f"{self.name}.csv")
        data = pd.read_csv(path)
        data = get_np_from_df(data, self.dims.names)
        return data

    def set_values(self, values: np.ndarray):
        assert self.values is not None, "Values not yet initialized"
        assert values.shape == self.values.shape, "Values shape does not match dimensions"
        self.values[...] = values

    def slice_id(self, **kwargs):
        ids_out = [slice(None) for _ in self.dims.letters]
        for dim_letter, item_name in kwargs.items():
            ids_out[self.dims.index(dim_letter)] = self.dims[dim_letter].items.index(item_name)
        return tuple(ids_out)

    def slice(self, **kwargs):
        #TODO: return a new NamedDimTensor instead of just the values
        # BUT make sure that it still fills the original object's values??
        return self.values[self.slice_id(**kwargs)]

    @property
    def shape(self):
        return self.dims.shape()

    def sum(self, sum_over_dims: tuple = (), result_dims: tuple = ()):
        #TODO: return a new NamedDimTensor instead of just the values
        assert not sum_over_dims and result_dims, "You can't simultaneously specify dims to sum over and dims not to sum over"

        if not sum_over_dims and not result_dims:
            return np.sum(self.values)
        elif sum_over_dims:
            result_dims = (o for o in self.dims.letters if o not in sum_over_dims)
        return np.einsum(f"{self.dims.string}->{''.join(result_dims)}", self.values)


class Process():

    def __init__(self, name: str, id: int):
        self.name = name
        self.id = id


class Flow(NamedDimArray):

    def __init__(self, from_process: str, to_process: str, dim_letters: tuple):
        name = f"{from_process} => {to_process}"
        super().__init__(name, dim_letters)
        self._from_process_name = from_process
        self._to_process_name = to_process

    def connect_to_processes(self, processes: dict):
        self.from_process = processes[self._from_process_name]
        self.to_process = processes[self._to_process_name]
        self.from_process_id = self.from_process.id
        self.to_process_id = self.to_process.id

class Stock(NamedDimArray):

    def __init__(self, name: str, process: int, stock_type: int, dim_letters: tuple):
        super().__init__(name, dim_letters)
        self.type = stock_type
        self._process_name = process

    def connect_to_process(self, processes: dict):
        self.process = processes[self._process_name]
        self.process_id = self.process.id


class Parameter(NamedDimArray):
    pass


class DataSetFromCSV(NamedDimArray):

    def __init__(self, name: str, dim_letters: tuple, parent_dims: DimensionSet):
        super().__init__(name, dim_letters)
        self.connect_to_dimensions(parent_dims.get_subset(dim_letters))
        self._data = self.load_data()

    @property
    def array(self):
        return self._data


class ArrayValueOnlyDict():

    def __init__(self, dict):
        self.dict = dict

    def __getitem__(self, name):
        return self.dict[name].values

    def __setitem__(self, name, item):
        self.dict[name].values[...] = item

    def slice(self, name, **kwargs):
        return self.dict[name].slice(**kwargs)
