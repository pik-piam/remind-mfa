from pydantic import BaseModel as PydanticBaseModel
from pydantic import model_validator
from typing import Optional, Callable
import numpy as np
from scipy.stats import gmean, hmean
from copy import copy
import sys

from sodym.named_dim_arrays import NamedDimArray

class Trade(PydanticBaseModel):
    """ A TradeModule handles the storing and calculation of trade data for a given MFASystem."""

    imports: NamedDimArray
    exports: NamedDimArray
    balancer: Optional[Callable] = None  # e.g. functions defined in trade_balancers.py

    @model_validator(mode='after')
    def validate_region_dimension(self):
        assert 'r' in self.imports.dims.letters, "Imports must have a Region dimension."
        assert 'r' in self.exports.dims.letters, "Exports must have a Region dimension."

        return self

    @model_validator(mode='after')
    def validate_trade_dimensions(self):
        assert self.imports.dims == self.exports.dims, "Imports and Exports must have the same dimensions."

        return self

    def balance(self, to: str='hmean', inplace=False):
        global_imports = self.imports.sum_nda_over('r')
        global_exports = self.exports.sum_nda_over('r')

        reference_trade = self.get_reference_trade(global_imports, global_exports, to)

        import_factor = reference_trade / global_imports.maximum(sys.float_info.epsilon)
        export_factor = reference_trade / global_exports.maximum(sys.float_info.epsilon)

        new_imports = self.imports * import_factor
        new_exports = self.exports * export_factor

        if not inplace:
            return Trade(imports=new_imports, exports=new_exports)

        self.imports = new_imports
        self.exports = new_exports

        return self

    @staticmethod
    def get_reference_trade(global_imports: NamedDimArray, global_exports: NamedDimArray, to: str='hmean'):
        reference_trade_lookup = {
            'maximum': global_imports.maximum(global_exports),
            'minimum': global_imports.minimum(global_exports),
            'imports': global_imports,
            'exports': global_exports,
            #TODO: document that this is the same method as referenced in Michaja's paper
            'hmean': copy(global_exports).set_values(
                hmean(np.stack([global_imports.values, global_exports.values]))),
            'gmean': copy(global_exports).set_values(
                gmean(np.stack([global_imports.values, global_exports.values]))),
            'amean': (global_imports + global_exports) / 2,
        }
        if to not in reference_trade_lookup:
            raise ValueError(f"Extrenum {to} not recognized. Must be one of {list(reference_trade_lookup.keys())}")
        return reference_trade_lookup[to]

    def __getitem__(self, key):
        if key == 'Imports':
            return self.imports
        elif key == 'Exports':
            return self.exports
        else:
            raise KeyError(f"Key {key} not found in Trade data - has to be either 'Imports' or 'Exports'.")

    def __setitem__(self, key, value):
        if key == 'Imports':
            self.imports = value
        elif key == 'Exports':
            self.exports = value
        else:
            raise KeyError(f"Key {key} has to be either 'Imports' or 'Exports'.")
