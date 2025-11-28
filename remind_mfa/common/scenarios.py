import os
import flodym as fd
from pydantic import field_validator, model_validator
from typing import List, Dict, Optional
import yaml
from enum import Enum

from remind_mfa.common.helper import RemindMFAParameterDefinition
from remind_mfa.common.helper import ModelNames, RemindMFABaseModel


class ScenarioReader(RemindMFABaseModel):
    name: str
    base_path: str
    model: ModelNames
    dims: fd.DimensionSet
    parameter_definitions: List[RemindMFAParameterDefinition]
    _scenarios: List["Scenario"] = []
    _parameters: dict = {}

    def get_parameters(self) -> dict:
        self.read_all()
        self.init_flodym_parameters()
        for scenario in self._scenarios:
            scenario.apply(self._parameters)
        return self._parameters

    def init_flodym_parameters(self):
        for param_def in self.parameter_definitions:
            name = param_def.name
            dims = self.dims[param_def.dim_letters]
            self._parameters[name] = fd.Parameter(name=name, dims=dims)

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
        file_name = os.path.join(self.base_path, f"{name}.yml")
        with open(file_name, "r") as f:
            text = yaml.safe_load(f)
        return Scenario(name=name, **text)


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
    type: 'ParameterType'
    index: Dict[str, str] = {}
    value: float

    @field_validator("models", mode="before")
    @classmethod
    def validate_models(cls, value):
        if isinstance(value, str):
            if value == "all":
                return list(ModelNames)
            else:
                return [ModelNames(value)]
        return value

    @model_validator(mode='after')
    def validate_index(self):
        if self.type == ParameterType.PLAIN and self.index:
            raise ValueError("Index should be empty for plain parameters.")
        return self

    def apply(self, parameters: dict):
        if self.type == ParameterType.PLAIN:
            parameters[self.parameter] = self.value
        elif self.type == ParameterType.FLODYM:
            parameter = parameters[self.parameter]
            if self.index:
                parameter[self.index] = self.value
            else:
                parameter[...] = self.value


class ParameterType(str, Enum):
    FLODYM = "flodym"
    PLAIN = "plain"
