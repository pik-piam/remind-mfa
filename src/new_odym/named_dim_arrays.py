"""
Concepts based on:

ODYM
Copyright (c) 2018 Industrial Ecology
author: Stefan Pauliuk, Uni Freiburg, Germany
https://github.com/IndEcol/ODYM

Re-written for use in simson project
"""

import numpy as np
import pandas as pd
from src.tools.read_data import read_data_to_df
from src.tools.tools import get_np_from_df
from src.new_odym.dimensions import DimensionSet


class NamedDimArray(object):
    """"
    Parent class for an array with pre-defined dimensions, which are addressed by name.
    Operations between different multi-dimensional arrays can than be performed conveniently, as the dimensions are automatically matched.

    In order to 'fix' the dimensions of the array, the array has to be 'declared' by calling the NamedDimArray object constructor with a set of dimensions before working with it.
    Basic mathematical operations between NamedDimArrays are defined, which return a NamedDimArray object as a result.

    In order to set the values of a NamedDimArray object to that of another one, the ellipsis slice ('[...]') can be used, e.g.
    foo[...] = bar.
    This ensures that the dimensionality of the array (foo) is not changed, and that the dimensionality of the right-hand side NamedDimArray (bar) is consistent.
    While the syntaxes like of 'foo = bar + baz' are also possible (where 'bar' and 'baz' are NamedDimArrays), it is not recommended, as it provides no control over the dimensionality of 'foo'.

    The values of the NamedDimArray object are stored in a numpy array, and can be accessed directly via the 'values' attribute.
    So if type(bar) is np.ndarray, the operation
    foo.values[...] = bar
    is also possible.
    It is not recommended to use 'foo.values = bar' without the slice, as this might change the dimensionality of foo.values.

    Slices of arrays can be set or retrieved.
    Here, a slicing dictionary is passed instead of the ellipsis to the square brackets of the MathOperationArrayDict object.
    Each key of the slicing dictionary is the letter of the dimension to be sliced, and each value is the name of the item where the slice is taken.
    For example, if we want to only consider the item 'C' (for carbon) in the element (letter 'e') dimension, the slicing dictionary would be {'e': 'C'}.
    The syntax for setting only the values of a slice of the array is
    foo[{'e': 'C'}] = bar
    and for only retrieving the values of a slice of the array, it is
    foo[...] = bar[{'e': 'C'}]

    The dimensions of a NamedDimArray stored as a DimensionSet object in the 'dims' attribute.
    """

    def __init__(self, name: str = 'unnamed', dim_letters: tuple = None, parent_alldims: DimensionSet = None, values: np.ndarray = None):
        """
        The minimal initialization sets only the name and the dimension letters.
        Optionally,
        - ...dimensions can be set in the form of a DimensionSet object, which is derived as a subset from a parent DimensionSet object.
        - ...values can be initialized directly (usually done for parameters, but not for flows and stocks, which are only computed later)
        """
        self.name   = name # object name
        assert type(dim_letters) == tuple or dim_letters is None, "dim_letters must be a tuple, if given"
        self._dim_letters = dim_letters

        self.dims = None
        self.values = None

        if parent_alldims is not None:
            self.init_dimensions(parent_alldims)
        if values is not None:
            self.set_values(values)

    def init_dimensions(self, parent_alldims: DimensionSet):
        """
        Get a DimensionSet object of the dimensions that the the array is defined over, by selecting the required subset of the parent_alldims.
        After defining the dimensions, the shape of the value array is known and the array can be initialized.
        """
        self.dims = parent_alldims.get_subset(self._dim_letters) # object name
        self.init_values()

    def init_values(self):
        self.values = np.zeros(self.dims.shape())

    def load_values(self):
        data = self.load_data()
        self.set_values(data)

    def load_data(self):
        data = read_data_to_df(type='dataset', name=self.name)
        data = get_np_from_df(data, self.dims.names)
        return data

    def set_values(self, values: np.ndarray):
        assert self.values is not None, "Values not yet initialized"
        assert values.shape == self.values.shape, "Shape of 'values' input array does not match dimensions of NamedDimArray object"
        self.values[...] = values

    def slice_obj(self, slice_dict: dict):
        return NamedDimArraySlice(self, slice_dict)

    @property
    def shape(self):
        return self.dims.shape()

    def sum_values(self):
        return np.sum(self.values)

    def sum_values_over(self, sum_over_dims: tuple = ()):
        result_dims = (o for o in self.dims.letters if o not in sum_over_dims)
        return np.einsum(f"{self.dims.string}->{''.join(result_dims)}", self.values)

    def cast_values_to(self, target_dims: DimensionSet):
        assert all([d in target_dims.letters for d in self.dims.letters]), f"Target of cast must contain all dimensions of the object! Source dims '{self.dims.string}' are not all contained in target dims '{target_dims.string}'. Maybe use sum_values_to() before casting"
        # safety procedure: order dimensions
        values = np.einsum(f"{self.dims.string}->{''.join([d for d in target_dims.letters if d in self.dims.letters])}", self.values)
        index = tuple([slice(None) if d in self.dims.letters else np.newaxis for d in target_dims.letters])
        multiple = tuple([1 if d.letter in self.dims.letters else d.len for d in target_dims])
        values = values[index]
        values = np.tile(values, multiple)
        return values

    def sum_values_to(self, result_dims: tuple = ()):
        return np.einsum(f"{self.dims.string}->{''.join(result_dims)}", self.values)

    def __add__(self, other):
        assert isinstance(other, NamedDimArray), "Can only add two NamedDimArrays"
        dims_out = tuple([d for d in self.dims.letters if d in other.dims.letters])
        return NamedDimArray(dim_letters=dims_out,
                             parent_alldims=self.dims,
                             values=self.sum_values_to(dims_out) + other.sum_values_to(dims_out))

    def __sub__(self, other):
        assert isinstance(other, NamedDimArray), "Can only add two NamedDimArrays"
        dims_out = tuple([d for d in self.dims.letters if d in other.dims.letters])
        return NamedDimArray(dim_letters=dims_out,
                             parent_alldims=self.dims,
                             values=self.sum_values_to(dims_out) - other.sum_values_to(dims_out))

    def __mul__(self, other):
        assert isinstance(other, NamedDimArray), "Can only multiply two NamedDimArrays"
        dims_out = DimensionSet(dimensions=list(set(self.dims).union(set(other.dims))))
        return NamedDimArray(dim_letters=dims_out.letters,
                             parent_alldims=dims_out,
                             values=np.einsum(f"{self.dims.string},{other.dims.string}->{dims_out.string}", self.values, other.values))

    def __truediv__(self, other):
        assert isinstance(other, NamedDimArray), "Can only divide two NamedDimArrays"
        dims_out = DimensionSet(dimensions=list(set(self.dims).union(set(other.dims))))
        return NamedDimArray(dim_letters=dims_out.letters,
                             parent_alldims=dims_out,
                             values=np.einsum(f"{self.dims.string},{other.dims.string}->{dims_out.string}", self.values, 1. / other.values))

    def __getitem__(self, keys):
        """
        Defines what is returned when the object with square brackets stands on the right-hand side of an assignment, e.g. foo = foo = bar[{'e': 'C'}]
        Here, it is solely used for slicing, the the input tot the square brackets must be a dictionary defining the slice.
        """
        assert isinstance(keys, dict), "__getitem__ (square brackets on RHS of assignment) are only implemented for slicing; must provide a slicing dictionary in the square brackets"
        return self.slice_obj(keys).to_nda()

    def __setitem__(self, keys, item):
        """
        Defines what is returned when the object with square brackets stands on the left-hand side of an assignment, e.g. 'foo[...] = bar' or 'foo[{'e': 'C'}] = bar'
        Two ways of using this operator are implemented:
        - If the ellipsis slice is used, the all values of the NamedDimArray object are set to the values of the NamedDimArray object on the right-hand side of the assignment.
          syntax: foo[...] = bar
        - If a slice dictionary is used, only the values of the slice are set to the values of the NamedDimArray object on the right-hand side of the assignment.
          syntax: foo[{'e': 'C'}] = bar

        The RHS is required here to be a NamedDimArray.
        If you want to set the values of a NamedDimArray object directly to a numpy array, use the syntax 'foo.values[...] = bar'.
        """
        assert isinstance(item, NamedDimArray), "Item on RHS of assignment must be a NamedDimArray"
        if isinstance(keys, type(Ellipsis)): # without slice
            self.values[...] = item.sum_values_to(self.dims.letters)
        elif isinstance(keys, dict): # with slice
            slice_obj = self.slice_obj(keys)
            slice_obj.values_pointer[...] = item.sum_values_to(slice_obj.dim_letters)

    def to_df(self):
        index = pd.MultiIndex.from_product([d.items for d in self.dims], names=self.dims.names)
        df = index.to_frame(index=False)
        df['value'] = self.values.flatten()
        return df


