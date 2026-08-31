import shutil
from pathlib import Path

import pytest

from remind_mfa.common.config_loader import CONFIG_DIR, load_config
from remind_mfa.common.helpers import ModelNames


def copy_default_config(destination: Path) -> None:
    shutil.copy(CONFIG_DIR / "default.toml", destination / "default.toml")
    (destination / "scenarios").mkdir()


@pytest.mark.parametrize("model", list(ModelNames))
def test_default_config_validates_for_every_model(model):
    config = load_config(["default"], model)

    assert config["model"] == model.value
    assert config["visualization"]["figures_path"].startswith(f"data/{model.value}/")


def test_scenarios_path_is_relative_to_declaring_config_file(tmp_path: Path):
    config_path = tmp_path / "custom.toml"
    config_path.write_text('[base.input]\nscenarios_path = "scenarios"\n', encoding="utf-8")
    (tmp_path / "scenarios").mkdir()

    config = load_config([CONFIG_DIR / "default.toml", config_path], ModelNames.STEEL)

    assert config["input"]["scenarios_path"] == str(tmp_path / "scenarios")


def test_absolute_scenarios_path_is_unchanged(tmp_path: Path):
    scenarios_path = tmp_path / "scenarios"
    config_path = tmp_path / "custom.toml"
    config_path.write_text(f'[base.input]\nscenarios_path = "{scenarios_path}"\n', encoding="utf-8")
    scenarios_path.mkdir()

    config = load_config([CONFIG_DIR / "default.toml", config_path], ModelNames.STEEL)

    assert config["input"]["scenarios_path"] == str(scenarios_path)


def test_model_overrides_all_base_layers(tmp_path):
    copy_default_config(tmp_path)
    (tmp_path / "first.toml").write_text(
        '[steel.model_switches]\nscenario = "model-first"\n', encoding="utf-8"
    )
    (tmp_path / "second.toml").write_text(
        '[base.model_switches]\nscenario = "base-second"\n', encoding="utf-8"
    )

    config = load_config(["default", "first", "second"], ModelNames.STEEL, config_dir=tmp_path)

    assert config["model_switches"]["scenario"] == "model-first"


def test_later_layers_merge_mappings_and_replace_arrays(tmp_path):
    copy_default_config(tmp_path)
    (tmp_path / "first.toml").write_text(
        """
[steel.visualization]
sankey.plotter_args.exclude_processes = ["first", "shared"]
sankey.plotter_args.slice_dict.r = "EUR"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "second.toml").write_text(
        """
[steel.visualization]
sankey.plotter_args.exclude_processes = ["second"]
sankey.plotter_args.slice_dict.t = 2040
""".strip(),
        encoding="utf-8",
    )

    config = load_config(["default", "first", "second"], ModelNames.STEEL, config_dir=tmp_path)
    plotter_args = config["visualization"]["sankey"]["plotter_args"]

    assert plotter_args["exclude_processes"] == ["second"]
    assert plotter_args["slice_dict"] == {"t": 2040, "r": "EUR"}


def test_missing_config_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        load_config(["missing"], ModelNames.STEEL, config_dir=tmp_path)


def test_unknown_root_is_rejected(tmp_path):
    (tmp_path / "bad.toml").write_text("[aluminium]\nvalue = true\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unknown top-level"):
        load_config(["bad"], ModelNames.STEEL, config_dir=tmp_path)


def test_root_values_must_be_tables(tmp_path):
    (tmp_path / "bad.toml").write_text('base = "not a table"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="must be a table"):
        load_config(["bad"], ModelNames.STEEL, config_dir=tmp_path)


def test_unknown_nested_field_is_rejected(tmp_path):
    (tmp_path / "bad.toml").write_text(
        "[steel.model_switches]\nmisspelled = true\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="misspelled"):
        load_config(["bad"], ModelNames.STEEL, config_dir=tmp_path)
