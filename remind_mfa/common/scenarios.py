import os
import ast
import csv
import flodym as fd
from pydantic import field_validator
from typing import List, Dict, Optional

from remind_mfa.common.common_definition import PlainDataPointDefinition
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.common_definition import RemindMFAParameterDefinition
from remind_mfa.common.helpers import ModelNames, RemindMFABaseModel


class ScenarioReader(RemindMFABaseModel):
    name: str
    base_path: str
    model: ModelNames
    dims: fd.DimensionSet
    parameter_definitions: List[RemindMFAParameterDefinition | PlainDataPointDefinition]
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
            if isinstance(param_def, RemindMFAParameterDefinition):
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
            col[len(index_prefix):]: parsed[col]
            for col in parsed
            if col.startswith(index_prefix) and parsed[col] is not None
        }
        extra_prefix = "extra:"
        extra = {
            col[len(extra_prefix):]: float(parsed[col])
            for col in parsed
            if col.startswith(extra_prefix) and parsed[col] is not None
        }
        return ScenarioDataPoint(
            parameter=parsed["parameter"],
            models=parsed["models"] if parsed["models"] is not None else "all",
            value=float(parsed["value"]),
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
            raise FileNotFoundError(
                f"inheritance.csv not found in {self.base_path}"
            )
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
    index: Dict[str, str] = {}
    value: float
    extra: Dict[str, float] = {}

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
        self.apply_single(parameters, self.parameter, self.value)
        for extra_name, extra_val in self.extra.items():
            self.apply_single(parameters, f"{self.parameter}_{extra_name}", extra_val)

    def apply_single(self, parameters: dict, param_name: str, val: float):
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
