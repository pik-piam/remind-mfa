"""Tests of the blicket loader and dataset in `blicketconf.py`."""

import pickle
from pathlib import Path
from types import SimpleNamespace

import blicket as bk
import flodym as fd
import numpy as np
import pytest

from blicketconf import Run, dataset, load_run, read_model
from remind_mfa.common.common_model import CommonModel
from remind_mfa.common.helpers import ModelNames
from remind_mfa.common.trade import Trade, TradeSet

TIME = fd.Dimension(name="Time", letter="t", items=[2020, 2030, 2040])
HISTORICAL_TIME = fd.Dimension(name="Historical Time", letter="h", items=[2020, 2030])
REGION = fd.Dimension(name="Region", letter="r", items=["EUR", "USA"])
END_USE = fd.Dimension(name="End Use", letter="u", items=["Construction", "Machinery"])

# 1, 2, 4, 8, ... so that every partial sum identifies its summands
VALUES = 2.0 ** np.arange(12).reshape(3, 2, 2)


class _FakeMFA:
    """Minimal stand-in for a `CommonMFASystem`, exposing only what the dataset reads."""

    def __init__(self, time: fd.Dimension, end_use: fd.Dimension, with_trade: bool = True):
        self.dims = fd.DimensionSet(dim_list=[TIME, HISTORICAL_TIME, REGION, end_use])
        dims = fd.DimensionSet(dim_list=[time, REGION, end_use])
        values = VALUES[: time.len]
        array = fd.FlodymArray(dims=dims, values=values, name="demand")
        self.flows = {"fabrication => use": array}
        self.stocks = {"use": SimpleNamespace(stock=array, inflow=array, outflow=None)}
        self.parameters = {
            "population": fd.FlodymArray(
                dims=fd.DimensionSet(dim_list=[time, REGION]), values=values.sum(axis=2)
            ),
            "collection_rate": fd.FlodymArray(
                dims=fd.DimensionSet(dim_list=[REGION]), values=np.array([0.5, 0.7])
            ),
            "scalar": fd.FlodymArray(dims=fd.DimensionSet(dim_list=[]), values=np.array(1.0)),
        }
        regional = fd.DimensionSet(dim_list=[time, REGION])
        self.trade_set = (
            TradeSet(
                markets={
                    "steel": Trade(
                        name="steel",
                        imports=fd.FlodymArray(dims=regional, values=values.sum(axis=2)),
                        exports=fd.FlodymArray(dims=regional, values=values.sum(axis=2) / 2),
                    )
                }
            )
            if with_trade
            else None
        )


class _FakeModel(CommonModel):
    """Minimal stand-in for a pickled model: a `CommonModel` without reading any data."""

    def __init__(
        self,
        name: str = "steel",
        scenario: str = "SSP2",
        region_mapping: str = "h12",
        end_use: fd.Dimension = END_USE,
    ):
        self.cfg = SimpleNamespace(
            model=ModelNames(name),
            model_switches=SimpleNamespace(scenario=scenario),
            input=SimpleNamespace(region_mapping=region_mapping),
        )
        self.future_mfa = _FakeMFA(TIME, end_use)
        self.historical_mfa = _FakeMFA(HISTORICAL_TIME, end_use, with_trade=False)
        self.dims = self.future_mfa.dims


def _write_run(folder: Path, name: str = "steel", **settings) -> Path:
    folder.mkdir(parents=True)
    path = folder / "model.pickle"
    with path.open("wb") as file:
        pickle.dump(_FakeModel(name, **settings), file)
    return path


def _selection(*paths: Path) -> bk.RunSelection:
    return bk.RunSelection(paths=paths)


def test_load_run_reads_the_pickle_of_a_run_folder(tmp_path: Path):
    folder = tmp_path / "2026-11-02--10-00-00_steel_SSP2_h12"
    path = _write_run(folder)

    run, info = load_run(_selection(folder))

    assert isinstance(run, Run)
    assert run.names == ["steel"]
    assert isinstance(run.models["steel"], CommonModel)
    assert run.scenario == "SSP2"
    assert run.region_mapping == "h12"
    assert info.id == folder.name
    assert info.profile == "steel_SSP2_h12"
    assert info.fingerprint == bk.fingerprint(path)
    assert info.commit is None


def test_load_run_takes_the_pickle_path_too(tmp_path: Path):
    folder = tmp_path / "ci_plastics_SSP2_h12"
    path = _write_run(folder, "plastics")

    _, info = load_run(_selection(path))

    assert info.id == folder.name
    assert info.profile == "plastics_SSP2_h12"


def test_load_run_collects_the_run_folders_of_a_series_folder(tmp_path: Path):
    series = tmp_path / "ci_series"
    cement = _write_run(series / "ci_cement_SSP2_h12", "cement")
    plastics = _write_run(series / "ci_plastics_SSP2_h12", "plastics")

    run, info = load_run(_selection(series))

    assert run.names == ["plastics", "cement"]  # the order of ModelNames, not of the folders
    assert len(run) == 2
    assert [model.name for model in run] == ["plastics", "cement"]
    assert info.id == "ci_series"
    assert info.profile == "plastics-cement_SSP2_h12"
    assert info.fingerprint == bk.fingerprint(cement, plastics)


