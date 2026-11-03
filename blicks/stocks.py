"""The in-use stock: by region and end use, per capita, over GDP, and its extrapolation."""

import functools
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

import blicket as bk
from blicks._helpers import (
    END_USE,
    PERIOD,
    PERIOD_ORDER,
    REGION,
    REGION_SPLIT,
    TIME,
    VALUE,
    WORLD_FIRST,
    by_end_use,
    by_model,
    frame,
    history_and_future,
    in_use_stock,
    last_historical_year,
    per_capita,
    per_capita_with_world,
    with_world,
)

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    from blicketconf import Run
    from remind_mfa.common.common_model import CommonModel

bk.group("stocks", title="In-use stocks")

GDP_PER_CAPITA = "GDP per capita"
SERIES = "Series"
STOCK = "Stock (historical and modelled)"
EXTRAPOLATION = "Pure extrapolation"


@bk.blick(
    title="In-use stock by region",
    unit="t",
    plot=bk.plots.line(x=TIME, y=VALUE, color=REGION, linetype=PERIOD),
    order=PERIOD_ORDER,
)
def in_use_by_region(run: "Run") -> pd.DataFrame:
    """The material in use per region, in t, summed over end uses and the other dimensions; one
    model at a time.

    The historical period is drawn solid, the projection dashed.
    """
    return by_model(run, _in_use_by_region)


def _in_use_by_region(model: "CommonModel") -> pd.DataFrame:
    stock = in_use_stock(model).sum_to(("t", "r"))
    return history_and_future(frame(stock), last_historical_year(model))


@bk.blick(
    title="In-use stock by end use",
    unit="t",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=END_USE),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def in_use_by_end_use(run: "Run") -> pd.DataFrame:
    """The material in use per region and end use, in t, with the world total as a region; one
    model at a time."""
    return by_model(run, lambda model: with_world(by_end_use(model, in_use_stock(model))))


@bk.blick(
    title="In-use stock per capita",
    unit="t per person",
    plot=bk.plots.line(x=TIME, y=VALUE, color=REGION, linetype=PERIOD),
    order=PERIOD_ORDER,
)
def in_use_per_capita(run: "Run") -> pd.DataFrame:
    """The material in use per person and region, in t per person; one model at a time."""
    return by_model(run, _in_use_per_capita)


def _in_use_per_capita(model: "CommonModel") -> pd.DataFrame:
    stock = per_capita(in_use_stock(model).sum_to(("t", "r")), model.future_mfa)
    return history_and_future(frame(stock), last_historical_year(model))


@bk.blick(
    title="In-use stock per capita by end use",
    unit="t per person",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=END_USE),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def in_use_per_capita_by_end_use(run: "Run") -> pd.DataFrame:
    """The material in use per person, region and end use, in t per person; World is the world
    total per world population; one model at a time."""
    return by_model(
        run, lambda model: per_capita_with_world(model, by_end_use(model, in_use_stock(model)))
    )


@bk.blick(
    title="In-use stock per capita over GDP per capita",
    unit="t per person",
    plot=bk.plots.scatter(
        x=GDP_PER_CAPITA, y=VALUE, color=REGION, linetype=PERIOD, along=TIME, x_scale="log"
    ),
    order=PERIOD_ORDER,
)
def in_use_per_capita_over_gdp(run: "Run") -> pd.DataFrame:
    """The material in use per person against GDP per capita, one trajectory per region, as the
    stock extrapolation sees it; GDP per capita on a logarithmic axis; one model at a time."""
    return by_model(run, lambda model: _over_gdp(model, _in_use_per_capita(model)))


@bk.blick(
    title="Stock extrapolation per capita",
    unit="t per person",
    plot=bk.plots.line(x=TIME, y=VALUE, color=SERIES),
    controls=REGION_SPLIT,
    independent_y=True,
)
def extrapolation_per_capita(run: "Run") -> pd.DataFrame:
    """The modelled in-use stock per person against the pure extrapolation from GDP per capita,
    per region; one model at a time.

    The modelled stock blends from the historical stock into the extrapolation; the pure
    extrapolation is the fitted regression alone, scaled by the saturation level.
    """
    return by_model(run, functools.partial(_extrapolation, dims=("t", "r")))


