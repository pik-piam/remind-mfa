import shutil
from pathlib import Path

import pytest

from remind_mfa.common.batch import Batch, BatchGrid
from remind_mfa.common.config_loader import CONFIG_DIR, ConfigStack, load_config
from remind_mfa.common.helpers import ModelNames


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    shutil.copy(CONFIG_DIR / "default.toml", tmp_path / "default.toml")
    return tmp_path


def write_batch(config_dir: Path, content: str, name: str = "test.batch") -> str:
    (config_dir / f"{name}.toml").write_text(content.strip() + "\n", encoding="utf-8")
    return name


def stack_with(config_dir: Path, content: str) -> ConfigStack:
    return ConfigStack.load(["default", write_batch(config_dir, content)], config_dir)


def batch_from(config_dir: Path, content: str, models: list[ModelNames] | None = None) -> Batch:
    return Batch.from_stack(stack_with(config_dir, content), models)


def test_grid_runs_full_product(config_dir):
    batch = batch_from(
        config_dir,
        """
[[batch_grid]]
model = ["steel", "cement"]
model_switches.scenario = ["SSP1", "SSP2", "SSP3"]
input.region_mapping = ["h12", "iso249"]
""",
    )

    assert len(batch.runs) == 2 * 3 * 2
    keys = {
        (run.model, run.config["model_switches"]["scenario"], run.config["input"]["region_mapping"])
        for run in batch.runs
    }
    assert len(keys) == 12
    assert all(run.config["export"]["bundle_export"] for run in batch.runs)
    assert all(run.config["export"]["run_suffix"] is None for run in batch.runs)


def test_several_grids_are_concatenated(config_dir):
    batch = batch_from(
        config_dir,
        """
[[batch_grid]]
model = ["steel"]
model_switches.scenario = ["SSP1", "SSP2"]

[[batch_grid]]
model = ["cement"]
input.region_mapping = ["iso249"]
""",
    )

    assert [(run.model, run.config["model_switches"]["scenario"]) for run in batch.runs] == [
        (ModelNames.STEEL, "SSP1"),
        (ModelNames.STEEL, "SSP2"),
        (ModelNames.CEMENT, "SSP2"),
    ]
    assert batch.runs[2].config["input"]["region_mapping"] == "iso249"


def test_without_grids_one_run_per_model(config_dir):
    batch = Batch.from_stack(ConfigStack.load(["default"], config_dir), list(ModelNames))

    assert [run.model for run in batch.runs] == list(ModelNames)
    assert all(not run.config["export"]["bundle_export"] for run in batch.runs)


def test_batch_layer_without_grids_is_a_normal_layer(config_dir):
    stack = stack_with(config_dir, '[base.model_switches]\nscenario = "SSP3"')

    assert Batch.requires_model_selection(stack)
    batch = Batch.from_stack(stack, [ModelNames.STEEL])
    assert batch.runs[0].config["model_switches"]["scenario"] == "SSP3"


def test_batch_layer_tables_apply_to_all_runs(config_dir):
    batch = batch_from(
        config_dir,
        """
[base.export]
prefix = "custom"

[[batch_grid]]
model = ["steel", "plastics"]
""",
    )

    assert {run.config["export"]["prefix"] for run in batch.runs} == {"custom"}


def test_model_filter_restricts_grids_with_model(config_dir):
    batch = batch_from(
        config_dir,
        """
[[batch_grid]]
model = ["steel", "cement"]
model_switches.scenario = ["SSP1", "SSP2"]
""",
        models=[ModelNames.CEMENT],
    )

    assert {run.model for run in batch.runs} == {ModelNames.CEMENT}
    assert len(batch.runs) == 2


def test_model_filter_fills_grids_without_model(config_dir):
    content = '[[batch_grid]]\nmodel_switches.scenario = ["SSP1", "SSP2"]'
    stack = stack_with(config_dir, content)

    assert Batch.requires_model_selection(stack)
    batch = Batch.from_stack(stack, [ModelNames.STEEL, ModelNames.PLASTICS])
    assert len(batch.runs) == 4


def test_grid_without_model_requires_models(config_dir):
    with pytest.raises(ValueError, match="does not define 'model'"):
        batch_from(config_dir, '[[batch_grid]]\nmodel_switches.scenario = ["SSP1"]')


