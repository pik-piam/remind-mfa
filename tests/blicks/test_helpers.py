"""Tests of the helpers the Blick modules share."""

from types import SimpleNamespace

import blicket as bk
import flodym as fd
import numpy as np
import pandas as pd
import pytest

from blicks._helpers import (
    END_USE,
    HISTORICAL,
    MODEL,
    PERIOD,
    PROJECTED,
    REGION,
    TIME,
    VALUE,
    WORLD,
    by_end_use,
    by_model,
    frame,
    history_and_future,
    model_of,
    shares,
    with_world,
)

TIME_DIM = fd.Dimension(name="Time", letter="t", items=[2020, 2030])
REGION_DIM = fd.Dimension(name="Region", letter="r", items=["EUR", "USA"])
END_USE_DIM = fd.Dimension(name="End Use", letter="u", items=["Construction", "Machinery"])
EXTENDED_DIM = fd.Dimension(name="Extended End Use", letter="e", items=["Buildings", "Roads"])
DIMS = fd.DimensionSet(dim_list=[TIME_DIM, REGION_DIM, END_USE_DIM])
VALUES = 2.0 ** np.arange(8).reshape(2, 2, 2)


def _array(dims: fd.DimensionSet = DIMS, values: np.ndarray = VALUES) -> fd.FlodymArray:
    return fd.FlodymArray(dims=dims, values=values)


def _run(*names: str) -> SimpleNamespace:
    """A stand-in for a `Run`: the models by name, each knowing its name."""
    return SimpleNamespace(
        models={name: SimpleNamespace(name=name) for name in names}, names=list(names)
    )


def test_frame_is_long_with_value_last():
    table = frame(_array())

    assert list(table.columns) == [TIME, REGION, END_USE, VALUE]
    assert len(table) == 8
    assert table[VALUE].iloc[0] == 1.0


def test_frame_calls_historical_time_time_and_renames_further_dimensions():
    historical = fd.Dimension(name="Historical Time", letter="h", items=[2020])
    array = _array(fd.DimensionSet(dim_list=[historical, EXTENDED_DIM]), np.array([[1.0, 2.0]]))

    table = frame(array, {"Extended End Use": END_USE})

    assert list(table.columns) == [TIME, END_USE, VALUE]


def test_with_world_puts_the_sum_over_regions_first():
    table = with_world(frame(_array().sum_to(("t", "r"))))

    assert table[REGION].iloc[0] == WORLD
    world = table[table[REGION] == WORLD].set_index(TIME)[VALUE]
    assert world[2020] == 1 + 2 + 4 + 8
    assert world[2030] == 16 + 32 + 64 + 128
    assert len(table) == 2 * 3  # two years, World and two regions


def test_with_world_of_a_regional_table_without_other_dimensions():
    table = with_world(frame(_array().sum_to(("r",))))

    assert table[REGION].to_list() == [WORLD, "EUR", "USA"]
    assert table[VALUE].iloc[0] == VALUES.sum()


def test_history_and_future_share_the_last_historical_year():
    table = history_and_future(frame(_array().sum_to(("t", "r"))), last_historical_year=2020)

    historical = table[table[PERIOD] == HISTORICAL]
    projected = table[table[PERIOD] == PROJECTED]
    assert historical[TIME].unique().tolist() == [2020]
    assert projected[TIME].unique().tolist() == [2020, 2030]
    assert list(table.columns) == [TIME, REGION, PERIOD, VALUE]


def test_shares_sum_to_one_and_leave_a_zero_total_null():
    table = frame(_array(values=np.array([[[1.0, 3.0], [0.0, 0.0]], [[2.0, 2.0], [5.0, 0.0]]])))

    result = shares(table, END_USE)

    totals = result.groupby([TIME, REGION])[VALUE].sum()
    assert totals[(2020, "EUR")] == pytest.approx(1.0)
    assert totals[(2030, "USA")] == pytest.approx(1.0)
    assert result[(result[TIME] == 2020) & (result[REGION] == "USA")][VALUE].isna().all()


def test_by_end_use_names_the_end_use_column_whatever_the_model_calls_it():
    cement = SimpleNamespace(name="cement")
    array = _array(fd.DimensionSet(dim_list=[TIME_DIM, REGION_DIM, EXTENDED_DIM]))

    table = by_end_use(cement, array)

    assert list(table.columns) == [TIME, REGION, END_USE, VALUE]
    assert set(table[END_USE]) == {"Buildings", "Roads"}


def test_model_of_picks_the_model_and_skips_runs_without_it():
    run = _run("plastics", "steel")

    assert model_of(run, "steel") is run.models["steel"]
    with pytest.raises(bk.Skip, match="a plastics and steel run; this Blick reads cement runs"):
        model_of(run, "cement")


def test_by_model_stacks_the_tables_with_the_model_first_in_run_order():
    run = _run("plastics", "steel")

    table = by_model(run, lambda model: pd.DataFrame({TIME: [2020], VALUE: [len(model.name)]}))

    assert list(table.columns) == [MODEL, TIME, VALUE]
    assert table[MODEL].to_list() == ["plastics", "steel"]
    assert table[VALUE].to_list() == [8, 5]
    assert isinstance(table[MODEL].dtype, pd.CategoricalDtype)
    assert list(table[MODEL].cat.categories) == ["plastics", "steel"]  # the display order
    assert table[MODEL].cat.ordered


def test_by_model_takes_arrays_and_leaves_out_the_models_that_skip():
    run = _run("plastics", "steel", "cement")

    def build(model):
        if model.name == "steel":
            raise bk.Skip("the steel model has no such thing")
        return _array().sum_to(("t",))

    table = by_model(run, build)

    assert table[MODEL].to_list() == ["plastics", "plastics", "cement", "cement"]
    assert list(table.columns) == [MODEL, TIME, VALUE]


def test_by_model_skips_the_blick_when_every_model_skips():
    run = _run("plastics", "steel")

    def build(model):
        raise bk.Skip(f"nothing for {model.name}")

    with pytest.raises(bk.Skip, match="plastics: nothing for plastics; steel: nothing for steel"):
        by_model(run, build)
