import os
import ast
import csv
import numpy as np
import flodym as fd
from pydantic import Field, field_validator, model_validator
from typing import Any, Dict, List, Optional

from remind_mfa.common.common_definition import (
    ExtrapolationDefinition,
    PlainDataPointDefinition,
    RemindMFAParameterDefinition,
)
from remind_mfa.common.helpers import ModelNames, RemindMFABaseModel

# Declares the numpy dtype of each `extra:` column on an extrapolation parameter.
# Strings need a fixed-width dtype: plain `str` would allocate single characters only.
EXTRA_DTYPES = {"year": float, "type": "<U32"}

VALID_TYPES = ("factor", "target")


class ExtrapolationScenarioParameter(RemindMFABaseModel):
    """Scenario values and metadata for one parameter extrapolation.

    The value array has dtype object: entries are either numbers or strings naming a
    model parameter that supplies the endpoint at the entry's coordinates. No
    arithmetic may operate on it; the extrapolator resolves it to floats first.
    """

    definition: ExtrapolationDefinition
    value: fd.Parameter
    is_set: Optional[fd.Parameter] = None
    """0/1 mask marking coordinates where a scenario row has set a value; distinguishes
    an explicit 0 from an untouched entry."""
    extras: Dict[str, fd.Parameter] = Field(default_factory=dict)

    @model_validator(mode="after")
    def init_is_set(self):
        if self.is_set is None:
            self.is_set = fd.Parameter(name=f"{self.definition.name}_is_set", dims=self.value.dims)
        return self

    @model_validator(mode="after")
    def check_split_balancing_item(self):
        if self.definition.split_balancing_item is None:
            return self
        split_dim = self.value.dims[self.definition.split_dimension_letter]
        if self.definition.split_balancing_item not in split_dim.items:
            raise ValueError(
                f"Unknown split_balancing_item '{self.definition.split_balancing_item}' for "
                f"'{self.definition.name}': not an item of dimension '{split_dim.name}'."
            )
        return self

    def set_value(self, value: float | str, index: Dict[str, Any]):
        if value is None:
            raise ValueError(f"Scenario row for '{self.definition.name}' has an empty value.")
        self._check_index(index)
        self._set(self.value, value, index)
        self._set(self.is_set, 1.0, index)

    def set_extra(self, name: str, value: float | str, index: Dict[str, Any]):
        self._check_index(index)
        if name not in self.extras:
            self.extras[name] = self._new_extra(name)
        self._set(self.extras[name], value, index)

    def _new_extra(self, name: str) -> fd.Parameter:
        """Allocate the array backing an extra, with the dtype declared in EXTRA_DTYPES."""
        dtype = EXTRA_DTYPES.get(name, float)
        values = np.zeros(self.value.dims.shape, dtype=dtype)
        return fd.Parameter(
            name=f"{self.definition.name}_{name}", dims=self.value.dims, values=values
        )

    def set_extras(self, extras: Dict[str, Any], index: Dict[str, Any]):
        for name, value in extras.items():
            self.set_extra(name, value, index)

    @staticmethod
    def _set(parameter: fd.Parameter, value: float | str, index: Dict[str, Any]):
        if index:
            parameter[index] = value
        else:
            parameter[...] = value

    def _check_index(self, index: Dict[str, Any]):
        """Check that index keys are valid dimension names and index values are valid items."""
        valid_names = set(self.value.dims.names)
        invalid = [name for name in index if name not in valid_names]
        if invalid:
            raise ValueError(
                f"Scenario row for '{self.definition.name}' indexes dimension(s) {invalid}, "
                f"which are not among its scenario dimensions {sorted(valid_names)}."
            )
        for dim_name, item in index.items():
            dim = self.value.dims[dim_name]
            if item not in dim.items:
                raise ValueError(
                    f"Scenario row for '{self.definition.name}': '{item}' is not a valid "
                    f"item of dimension '{dim_name}'. Valid items: {dim.items}."
                )

    def referenced_parameters(self) -> list:
        """Sorted unique names of model parameters referenced as endpoints in the scenario values."""
        return sorted({v for v in self.value.values.flat if isinstance(v, str)})

    def resolve_type(self) -> str:
        """Single extrapolation type of the parameter, declared via 'extra:type'.

        Rows without 'extra:type' use the type declared by the other rows, so one
        declaration (e.g. in the base scenario) suffices. Mixed types are not
        supported: raises unless exactly one valid type is declared.
        """
        name = self.definition.name
        type_extra = self.extras.get("type")
        declared = type_extra.values[self.is_set.values > 0] if type_extra is not None else []
        types = {str(t) for t in declared if t}
        if not types:
            raise ValueError(
                f"'{name}' has no extrapolation type. Declare it with an 'extra:type' "
                f"column in the scenario CSV; valid types: {VALID_TYPES}."
            )
        if len(types) > 1:
            raise ValueError(
                f"'{name}' declares mixed extrapolation types {sorted(types)}; "
                "only one type per parameter is supported."
            )
        (ext_type,) = types
        if ext_type not in VALID_TYPES:
            raise ValueError(
                f"'{name}' declares an invalid extrapolation type '{ext_type}'. "
                f"Valid types: {VALID_TYPES}."
            )
        return ext_type