def test_model_filter_leaving_no_run_is_rejected(config_dir):
    with pytest.raises(ValueError, match="do not leave any run"):
        batch_from(config_dir, '[[batch_grid]]\nmodel = ["steel"]', models=[ModelNames.CEMENT])


def test_grids_with_models_require_no_selection(config_dir):
    assert not Batch.requires_model_selection(
        stack_with(config_dir, '[[batch_grid]]\nmodel = ["steel"]')
    )


@pytest.mark.parametrize(
    "content, message",
    [
        ('[[batch_grid]]\nmodel = "steel"', "must be a list"),
        ('[[batch_grid]]\nmodel = ["steel"]\nmodel_switches.scenario = []', "must not be empty"),
        ("[[batch_grid]]\nmodel_switches = {}", "does not contain any values"),
        ('[[batch_grid]]\nmodel = ["aluminium"]', "aluminium"),
        ('[[batch_grid]]\nmodel = ["steel"]\nmodel_switches.misspelled = [1]', "misspelled"),
        ('batch_grid = "not a table"', "array of tables"),
    ],
)
def test_invalid_grids_are_rejected(config_dir, content, message):
    with pytest.raises(ValueError, match=message):
        batch_from(config_dir, content)


def test_grid_in_normal_layer_is_rejected(config_dir):
    (config_dir / "plain.toml").write_text('[[batch_grid]]\nmodel = ["steel"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match="only allowed in batch layers"):
        load_config(["default", "plain"], ModelNames.STEEL, config_dir=config_dir)


def test_two_batch_layers_are_rejected(config_dir):
    first = write_batch(config_dir, '[[batch_grid]]\nmodel = ["steel"]', name="first.batch")
    second = write_batch(config_dir, '[[batch_grid]]\nmodel = ["cement"]', name="second.batch")

    with pytest.raises(ValueError, match="At most one batch layer"):
        ConfigStack.load(["default", first, second], config_dir)


def test_varied_values_are_appended_to_folder_name(config_dir):
    batch = batch_from(
        config_dir,
        """
[[batch_grid]]
model = ["steel"]
model_switches.scenario = ["SSP1", "SSP2"]
model_switches.lifetime_model_name = ["LogNormalLifetime", "WeibullLifetime"]
visualization.do_visualize = [false]
""",
    )

    suffixes = [run.config["export"]["run_suffix"] for run in batch.runs]
    assert suffixes == ["LogNormalLifetime", "WeibullLifetime"] * 2


def test_values_differing_only_between_grids_are_appended(config_dir):
    batch = batch_from(
        config_dir,
        """
[[batch_grid]]
model = ["steel"]
visualization.do_visualize = [false]

[[batch_grid]]
model = ["steel"]
visualization.sankey.plotter_args.exclude_processes = [["sysenv", "imports"]]
""",
    )

    assert [run.config["export"]["run_suffix"] for run in batch.runs] == [
        "do_visualize-False_exclude_processes-sysenv-imports-exports",
        "do_visualize-True_exclude_processes-sysenv-imports",
    ]


def test_duplicate_folders_are_rejected(config_dir):
    with pytest.raises(ValueError, match="same folder"):
        batch_from(
            config_dir,
            """
[[batch_grid]]
model = ["steel"]
model_switches.scenario = ["SSP1"]

[[batch_grid]]
model = ["steel"]
model_switches.scenario = ["SSP1", "SSP2"]
""",
        )


def test_input_cfgs_are_distinct(config_dir):
    batch = batch_from(
        config_dir,
        """
[[batch_grid]]
model = ["steel", "cement"]
model_switches.scenario = ["SSP1", "SSP2"]
input.region_mapping = ["h12", "iso249"]
""",
    )

    assert sorted(cfg.region_mapping for cfg in batch.input_cfgs()) == ["h12", "iso249"]


def test_grid_from_dict_flattens_nested_tables():
    grid = BatchGrid.from_dict(
        {"model": ["steel"], "visualization": {"sankey": {"do_visualize": [True, False]}}}
    )

    assert grid.models == [ModelNames.STEEL]
    assert grid.values[("visualization", "sankey", "do_visualize")] == [True, False]
