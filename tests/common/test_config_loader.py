import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from remind_mfa.common.config_loader import CONFIG_DIR, CONFIG_SECTIONS, load_config, merge_config
from remind_mfa.common.helpers import ModelNames


def copy_default_config(destination: Path) -> None:
    shutil.copy(CONFIG_DIR / "default.toml", destination / "default.toml")
    (destination / "scenarios").mkdir()


@pytest.mark.parametrize("model", list(ModelNames))
def test_default_config_validates_for_every_model(model):
    config = load_config(["default"], model)

    assert config["model"] == model.value
    assert config["export"]["path"] == str(Path.cwd() / "data_out")


def test_paths_are_relative_to_root_dir(tmp_path: Path):
    (tmp_path / "data_in").mkdir()
    (tmp_path / "config" / "scenarios").mkdir(parents=True)
    config_path = tmp_path / "custom.toml"
    config_path.write_text(
        '[base.input]\nmadrat_output_path = "madrat_overwrite"\n', encoding="utf-8"
    )

    config = load_config(
        [CONFIG_DIR / "default.toml", config_path], ModelNames.STEEL, root_dir=tmp_path
    )

    assert config["input"]["input_data_path"] == str(tmp_path / "data_in")
    assert config["input"]["scenarios_path"] == str(tmp_path / "config" / "scenarios")
    assert config["input"]["madrat_output_path"] == str(tmp_path / "madrat_overwrite")
    assert config["export"]["path"] == str(tmp_path / "data_out")


def test_absolute_scenarios_path_is_unchanged(tmp_path: Path):
    scenarios_path = tmp_path / "scenarios"
    config_path = tmp_path / "custom.toml"
    config_path.write_text(
        f'[base.input]\nscenarios_path = "{scenarios_path.as_posix()}"\n', encoding="utf-8"
    )
    scenarios_path.mkdir()

    config = load_config([CONFIG_DIR / "default.toml", config_path], ModelNames.STEEL)

    assert config["input"]["scenarios_path"] == str(scenarios_path)


def test_missing_input_path_is_rejected(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="input.input_data_path"):
        load_config([CONFIG_DIR / "default.toml"], ModelNames.STEEL, root_dir=tmp_path)


def test_model_overrides_all_base_layers(tmp_path):
    copy_default_config(tmp_path)
    (tmp_path / "first.toml").write_text(
        '[steel.model_switches]\nscenarios = ["model-first"]\n', encoding="utf-8"
    )
    (tmp_path / "second.toml").write_text(
        '[base.model_switches]\nscenarios = ["base-second"]\n', encoding="utf-8"
    )

    config = load_config(["default", "first", "second"], ModelNames.STEEL, config_dir=tmp_path)

    assert config["model_switches"]["scenarios"] == ["model-first"]


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


def test_overrides_win_over_all_layers(tmp_path):
    copy_default_config(tmp_path)
    (tmp_path / "first.toml").write_text(
        '[base.export]\nprefix = "base-file"\n\n'
        '[steel.model_switches]\nscenarios = ["model-file"]\n',
        encoding="utf-8",
    )
    overrides = {
        "base": {"export": {"prefix": "base-override"}},
        "steel": {"model_switches": {"scenarios": ["model-override"]}},
    }

    tables = load_config(["default", "first"], config_dir=tmp_path)
    config = merge_config(tables, ModelNames.STEEL, overrides=overrides)

    assert config["export"]["prefix"] == "base-override"
    assert config["export"]["bundle_export"] is False
    assert config["model_switches"]["scenarios"] == ["model-override"]


def test_overrides_with_unknown_root_are_rejected():
    with pytest.raises(ValueError, match="Unknown top-level.*overrides"):
        merge_config(load_config(["default"]), ModelNames.STEEL, overrides={"aluminium": {}})


def test_overrides_are_validated():
    overrides = {"steel": {"model_switches": {"misspelled": True}}}

    with pytest.raises(ValueError, match="misspelled"):
        merge_config(load_config(["default"]), ModelNames.STEEL, overrides=overrides)


def test_without_model_returns_tables_in_file_layout():
    tables = load_config(["default"])

    assert set(tables) <= CONFIG_SECTIONS
    assert "model" not in tables
    assert tables["base"]["input"]["input_data_path"] == "data_in"
    assert merge_config(tables, ModelNames.STEEL) == load_config(["default"], ModelNames.STEEL)


def test_merge_config_leaves_tables_unchanged():
    tables = load_config(["default"])
    pristine_tables = deepcopy(tables)
    overrides = {"steel": {"model_switches": {"scenarios": ["override"]}, "export": {"bundle_export": True}}}

    steel_config = merge_config(tables, ModelNames.STEEL, overrides=overrides)
    cement_config = merge_config(tables, ModelNames.CEMENT)

    assert steel_config["model_switches"]["scenarios"] == ["override"]
    assert steel_config["export"]["bundle_export"] is True
    assert cement_config["export"]["bundle_export"] is False
    assert cement_config["export"]["path"] == str(Path.cwd() / "data_out")
    assert tables == pristine_tables
