import tomllib
from copy import deepcopy
from pathlib import Path

from remind_mfa.common.helpers import ModelNames, get_model_classes

CONFIG_DIR = Path.cwd() / "config"
CONFIG_SECTIONS = {"base", *(model.value for model in ModelNames)}


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


def _validate_config(config: dict, path: Path) -> None:
    """Validate the basic structure of a configuration dictionary."""
    unknown_sections = set(config) - CONFIG_SECTIONS
    if unknown_sections:
        unknown = ", ".join(sorted(unknown_sections))
        raise ValueError(f"Unknown top-level configuration table(s) in {path}: {unknown}.")
    for root, value in config.items():
        if not isinstance(value, dict):
            raise ValueError(f"Top-level configuration key {root!r} in {path} must be a table.")


def _load_config_file(name: str, config_dir: Path = CONFIG_DIR) -> dict:
    path = config_dir / f"{name}.toml"
    if not path.is_file():
        raise FileNotFoundError(f"Configuration {name!r} not found in {config_dir}.")

    with path.open("rb") as stream:
        data = tomllib.load(stream)

    _validate_config(data, path)
    return data


def load_config(
    config_names: list[str],
    model: ModelNames,
    config_dir: Path = CONFIG_DIR,
) -> dict:
    """Load and merge the specified configuration, and return the resulting, validated model configuration."""
    layers = [_load_config_file(name, config_dir) for name in config_names]

    # Merge the base and model-specific configurations from all layers
    base_config: dict = {}
    model_config: dict = {}
    for layer in layers:
        base_config = _deep_merge(base_config, layer.get("base", {}))
        model_config = _deep_merge(model_config, layer.get(model.value, {}))

    # Merge the model-specific configuration into the base configuration
    config = _deep_merge(base_config, model_config)
    config["model"] = model.value
    get_model_classes()[model].ConfigCls.model_validate(config)
    return config