class NamedDimArraySlice():
    """
    A slice refers to a subset of the 'values' numpy array of a NamedDimArray object.
    The subset is defined by specifying dimensions along which the array is sliced, and the names of the items of the subset along these dimensions.
    This is done by passing a slice_dict dictionary of the form {'dim_letter': 'item_name'} to the class constructor.
    Instead of a single 'item_name', a list of 'item_names' can be passed.
    Definition examples:
      slice_dict={'e': 'C'} gives you all values where the element is carbon,
      slice_dict={'e': 'C', 'r': ['EUR', 'USA']} gives you all values where the element is carbon and the region is Europe or the USA.

    This class manages returning a pointer to the sliced array and different other associated outputs.
    Note that does not inherit from NamedDimArray, so it is not a NamedDimArray object itself.
    However, one can use it to create a NamedDimArray object with the to_nda() method.
    """

    def __init__(self, named_dim_array: NamedDimArray, slice_dict: dict):
        self.nda = named_dim_array
        self.slice_dict = slice_dict
        self.has_dim_with_several_items = any(isinstance(v, (tuple, list, np.ndarray)) for v in self.slice_dict.values())
        self._init_ids()

    @property
    def ids(self):
        """
        Indices used for slicing the values array
        """
        return tuple(self._id_list)

    @property
    def values_pointer(self):
        """
        Pointer to the subset of the values array of the parent NamedDimArray object.
        """
        return self.nda.values[self.ids]

    @property
    def dim_letters(self):
        """
        Updated dimension letters, where sliced dimensions with only one item along that direction are removed.
        """
        all_letters = self.nda.dims.letters
        # remove the dimensions along which there is only one item
        letters_removed = [d for d, items in self.slice_dict.items() if isinstance(items, str)]
        return tuple([d for d in all_letters if d not in letters_removed])

    def to_nda(self):
        """
        Return a NamedDimArray object that is a slice of the original NamedDimArray object.
        Attention: This creates a new NamedDimArray object, which is not linked to the original one.
        """
        assert not self.has_dim_with_several_items, "Cannot convert to NamedDimArray if there are dimensions with several items"
        return NamedDimArray(dim_letters=self.dim_letters,
                             parent_alldims=self.nda.dims,
                             values=self.values_pointer)

    def _init_ids(self):
        """
        - Init the internal list of index slices to slice(None) (i.e. no slicing, keep all items along that dimension)
        - For each dimension that is sliced, get the corresponding item IDs and set the index slice to these IDs.
        """
        self._id_list = [slice(None) for _ in self.nda.dims.letters]
        for dim_letter, item_or_items in self.slice_dict.items():
            item_ids_singledim = self._get_items_ids(dim_letter, item_or_items)
            self._set_ids_singledim(dim_letter, item_ids_singledim)


    def _get_items_ids(self, dim_letter, item_or_items):
        """
        Given either a single item name or a list of item names, return the corresponding item IDs, along one dimension 'dim_letter'.
        """
        if isinstance(item_or_items, str): # single item
            return self._get_single_item_id(dim_letter, item_or_items)
        elif isinstance(item_or_items, (tuple, list, np.ndarray)): # list of items
            return [self._get_single_item_id(dim_letter, item) for item in item_or_items]

    def _get_single_item_id(self, dim_letter, item_name):
        return self.nda.dims[dim_letter].items.index(item_name)

    def _set_ids_singledim(self, dim_letter, ids):
        self._id_list[self.nda.dims.index(dim_letter)] = ids



