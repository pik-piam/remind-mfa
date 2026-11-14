"""Batch runs: one or more model runs defined by `[[batch_matrix]]` tables.

One configuration layer may contain an array of `[[batch_matrix]]` tables. Each matrix maps
configuration keys, in the merged structure without `base`/model sections, to lists of values,
and defines the Cartesian product of these values as runs. The key `model` selects the
models. Without matrices, a batch consists of one run per selected model.
"""

import itertools
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from remind_mfa.common.config_loader import MATRIX_SECTION, ConfigStack
from remind_mfa.common.helpers import ModelNames, init_model

type ConfigPath = tuple[str, ...]
"""Path of keys to a value in the merged configuration, e.g. ("model_switches", "scenario")."""

MODEL_PATH: ConfigPath = ("model",)
NAMED_PATHS: frozenset[ConfigPath] = frozenset(
    {MODEL_PATH, ("model_switches", "scenario"), ("input", "region_mapping")}
)
"""Paths whose values are already part of the run folder name."""


def _format_path(path: ConfigPath) -> str:
    return ".".join(path)


def _nested_dict(values: dict[ConfigPath, Any]) -> dict:
    """Turn a mapping of key paths to values into a nested dictionary."""
    nested: dict = {}
    for path, value in values.items():
        table = nested
        for key in path[:-1]:
            table = table.setdefault(key, {})
        table[path[-1]] = value
    return nested


def _get_nested(config: dict, path: ConfigPath) -> Any:
    """Value at the given key path of a nested dictionary, or None if it does not exist."""
    value: Any = config
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


@dataclass(frozen=True)
class BatchMatrix:
    """One `[[batch_matrix]]` table: candidate values per configuration key path."""

    values: dict[ConfigPath, list]
    """Candidate values by key path, in the order of the table."""

    @classmethod
    def from_dict(cls, table: dict, name: str = MATRIX_SECTION) -> "BatchMatrix":
        """Create a matrix from a `[[batch_matrix]]` table.

        Every leaf of the table must be a non-empty list of values.

        Args:
            table: The parsed table.
            name: Name of the table, used in error messages.
        """
        values: dict[ConfigPath, list] = {}

        def collect(table: dict, parent: ConfigPath) -> None:
            for key, value in table.items():
                path = (*parent, key)
                if isinstance(value, dict):
                    collect(value, path)
                elif not isinstance(value, list):
                    raise ValueError(
                        f"{name}.{_format_path(path)} must be a list of values, "
                        f"but got {value!r}."
                    )
                elif not value:
                    raise ValueError(f"{name}.{_format_path(path)} must not be empty.")
                else:
                    values[path] = value

        collect(table, ())
        if not values:
            raise ValueError(f"{name} does not contain any values.")
        if MODEL_PATH in values:
            values[MODEL_PATH] = [ModelNames(model) for model in values[MODEL_PATH]]
        return cls(values=values)

    @property
    def models(self) -> list[ModelNames] | None:
        """Models given in the matrix, or None if the matrix does not define `model`."""
        return self.values.get(MODEL_PATH)

    def combinations(
        self, models: list[ModelNames] | None
    ) -> Iterator[tuple[ModelNames, dict[ConfigPath, Any]]]:
        """Yield all combinations of the matrix values as (model, values by key path).

        Args:
            models: Selected models. Matrices without `model` run these models; matrices with
                `model` are restricted to them. None means no restriction.
        """
        if self.models is None:
            if models is None:
                raise ValueError(
                    f"A [[{MATRIX_SECTION}]] table does not define 'model'; "
                    "select models with --model."
                )
            matrix_models = models
        else:
            matrix_models = [model for model in self.models if models is None or model in models]
        paths = [path for path in self.values if path != MODEL_PATH]
        for model in matrix_models:
            for combination in itertools.product(*(self.values[path] for path in paths)):
                yield model, dict(zip(paths, combination))


@dataclass
class BatchRun:
    """One model run of a batch."""

    model: ModelNames
    config: dict
    """Merged and validated configuration of the run."""
    matrix_values: dict[ConfigPath, Any]
    """Values set by the matrix (empty for runs without matrices)."""

    @property
    def description(self) -> str:
        values = ", ".join(
            f"{_format_path(path)}={value}" for path, value in self.matrix_values.items()
        )
        return f"{self.model.value}" + (f" ({values})" if values else "")

    @property
    def folder_key(self) -> tuple:
        """The parts of the run folder name, apart from a timestamp prefix."""
        export = self.config["export"]
        return (
            export.get("prefix"),
            self.model.value,
            self.config["model_switches"]["scenario"],
            self.config["input"]["region_mapping"],
            export.get("run_suffix"),
        )


