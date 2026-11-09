import logging
import tomllib
from copy import deepcopy
from dataclasses import dataclass
from functools import reduce
from pathlib import Path

from remind_mfa.common.helpers import ModelNames, get_model_class

CONFIG_DIR = Path.cwd() / "config"
CONFIG_SECTIONS = {"base", *(model.value for model in ModelNames)}
GRID_SECTION = "batch_grid"
BATCH_SUFFIX = ".batch"
"""Suffix of the file stem of batch layers, i.e. layers that may contain `[[batch_grid]]` tables."""


def get_config_paths(config_dir: Path = CONFIG_DIR) -> list[Path]:
    """Return a list of all TOML configuration files in the given directory."""
    return sorted(config_dir.glob("*.toml"))


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge mappings, with `override` taking precedence over `base`."""

    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def is_batch_layer(name: str | Path) -> bool:
    """Whether a configuration name or path refers to a batch layer (`<name>.batch.toml`)."""
    file_name = Path(name).name
    return file_name.endswith(BATCH_SUFFIX) or file_name.endswith(f"{BATCH_SUFFIX}.toml")


def _check_batch_layers(config_names: list[str | Path]) -> None:
    """Raise an error if more than one batch layer is given."""
    batch_layers = [str(name) for name in config_names if is_batch_layer(name)]
    if len(batch_layers) > 1:
        raise ValueError(
            f"At most one batch layer (*{BATCH_SUFFIX}.toml) may be given, "
            f"but got {', '.join(batch_layers)}."
        )


def _validate_config(config: dict, path: Path) -> None:
    """Validate the basic structure of a configuration dictionary.

    Batch layers (`<name>.batch.toml`) may additionally contain an array of `[[batch_grid]]` tables.
    """
    allowed_sections = CONFIG_SECTIONS | ({GRID_SECTION} if is_batch_layer(path) else set())
    unknown_sections = set(config) - allowed_sections
    if GRID_SECTION in unknown_sections:
        raise ValueError(
            f"[[{GRID_SECTION}]] tables in {path} are only allowed in batch layers, "
            f"i.e. files named <name>{BATCH_SUFFIX}.toml."
        )
    if unknown_sections:
        unknown = ", ".join(sorted(unknown_sections))
        raise ValueError(f"Unknown top-level configuration table(s) in {path}: {unknown}.")
    for root, value in config.items():
        if root == GRID_SECTION:
            if not isinstance(value, list) or not all(isinstance(grid, dict) for grid in value):
                raise ValueError(
                    f"{GRID_SECTION!r} in {path} must be an array of tables ([[{GRID_SECTION}]])."
                )
        elif not isinstance(value, dict):
            raise ValueError(f"Top-level configuration key {root!r} in {path} must be a table.")


def _resolve_paths(config: dict, root_dir: Path) -> None:
    """Resolve all relative paths in the configuration against the given root directory."""
    CONFIG_PATHS = [
        ("input", "input_data_path", True),
        ("input", "scenarios_path", True),
        ("input", "madrat_output_path", False),
        ("export", "path", False),
    ]
    for section_name, key, must_exist in CONFIG_PATHS:
        section = config.get(section_name)
        if not section or section.get(key) is None:
            continue
        path = _resolve_relative_path(section[key], root_dir)
        if must_exist and not path.exists():
            raise FileNotFoundError(
                f"Path {path} for {section_name}.{key} does not exist (resolved against {root_dir})."
            )
        section[key] = str(path)


def _resolve_relative_path(path: str, root_dir: Path) -> Path:
    """Resolve a relative path against the given root directory."""
    resolved_path = Path(path)
    if not resolved_path.is_absolute():
        resolved_path = root_dir / resolved_path
    return resolved_path.resolve()


@dataclass(frozen=True)
class ConfigLayer:
    """One parsed and checked configuration file."""

    path: Path
    data: dict

    @classmethod
    def load(cls, name: str | Path, config_dir: Path = CONFIG_DIR) -> "ConfigLayer":
        """Load a TOML configuration file and check its structure.

        Args:
            name: Path to a file, or stem (without the .toml extension) of a file in `config_dir`.
            config_dir: Directory in which names are looked up.
        """
        path = Path(name)
        if not path.is_file():
            path = config_dir / f"{name}.toml"
            if not path.is_file():
                raise FileNotFoundError(f"Configuration {name!r} not found in {config_dir}.")
        logging.info(f"Loading configuration from {path}.")

        with path.open("rb") as stream:
            data = tomllib.load(stream)

        _validate_config(data, path)
        return cls(path=path, data=data)

    def section(self, name: str) -> dict:
        """The given top-level table, or an empty one if the file does not contain it."""
        return self.data.get(name, {})


class ConfigStack:
    """An ordered stack of configuration layers, at most one of which is a batch layer.

    The configuration of a model is the merge of an ordered list of sections, all with the
    structure of the final configuration, with later sections taking precedence:

        base(layer 1) ... base(layer n) < model(layer 1) ... model(layer n) < overrides

    Overrides are used by batch runs to apply the values of one `[[batch_grid]]` combination.
    """

    def __init__(self, layers: list[ConfigLayer], root_dir: Path | None = None):
        """Create a stack from loaded layers.

        Args:
            layers: The configuration layers in merge order.
            root_dir: Directory against which relative paths are resolved (default: current
                working directory).
        """
        _check_batch_layers([layer.path for layer in layers])
        self.layers = layers
        self.root_dir = root_dir if root_dir is not None else Path.cwd()

    @classmethod
    def load(
        cls,
        config_names: list[str | Path],
        config_dir: Path = CONFIG_DIR,
        root_dir: Path | None = None,
    ) -> "ConfigStack":
        """Load the given configuration layers, as names in `config_dir` or paths, in merge order."""
        _check_batch_layers(config_names)
        return cls([ConfigLayer.load(name, config_dir) for name in config_names], root_dir)

    @property
    def batch_grids(self) -> list[dict] | None:
        """The raw `[[batch_grid]]` tables of the batch layer, or None if there are none."""
        grids = [grid for layer in self.layers for grid in layer.data.get(GRID_SECTION, [])]
        return grids or None

    def sections(self, model: ModelNames | None) -> list[dict]:
        """The sections to merge for the given model, in merge order."""
        sections = [layer.section("base") for layer in self.layers]
        if model is not None:
            sections += [layer.section(model.value) for layer in self.layers]
        return sections

    def resolve(self, model: ModelNames | None, *overrides: dict) -> dict:
        """Merge the sections of the given model and the overrides, and validate the result.

        Args:
            model: Model whose sections are merged over the base sections. If None, only the base
                sections are used and the result is not validated.
            overrides: Values in the structure of the final configuration, merged in order over
                the sections before path resolution and validation.

        Returns:
            The merged configuration dictionary.
        """
        config = reduce(_deep_merge, [*self.sections(model), *overrides], {})
        _resolve_paths(config, self.root_dir)
        if model is not None:
            config["model"] = model.value
            get_model_class(model).ConfigCls.model_validate(config)
        return config


def load_config(
    config_names: list[str | Path],
    model: ModelNames | None = None,
    config_dir: Path = CONFIG_DIR,
    root_dir: Path | None = None,
) -> dict:
    """Load and merge the specified configuration, and return the resulting, validated model configuration.

    Shorthand for `ConfigStack.load(...).resolve(model)`. Relative paths in the configuration are
    resolved against `root_dir` (default: current working directory). `[[batch_grid]]` tables of
    batch layers are not applied.
    """
    return ConfigStack.load(config_names, config_dir, root_dir).resolve(model)