class Process():
    """
    Processes serve as nodes for the MFA system layout definition.
    Flows are defined between two processes. Stocks are connected to a process.
    Processes do not contain values themselves.

    Processes get an ID by the order they are defined in  in the MFA system definition.
    The process with ID 0 necessarily contains everything outside the system boundary.
    """

    def __init__(self, name: str, id: int):
        if id == 0:
            assert name == 'sysenv', "The process with ID 0 must be named 'sysenv', as it contains everything outside the system boundary."
        self.name = name
        self.id = id


class Flow(NamedDimArray):
    """
    The values of Flow objects are the main computed outcome of the MFA system.
    A flow connects two processes.
    Its name is set as a combination of the names of the two processes it connects.

    Note that it is a subclass of NamedDimArray, so most of the methods are defined in the NamedDimArray class.
    """

    def __init__(self, from_process: str, to_process: str, dim_letters: tuple):
        """
        Wrapper for the NamedDimArray constructor (without initialization of dimensions and values).
        Important: The flow name is defined here as a combination of the names of the two processes it connects.
        """
        name = f"{from_process} => {to_process}"
        super().__init__(name, dim_letters)
        self._from_process_name = from_process
        self._to_process_name = to_process

    def attach_to_processes(self, processes: dict):
        """
        Store links to the Process objects the Flow connects, and their IDs.
        (To set up the links, the names given in the Flow definition dict are used)
        """
        self.from_process = processes[self._from_process_name]
        self.to_process = processes[self._to_process_name]
        self.from_process_id = self.from_process.id
        self.to_process_id = self.to_process.id


class StockArray(NamedDimArray):
    """
    Stocks allow accumulation of material at a process, i.e. between two flows.
    As Stock contains NamedDimArrays for its stock value, inflow and outflow.
    For details, see the Stock class.
    """
    pass


class Parameter(NamedDimArray):
    """
    Parameters are used for example to define the share of flows that go into one branch when the flow splits at a process.

    All methods are defined in the NamedDimArray parent class.
    """
    pass