class Batch:
    """A list of model runs, created from a configuration stack, which may contain matrices."""

    def __init__(self, runs: list[BatchRun]):
        self.runs = runs

    @staticmethod
    def requires_model_selection(stack: ConfigStack) -> bool:
        """Whether the user must select models, i.e. not every matrix defines `model`."""
        matrices = stack.batch_matrices
        if matrices is None:
            return True
        return any(MODEL_PATH[0] not in matrix for matrix in matrices)

    @classmethod
    def from_stack(cls, stack: ConfigStack, models: list[ModelNames] | None) -> "Batch":
        """Create and validate all runs of a configuration stack.

        Args:
            stack: Configuration layers, at most one of which contains matrices.
            models: Selected models (see `BatchMatrix.combinations`). Required if the stack does
                not contain matrices. None means no restriction.

        Raises:
            ValueError: If no run remains, if a configuration is invalid, or if two runs would
                be written to the same folder.
        """
        raw_matrices = stack.batch_matrices
        if raw_matrices is None:
            if models is None:
                raise ValueError("Select models with --model.")
            return cls([BatchRun(model, stack.resolve(model), {}) for model in models])

        matrices = [
            BatchMatrix.from_dict(matrix, name=f"{MATRIX_SECTION}[{index}]")
            for index, matrix in enumerate(raw_matrices)
        ]
        combinations = [
            (model, values) for matrix in matrices for model, values in matrix.combinations(models)
        ]
        if not combinations:
            raise ValueError("The selected models do not leave any run of the batch.")
        # first pass: effective configurations, from which the varied values are determined
        configs = [stack.resolve(model, _nested_dict(values)) for model, values in combinations]
        suffixes = _folder_suffixes([values for _, values in combinations], configs)
        # second pass: bundle the export and name the run folders
        runs = [
            BatchRun(
                model, stack.resolve(model, _nested_dict(values), _batch_export(suffix)), values
            )
            for (model, values), suffix in zip(combinations, suffixes)
        ]
        cls._check_unique_folders(runs)
        return cls(runs)

    @staticmethod
    def _check_unique_folders(runs: list[BatchRun]) -> None:
        runs_by_folder: dict[tuple, list[BatchRun]] = {}
        for run in runs:
            runs_by_folder.setdefault(run.folder_key, []).append(run)
        duplicates = [runs for runs in runs_by_folder.values() if len(runs) > 1]
        if duplicates:
            listing = "\n".join(" / ".join(run.description for run in runs) for runs in duplicates)
            raise ValueError(f"Several batch runs would be written to the same folder:\n{listing}")

    def run(self) -> None:
        """Run, export and visualize all runs in order."""
        for index, batch_run in enumerate(self.runs, start=1):
            logging.info("=" * 103)
            logging.info(f"Starting run {index}/{len(self.runs)}: {batch_run.description}")
            model = init_model(cfg=batch_run.config)
            logging.info(f"{type(model).__name__} instance created.")
            model.run()
            logging.info("Model computations completed.")
            model.export()
            logging.info("Export completed.")
            model.visualize()
            logging.info("Visualization completed.")


def _batch_export(run_suffix: str | None) -> dict:
    """Override that bundles the export of a batch run and names its folder."""
    return {"export": {"bundle_export": True, "run_suffix": run_suffix}}


def _folder_suffixes(
    matrix_values: list[dict[ConfigPath, Any]], configs: list[dict]
) -> list[str | None]:
    """Run folder suffixes: the values of matrix keys that differ between the runs.

    Keys whose values are part of the folder name anyway (model, scenario, region mapping) are
    left out. Values are compared in the effective configurations, so a key set in one matrix
    only is appended if its value differs from the one the other runs get from the layers.
    """
    paths = dict.fromkeys(
        path for values in matrix_values for path in values if path not in NAMED_PATHS
    )
    varied_paths = [
        path for path in paths if len({repr(_get_nested(config, path)) for config in configs}) > 1
    ]
    return [
        "_".join(_suffix_part(path, _get_nested(config, path)) for path in varied_paths) or None
        for config in configs
    ]


def _suffix_part(path: ConfigPath, value: Any) -> str:
    """Folder name part for a value: strings as they are, other values as `<key>-<value>`."""
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-")
    return text if isinstance(value, str) else f"{path[-1]}-{text}"
