import os
import numpy as np
import pandas as pd
from copy import copy
from src.tools.config import cfg
from src.tools.tools import get_np_from_df
from src.new_odym.dimensions import DimensionSet


class NamedDimArray(object):

    def __init__(self, name: str, dim_letters: tuple, parent_alldims: DimensionSet = None, values: np.ndarray = None):
        """ Basic initialisation of Obj."""
        self.name   = name # object name
        assert type(dim_letters) == tuple, "dim_letters must be a tuple"
        self._dim_letters = dim_letters

        self.dims = None
        self.values = None

        if parent_alldims is not None:
            self.attach_to_dimensions(parent_alldims)
        if values is not None:
            self.set_values(values)

    def attach_to_dimensions(self, parent_alldims: DimensionSet):
        self.dims = parent_alldims.get_subset(self._dim_letters) # object name
        self.init_values()

    def init_values(self):
        self.values = np.zeros(self.dims.shape())

    def load_values(self):
        data = self.load_data()
        self.set_values(data)

    def load_data(self):
        path = os.path.join(cfg.data_path, 'input', 'datasets', f"{self.name}.csv")
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

    def sum_values(self):
        return np.sum(self.values)

    def sum_values_over(self, sum_over_dims: tuple = ()):
        result_dims = (o for o in self.dims.letters if o not in sum_over_dims)
        return np.einsum(f"{self.dims.string}->{''.join(result_dims)}", self.values)

    def sum_values_to(self, result_dims: tuple = ()):
        return np.einsum(f"{self.dims.string}->{''.join(result_dims)}", self.values)

    def __add__(self, other):
        assert isinstance(other, NamedDimArray), "Can only add NamedDimArrays"
        dims_out = tuple([d for d in self.dims.letters if d in other.dims.letters])
        return NamedDimArray(f"( '{self.name}' + '{other.name}' )",
                             dims_out,
                             parent_alldims=self.dims,
                             values=self.sum_values_to(dims_out) + other.sum_values_to(dims_out))

    def __sub__(self, other):
        assert isinstance(other, NamedDimArray), "Can only add NamedDimArrays"
        dims_out = tuple([d for d in self.dims.letters if d in other.dims.letters])
        return NamedDimArray(f"( '{self.name}' - '{other.name}' )",
                             dims_out,
                             parent_alldims=self.dims,
                             values=self.sum_values_to(dims_out) - other.sum_values_to(dims_out))

    def __mul__(self, other):
        assert isinstance(other, NamedDimArray), "Can only multiply NamedDimArrays"
        dims_out = DimensionSet(dimensions=list(set(self.dims).union(set(other.dims))))
        return NamedDimArray(f"( '{self.name}' * '{other.name}' )",
                             dims_out.letters,
                             parent_alldims=dims_out,
                             values=np.einsum(f"{self.dims.string},{other.dims.string}->{dims_out.string}", self.values, other.values))

    def __truediv__(self, other):
        assert isinstance(other, NamedDimArray), "Can only divide NamedDimArrays"
        dims_out = DimensionSet(dimensions=list(set(self.dims).union(set(other.dims))))
        return NamedDimArray(f"( '{self.name}' / '{other.name}' )",
                             dims_out.letters,
                             parent_alldims=dims_out,
                             values=np.einsum(f"{self.dims.string},{other.dims.string}->{dims_out.string}", self.values, 1. / other.values))

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

    def attach_to_processes(self, processes: dict):
        self.from_process = processes[self._from_process_name]
        self.to_process = processes[self._to_process_name]
        self.from_process_id = self.from_process.id
        self.to_process_id = self.to_process.id

class Stock(NamedDimArray):

    def __init__(self, name: str, process: int, stock_type: int, dim_letters: tuple):
        super().__init__(name, dim_letters)
        self.type = stock_type
        self._process_name = process

    def attach_to_process(self, processes: dict):
        self.process = processes[self._process_name]
        self.process_id = self.process.id

    def cumsum_time(self):
        arr_out = copy(self)
        arr_out.values = np.cumsum(self.values, axis=self.dims.index('t'))
        return arr_out


class Parameter(NamedDimArray):
    pass


class DataSetFromCSV(NamedDimArray):

    def __init__(self, name: str, dim_letters: tuple, parent_dims: DimensionSet):
        super().__init__(name, dim_letters)
        self.attach_to_dimensions(parent_dims.get_subset(dim_letters))
        self._data = self.load_data()

    @property
    def array(self):
        return self._data


class MathOperationArrayDict():

    def __init__(self, input):
        self.verbose = False
        if isinstance(input, dict):
            self._dict = input
        elif isinstance(input, list):
            self._dict = {obj.name: obj for obj in input}

    def __getitem__(self, keys):
        if not isinstance(keys, tuple):
            key = keys
            return self._dict[key]
        else:
            key = keys[0]
            slice_dict = keys[1]
            assert isinstance(slice_dict, dict), "Second argument must be a dictionary"
            dims_out = tuple([d for d in self._dict[key].dims.letters if d not in slice_dict.keys()])
            slice_str = ", ".join([f"{k}={v}" for k, v in slice_dict.items()])
            return NamedDimArray(f"{key}[{slice_str}]",
                                 dim_letters=dims_out,
                                 parent_alldims=self._dict[key].dims,
                                 values=self._dict[key].slice(**slice_dict))

    def __setitem__(self, keys, item):
        assert isinstance(item, NamedDimArray), "Item on RHS of assignment must be a NamedDimArray"
        if not isinstance(keys, tuple):
            key = keys
            if cfg.verbose:
                print(f"Set   '{key}' = '{item.name}'")
            self._dict[key].values[...] = item.sum_values_to(self._dict[key].dims.letters)
        else:
            key = keys[0]
            slice_dict = keys[1]
            assert isinstance(slice_dict, dict), "Second argument must be a dictionary"
            dims_out = tuple([d for d in self._dict[key].dims.letters if d not in slice_dict.keys()])
            slice_str = ", ".join([f"{k}={v}" for k, v in slice_dict.items()])
            if cfg.verbose:
                print(f"Set   '{key}[{slice_str}]' = '{item.name}'")
            self._dict[key].slice(**slice_dict)[...] = item.sum_values_to(dims_out)
