"""Tests of the batch runner: the run folders it hands to the viewer."""

from pathlib import Path
from types import SimpleNamespace

from remind_mfa.common import batch
from remind_mfa.common.helpers import ModelNames


class _FakeModel:
    """A model that runs and exports nothing but knows its run folder."""

    def __init__(self, name: str, folder: Path, pickle: bool):
        self.name = name
        self.data_writer = SimpleNamespace(
            cfg=SimpleNamespace(do_export=True, pickle=SimpleNamespace(do_export=pickle)),
            run_path=lambda: str(folder),
        )

    def run(self) -> None:
        pass

    def export(self) -> None:
        pass


def test_run_batch_returns_the_run_folders_of_the_models_with_a_pickle(monkeypatch, tmp_path):
    folders = {name: tmp_path / f"test_{name.value}_SSP2_h12" for name in ModelNames}
    pickles = {ModelNames.STEEL: True, ModelNames.CEMENT: True, ModelNames.PLASTICS: False}
    monkeypatch.setattr(batch, "load_config", lambda config_names, model_name: model_name)
    monkeypatch.setattr(
        batch, "init_model", lambda cfg: _FakeModel(cfg.value, folders[cfg], pickles[cfg])
    )

    models = [ModelNames.STEEL, ModelNames.PLASTICS, ModelNames.CEMENT]

    run_paths = batch.run_batch(["default"], models)

    assert run_paths == [folders[ModelNames.STEEL], folders[ModelNames.CEMENT]]