def test_load_run_collects_several_run_folders(tmp_path: Path):
    steel = tmp_path / "test_steel_SSP2_h12"
    cement = tmp_path / "test_cement_SSP2_h12"
    _write_run(steel)
    _write_run(cement, "cement")

    run, info = load_run(_selection(cement, steel))

    assert run.names == ["steel", "cement"]
    assert info.id == "test_cement_SSP2_h12 + test_steel_SSP2_h12"
    assert info.profile == "steel-cement_SSP2_h12"


def test_load_run_rejects_the_same_model_twice(tmp_path: Path):
    first = tmp_path / "a_steel_SSP2_h12"
    second = tmp_path / "b_steel_SSP2_h12"
    _write_run(first)
    _write_run(second)

    with pytest.raises(ValueError, match="both hold the steel model"):
        load_run(_selection(first, second))


def test_load_run_rejects_models_of_different_scenarios(tmp_path: Path):
    steel = tmp_path / "test_steel_SSP2_h12"
    cement = tmp_path / "test_cement_SSP1_h12"
    _write_run(steel)
    _write_run(cement, "cement", scenario="SSP1")

    with pytest.raises(ValueError, match="different scenarios or region mappings"):
        load_run(_selection(steel, cement))


def test_load_run_rejects_a_folder_without_a_pickle(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="model.pickle"):
        load_run(_selection(tmp_path))


def test_read_model_rejects_other_pickles(tmp_path: Path):
    path = tmp_path / "model.pickle"
    with path.open("wb") as file:
        pickle.dump({"flows": {}}, file)

    with pytest.raises(RuntimeError, match="does not hold a REMIND-MFA model"):
        read_model(path)


@pytest.fixture
def frames() -> bk.Frames:
    return dataset(Run({"steel": _FakeModel()}))


def test_dataset_lists_flows_stocks_trade_and_parameters_per_model(frames: bk.Frames):
    names = [quantity.name for quantity in frames.quantities()]

    assert "steel/flows/fabrication => use" in names
    assert {"steel/stocks/use/stock", "steel/stocks/use/inflow"} <= set(names)
    assert "steel/stocks/use/outflow" not in names  # the stock has none
    assert {
        "steel/trade/steel/imports",
        "steel/trade/steel/exports",
        "steel/trade/steel/net_imports",
    } <= set(names)
    assert {"steel/parameters/population", "steel/parameters/collection_rate"} <= set(names)
    assert "steel/parameters/scalar" not in names  # no dimension, nothing to chart
    assert "steel/historical/flows/fabrication => use" in names
    assert "steel/historical/stocks/use/stock" in names
    assert not any("/historical/parameters" in name for name in names)


def test_dataset_describes_the_quantities(frames: bk.Frames):
    quantities = {quantity.name: quantity for quantity in frames.quantities()}

    flow = quantities["steel/flows/fabrication => use"]
    assert flow.unit == "t per year"
    assert flow.dimensions == ("Time", "Region", "End Use")
    assert flow.additive
    assert flow.group == "steel flows"
    assert quantities["steel/stocks/use/stock"].unit == "t"
    rate = quantities["steel/parameters/collection_rate"]
    assert rate.unit == "fraction"
    assert not rate.additive
    assert rate.group == "steel parameters"
    assert quantities["steel/parameters/population"].unit == "people"
    # the historical system counts its years on Time as well, so both share a chart
    historical = quantities["steel/historical/flows/fabrication => use"]
    assert historical.dimensions == flow.dimensions
    assert historical.group == "steel flows (historical)"


def test_dataset_declares_the_dimensions_in_model_order(frames: bk.Frames):
    dimensions = {dimension.name: dimension for dimension in frames.dimensions()}

    assert list(dimensions) == ["Time", "Region", "End Use"]
    assert dimensions["Time"].dtype == "integer"
    assert dimensions["Time"].values == [2020, 2030, 2040]  # Historical Time's years are among
    assert dimensions["Region"].dtype == "string"
    assert dimensions["Region"].values == ["EUR", "USA"]


def test_dataset_of_several_models_unites_the_values_of_a_dimension():
    plastics_end_use = fd.Dimension(name="End Use", letter="u", items=["Packaging", "Machinery"])
    run = Run({"plastics": _FakeModel("plastics", end_use=plastics_end_use), "steel": _FakeModel()})

    frames = dataset(run)

    dimensions = {dimension.name: dimension for dimension in frames.dimensions()}
    assert dimensions["End Use"].values == ["Packaging", "Machinery", "Construction"]
    names = [quantity.name for quantity in frames.quantities()]
    assert "plastics/flows/fabrication => use" in names
    assert "steel/flows/fabrication => use" in names


def test_dataset_selects_and_sums(frames: bk.Frames):
    table = frames.select("steel/flows/fabrication => use", ["Time", "Region"], {"Region": ["EUR"]})

    assert table.columns == ["Time", "Region", "value"]
    assert table["Time"].to_list() == [2020, 2030, 2040]
    # EUR is the first region: the sum of its two end uses per year
    assert table["value"].to_list() == [1.0 + 2.0, 16.0 + 32.0, 256.0 + 512.0]

    historical = frames.select("steel/historical/flows/fabrication => use", ["Time"], {})
    assert historical["Time"].to_list() == [2020, 2030]