@bk.blick(
    title="Stock extrapolation per capita by end use",
    unit="t per person",
    plot=bk.plots.line(x=TIME, y=VALUE, color=REGION, linetype=SERIES),
    controls={END_USE: "split"},
    independent_y=True,
)
def extrapolation_per_capita_by_end_use(run: "Run") -> pd.DataFrame:
    """The modelled in-use stock per person against the pure extrapolation, per region, one panel
    per end use; one model at a time."""
    return by_model(run, functools.partial(_extrapolation, dims=("t", "r", "u")))


@bk.blick(
    title="Stock extrapolation per capita over GDP per capita",
    unit="t per person",
    plot=bk.plots.scatter(x=GDP_PER_CAPITA, y=VALUE, color=SERIES, along=TIME, x_scale="log"),
    controls=REGION_SPLIT,
    independent_y=True,
)
def extrapolation_per_capita_over_gdp(run: "Run") -> pd.DataFrame:
    """The modelled in-use stock per person and the pure extrapolation against GDP per capita, per
    region; one model at a time."""
    return by_model(run, lambda model: _over_gdp(model, _extrapolation(model, ("t", "r"))))


@bk.blick(
    title="Stock regression function",
    unit="t per person",
    plot=bk.plots.scatter(x=GDP_PER_CAPITA, y=VALUE, color=END_USE, along="Point", x_scale="log"),
    independent_y=True,
)
def regression_function(run: "Run") -> pd.DataFrame:
    """The fitted regression of the in-use stock per person on GDP per capita, per end use, over
    the range of GDP per capita the model covers; one set of fitted parameters per region, after
    the regional adaptation; one model at a time."""
    return by_model(run, _regression_function)


def _regression_function(model: "CommonModel") -> pd.DataFrame:
    from remind_mfa.common.data_transformations import broadcast_trailing_dimensions

    handler = model.stock_handler
    extrapolation = handler.extrapolation
    log_gdppc = np.log10(handler.gdppc.values)
    grid = np.logspace(np.min(log_gdppc), np.max(log_gdppc), model.dims["t"].len)
    gdppc = broadcast_trailing_dimensions(grid, handler.dims_out)
    predictor = handler.get_predictor(gdppc)
    prms = [extrapolation.fit_prms[np.newaxis, ..., i] for i in range(extrapolation.n_prms)]
    values = extrapolation.func(predictor, prms)
    dims = handler.dims_out
    columns = {TIME: "Point"}
    table = frame(_array(dims, values), columns)
    table[GDP_PER_CAPITA] = frame(_array(dims, gdppc), columns)[VALUE]
    table["Point"] = table["Point"].rank(method="dense").astype(int) - 1
    columns_order = [c for c in table.columns if c not in (GDP_PER_CAPITA, VALUE)]
    return table[[*columns_order, GDP_PER_CAPITA, VALUE]]


def _array(dims, values):
    import flodym as fd

    return fd.FlodymArray(dims=dims, values=values)


def _extrapolation(model: "CommonModel", dims: tuple[str, ...]) -> pd.DataFrame:
    """The modelled stock and the pure extrapolation per person, summed to ``dims``, as one table
    with a ``Series`` column."""
    mfa = model.future_mfa
    saturation = model.end_use_specific_sat_level
    stock = per_capita((model.stock_handler.stocks * saturation).sum_to(dims), mfa)
    extrapolation = (model.stock_handler.fitted_regression * saturation).sum_to(dims)
    table = pd.concat(
        {STOCK: frame(stock), EXTRAPOLATION: frame(extrapolation)}, names=[SERIES]
    ).reset_index(level=SERIES)
    return table[[*[c for c in table.columns if c not in (SERIES, VALUE)], SERIES, VALUE]]


def _over_gdp(model: "CommonModel", table: pd.DataFrame) -> pd.DataFrame:
    """``table`` with GDP per capita of its year and region as a measure before ``value``."""
    gdppc = frame(model.future_mfa.parameters["gdppc"]).rename(columns={VALUE: GDP_PER_CAPITA})
    merged = table.merge(gdppc, on=[TIME, REGION], how="left")
    columns = [c for c in merged.columns if c not in (GDP_PER_CAPITA, VALUE)]
    return merged[[*columns, GDP_PER_CAPITA, VALUE]]