class ScenarioReader(RemindMFABaseModel):
    name: str
    base_path: str
    model: ModelNames
    dims: fd.DimensionSet
    parameter_definitions: List[
        ExtrapolationDefinition | RemindMFAParameterDefinition | PlainDataPointDefinition
    ]
    _scenarios: List["Scenario"] = []
    _parameters: dict = {}

    def get_parameters(self) -> dict:
        self.read_all()
        self.init_parameters()
        for scenario in self._scenarios:
            scenario.apply(self._parameters)
        return self._parameters

    def init_parameters(self):
        for param_def in self.parameter_definitions:
            name = param_def.name
            if isinstance(param_def, ExtrapolationDefinition):
                dims = self.dims[param_def.dim_letters]
                # object dtype: entries hold numbers or names of endpoint parameters
                values = np.zeros(dims.shape, dtype=object)
                self._parameters[name] = ExtrapolationScenarioParameter(
                    definition=param_def,
                    value=fd.Parameter(name=name, dims=dims, values=values),
                )
            elif isinstance(param_def, RemindMFAParameterDefinition):
                dims = self.dims[param_def.dim_letters]
                self._parameters[name] = fd.Parameter(name=name, dims=dims)
            elif isinstance(param_def, PlainDataPointDefinition):
                self._parameters[name] = None

    def read_all(self):
        name = self.name
        while True:
            scenario = self.read_single(name)
            scenario.filter_data_by_model(self.model)
            self._scenarios.insert(0, scenario)
            if scenario.parent is None:
                break
            name = scenario.parent

    def read_single(self, name: str) -> "Scenario":
        csv_file = os.path.join(self.base_path, f"{name}.csv")
        if os.path.exists(csv_file):
            return self._read_csv(name, csv_file)
        else:
            raise FileNotFoundError(f"No scenario file found for '{name}' (tried .csv)")

    def _read_csv(self, name: str, file_name: str) -> "Scenario":
        parent = self._read_parent_from_inheritance(name)
        with open(file_name, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(self._iter_active_csv_lines(f))
            data_points = [self._parse_csv_row(row) for row in reader]
        return Scenario(name=name, parent=parent, data=data_points)

    @staticmethod
    def _iter_active_csv_lines(file_obj):
        for line in file_obj:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            yield line

    @staticmethod
    def _parse_csv_row(row: dict) -> "ScenarioDataPoint":
        parsed = {col: ScenarioReader._parse_csv_value(val) for col, val in row.items()}
        index_prefix = "index:"
        index = {
            col[len(index_prefix) :]: parsed[col]
            for col in parsed
            if col.startswith(index_prefix) and parsed[col] is not None
        }
        extra_prefix = "extra:"
        extra = {
            col[len(extra_prefix) :]: parsed[col]
            for col in parsed
            if col.startswith(extra_prefix) and row[col].strip() != ""
        }
        return ScenarioDataPoint(
            parameter=parsed["parameter"],
            models=parsed["models"] if parsed["models"] is not None else "all",
            value=parsed["value"],
            index=index,
            extra=extra,
        )

    @staticmethod
    def _parse_csv_value(val: str):
        val = val.strip() if val else ""
        if val == "":
            return None
        try:
            return ast.literal_eval(val)
        except (ValueError, SyntaxError):
            return val

    def _read_parent_from_inheritance(self, name: str) -> Optional[str]:
        inheritance_file = os.path.join(self.base_path, "inheritance.csv")
        if not os.path.exists(inheritance_file):
            raise FileNotFoundError(f"inheritance.csv not found in {self.base_path}")
        with open(inheritance_file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(self._iter_active_csv_lines(f))
            for row in reader:
                if row["scenario"] == name:
                    parent = row.get("parent", "").strip()
                    return parent if parent else None
        return None


class Scenario(RemindMFABaseModel):
    name: str
    parent: Optional[str] = None
    data: List["ScenarioDataPoint"] = []

    def filter_data_by_model(self, model_name: ModelNames):
        self.data = [p for p in self.data if model_name in p.models]

    def apply(self, parameters: dict):
        for data_point in self.data:
            data_point.apply(parameters)


class ScenarioDataPoint(RemindMFABaseModel):
    parameter: str
    models: List[ModelNames] | str = "all"
    index: Dict[str, Any] = {}
    value: Any
    extra: Dict[str, Any] = {}

    @field_validator("models", mode="before")
    @classmethod
    def validate_models(cls, value):
        if isinstance(value, str):
            if value == "all":
                return list(ModelNames)
            else:
                return [ModelNames(v.strip()) for v in value.split(",")]
        return value

    def apply(self, parameters: dict):
        parameter = parameters.get(self.parameter)
        if isinstance(parameter, ExtrapolationScenarioParameter):
            parameter.set_value(self.value, self.index)
            parameter.set_extras(self.extra, self.index)
            return

        self.apply_single(parameters, self.parameter, self.value)
        for extra_name, extra_val in self.extra.items():
            self.apply_single(parameters, f"{self.parameter}_{extra_name}", extra_val)

    def apply_single(self, parameters: dict, param_name: str, val: float):
        if param_name not in parameters:
            raise ValueError(
                f"Scenario data point refers to undefined scenario parameter '{param_name}'. "
                "Scenario parameters must be declared in the scenario parameter definitions."
            )
        parameter = parameters[param_name]
        if isinstance(parameter, fd.Parameter):
            if self.index:
                parameter[self.index] = val
            else:
                parameter[...] = val
        else:
            if self.index:
                raise ValueError("Index should be empty for plain parameters.")
            parameters[param_name] = val
