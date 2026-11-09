from pathlib import Path

import pytest

from remind_mfa.common import batch
from remind_mfa.common.config_loader import CONFIG_DIR, load_config
from remind_mfa.common.helpers import ModelNames
from remind_mfa.common.scenarios import ALL_SCENARIOS, list_runnable_scenarios

type RecordedRun = tuple[str, str, bool]


@pytest.fixture
def recorded_runs(monkeypatch) -> list[RecordedRun]:
    """Replace the model run by a recorder of (model, scenario, bundle_export) per run."""
    runs: list[RecordedRun] = []

    def record_run(model_config: dict) -> None:
        (scenario,) = model_config["model_switches"]["scenarios"]
        runs.append((model_config["model"], scenario, model_config["export"]["bundle_export"]))

    monkeypatch.setattr(batch, "run_model", record_run)
    return runs


def configured_run(model: ModelNames) -> RecordedRun:
    """Return the run of a model with the default configuration, as recorded by the fixture."""
    config = load_config(["default"], model)
    (scenario,) = config["model_switches"]["scenarios"]
    return (model.value, scenario, config["export"]["bundle_export"])


def test_no_selection_runs_each_model_once_as_configured(recorded_runs):
    batch.run_batch(["default"], [ModelNames.STEEL, ModelNames.CEMENT])

    assert recorded_runs == [configured_run(ModelNames.STEEL), configured_run(ModelNames.CEMENT)]


def test_all_runs_every_runnable_scenario_per_model(recorded_runs):
    runnable_scenarios = list_runnable_scenarios(CONFIG_DIR / "scenarios")
    assert len(runnable_scenarios) > 1

    batch.run_batch(["default"], [ModelNames.STEEL], [ALL_SCENARIOS], bundle_export=True)

    assert recorded_runs == [("steel", name, True) for name in runnable_scenarios]


def test_selected_scenarios_run_in_order_for_every_model(recorded_runs):
    batch.run_batch(["default"], [ModelNames.STEEL, ModelNames.PLASTICS], ["SSP2", "SSP1", "SSP2"])

    bundle_export = configured_run(ModelNames.STEEL)[2]
    assert recorded_runs == [
        ("steel", "SSP2", bundle_export),
        ("steel", "SSP1", bundle_export),
        ("plastics", "SSP2", bundle_export),
        ("plastics", "SSP1", bundle_export),
    ]


def test_configured_scenarios_run_per_model(recorded_runs, tmp_path: Path):
    layer = tmp_path / "scenarios.toml"
    layer.write_text(
        '[base.model_switches]\nscenarios = ["SSP1", "SSP3"]\n\n'
        '[cement.model_switches]\nscenarios = ["SSP5"]\n',
        encoding="utf-8",
    )
    bundle_export = configured_run(ModelNames.STEEL)[2]

    batch.run_batch(["default", str(layer)], [ModelNames.STEEL, ModelNames.CEMENT])

    assert recorded_runs == [
        ("steel", "SSP1", bundle_export),
        ("steel", "SSP3", bundle_export),
        ("cement", "SSP5", bundle_export),
    ]


def test_selection_overrides_configured_scenarios(recorded_runs, tmp_path: Path):
    layer = tmp_path / "scenarios.toml"
    layer.write_text('[steel.model_switches]\nscenarios = ["SSP1", "SSP3"]\n', encoding="utf-8")

    batch.run_batch(["default", str(layer)], [ModelNames.STEEL], ["SSP4"], bundle_export=False)

    assert recorded_runs == [("steel", "SSP4", False)]


def test_mrindustry_config_runs_bundled_basic_ssp_scenarios(recorded_runs):
    batch.run_batch(["default", "mrindustry"], [ModelNames.STEEL])

    assert recorded_runs == [("steel", f"SSP{number}", True) for number in range(1, 6)]
    assert load_config(["default", "mrindustry"], ModelNames.STEEL)["export"]["prefix"] == "mrindustry"


def test_configuration_files_are_read_once(monkeypatch, recorded_runs):
    load_calls: list[list[str]] = []

    def counting_load_config(config_names, *args, **kwargs):
        load_calls.append(list(config_names))
        return load_config(config_names, *args, **kwargs)

    monkeypatch.setattr(batch, "load_config", counting_load_config)

    batch.run_batch(["default"], list(ModelNames), ["SSP2", "SSP1"])

    assert load_calls == [["default"]]
    assert len(recorded_runs) == 2 * len(ModelNames)
