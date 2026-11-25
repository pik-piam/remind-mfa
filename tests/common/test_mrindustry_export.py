"""Tests for the versioned mrindustry export and the metadata of every export."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import flodym as fd
import numpy as np
import pytest

from remind_mfa.common import helpers
from remind_mfa.common.code_version import CodeVersion
from remind_mfa.common.common_export import CommonDataExporter, RemindInputVariable
from remind_mfa.common.common_mappings import CommonDisplayNames
from remind_mfa.common.common_model import CommonModel
from remind_mfa.common.config_loader import load_config
from remind_mfa.common.helpers import ModelNames, get_model_class

SHA = "0123456789abcdef0123456789abcdef01234567"
VERSION = CodeVersion(remind_mfa_version="1.0.1", git_sha=SHA)
VERSION_FOLDER = "1.0.1-01234567"
DIMS = fd.DimensionSet(
    dim_list=[
        fd.Dimension(name="Time", letter="t", items=[2020, 2021]),
        fd.Dimension(name="Region", letter="r", items=["EUR", "USA"]),
    ]
)


class Exporter(CommonDataExporter):
    """Exporter of a single REMIND input variable."""

    def get_mrindustry_variables(self) -> list[RemindInputVariable]:
        array = fd.FlodymArray(dims=DIMS, values=np.array([[1.0, 2.0], [3.0, 4.0]]))
        return [RemindInputVariable(name="flow", calculation_function=lambda _: array, unit="t/yr")]


@pytest.fixture(autouse=True)
def fixed_code_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the exports independent of the state of this checkout and of earlier tests."""
    monkeypatch.setattr(CodeVersion, "detect", lambda: VERSION)
    monkeypatch.setattr(helpers, "_BATCH_EXPORT_PATH", None)


def make_run(
    export_path: Path,
    model: ModelNames = ModelNames.STEEL,
    scenario: str = "SSP2",
    export_mrindustry: bool = True,
) -> tuple[Exporter, CommonModel]:
    """Exporter and computed model stand-in of a run with the mrindustry configuration.

    Args:
        export_path: Base folder of the export.
        model: Model of the run.
        scenario: Scenario of the run.
        export_mrindustry: Whether the run writes the mrindustry export.
    """
    config = load_config(["default", "mrindustry"], model)
    config["model_switches"]["scenario"] = scenario
    config["export"] |= {"path": str(export_path), "pickle": {"do_export": False}}
    config["export"]["mrindustry"]["do_export"] = export_mrindustry
    cfg = get_model_class(model).ConfigCls(**config)
    exporter = Exporter(cfg=cfg.export, display_names=CommonDisplayNames())
    run = SimpleNamespace(cfg=cfg, name=model.value, future_mfa=None)
    return exporter, cast(CommonModel, run)


def metadata_path(exporter: Exporter) -> Path:
    """Metadata file in the version folder of a run."""
    return Path(exporter.run_path()).parent / "metadata.json"


def test_export_is_written_into_a_version_folder(tmp_path: Path):
    exporter, run = make_run(tmp_path)

    exporter.export(run)

    run_folder = "steel_SSP2_iso249"
    files = (path for path in tmp_path.rglob("*") if path.is_file())
    assert sorted(path.relative_to(tmp_path).as_posix() for path in files) == [
        f"mrindustry_batch/{VERSION_FOLDER}/metadata.json",
        f"mrindustry_batch/{VERSION_FOLDER}/{run_folder}/flow.csv",
    ]
    csv_path = tmp_path / "mrindustry_batch" / VERSION_FOLDER / run_folder / "flow.csv"
    assert csv_path.read_text(encoding="utf-8").splitlines() == [
        "Time,Region,flow",
        "2020,EUR,1.0",
        "2020,USA,2.0",
        "2021,EUR,3.0",
        "2021,USA,4.0",
    ]


def test_metadata_describes_code_and_input_data(tmp_path: Path):
    exporter, run = make_run(tmp_path, model=ModelNames.CEMENT, scenario="SSP1")

    exporter.export(run)

    metadata = json.loads(metadata_path(exporter).read_text(encoding="utf-8"))
    assert metadata.pop("created").endswith("+00:00")
    assert metadata == {
        "remind_mfa_version": "1.0.1",
        "git_sha": SHA,
        "input_data_revision": run.cfg.input.input_data_revision,
    }


def test_models_and_scenarios_share_the_version_folder(tmp_path: Path):
    runs = [
        make_run(tmp_path, model=ModelNames.STEEL, scenario="SSP2"),
        make_run(tmp_path, model=ModelNames.CEMENT, scenario="SSP2"),
        make_run(tmp_path, model=ModelNames.PLASTICS, scenario="SSP1"),
    ]

    for exporter, run in runs:
        exporter.export(run)

    (version_folder,) = (tmp_path / "mrindustry_batch").iterdir()
    assert sorted(path.name for path in version_folder.iterdir()) == [
        "cement_SSP2_iso249",
        "metadata.json",
        "plastics_SSP1_eu21",
        "steel_SSP2_iso249",
    ]


def test_export_without_git_records_unknown_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    without_git = CodeVersion(remind_mfa_version="1.0.1")
    monkeypatch.setattr(CodeVersion, "detect", lambda: without_git)
    exporter, run = make_run(tmp_path)

    exporter.export(run)

    metadata = json.loads(metadata_path(exporter).read_text(encoding="utf-8"))
    assert metadata["git_sha"] == "unknown"
    assert metadata_path(exporter).parent.name == "1.0.1-unknown"


@pytest.mark.parametrize(
    ("bundle_export", "metadata_file"),
    [
        (True, "mrindustry_batch/metadata.json"),
        (False, "mrindustry_steel_SSP2_iso249/metadata.json"),
    ],
    ids=["bundled", "not bundled"],
)
def test_export_without_mrindustry_writes_metadata_without_version_folder(
    tmp_path: Path, bundle_export: bool, metadata_file: str
):
    exporter, run = make_run(tmp_path, export_mrindustry=False)
    exporter.cfg.bundle_export = bundle_export

    exporter.export(run)

    files = [path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.*")]
    assert files == [metadata_file]
    assert json.loads((tmp_path / metadata_file).read_text(encoding="utf-8"))["git_sha"] == SHA
