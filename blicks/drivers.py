"""The drivers of the models: GDP, population and the scenario factors."""

import functools
from typing import TYPE_CHECKING

import pandas as pd

import blicket as bk
from blicks._helpers import END_USE, REGION, REGION_SPLIT, TIME, VALUE, by_model, frame

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    import flodym as fd

    from blicketconf import Run
    from remind_mfa.common.common_model import CommonModel

bk.group("drivers", title="Drivers and scenario factors")

FACTOR = "Factor"


@bk.blick(
    title="GDP per capita",
    unit="2005 USD PPP per person",
    plot=bk.plots.line(x=TIME, y=VALUE, color=REGION, y_scale="log"),
)
def gdp_per_capita(run: "Run") -> pd.DataFrame:
    """GDP per capita per region, in 2005 USD at purchasing power parity, of the driver scenario
    the models use; one model at a time, since each reads its own copy of the drivers."""
    return by_model(run, lambda model: model.future_mfa.parameters["gdppc"])


@bk.blick(
    title="GDP",
    unit="2005 USD PPP",
    plot=bk.plots.line(x=TIME, y=VALUE, color=REGION, y_scale="log"),
)
def gdp(run: "Run") -> pd.DataFrame:
    """GDP per region, GDP per capita times population; one model at a time."""
    return by_model(run, _gdp)


def _gdp(model: "CommonModel") -> "fd.FlodymArray":
    parameters = model.future_mfa.parameters
    return parameters["gdppc"] * parameters["population"]


@bk.blick(
    title="Population",
    unit="people",
    plot=bk.plots.line(x=TIME, y=VALUE, color=REGION),
)
def population(run: "Run") -> pd.DataFrame:
    """Population per region of the driver scenario the models use; one model at a time."""
    return by_model(run, lambda model: model.future_mfa.parameters["population"])


@bk.blick(
    title="Trade and stock factors",
    unit="factor",
    plot=bk.plots.line(x=TIME, y=VALUE, color=REGION),
    independent_y=True,
    defaults={FACTOR: "trade_factor"},  # Factor is a filter: one factor at a time
)
def scenario_factors(run: "Run") -> pd.DataFrame:
    """The scenario factors on future trade and on the extrapolated stock, per model, region and
    year.

    Both are 1 in the historical years and move towards the scenario's targets afterwards.
    """
    factors = {"trade_factor": "trade_factor", "stock_factor": "stock_factor"}
    return by_model(run, functools.partial(_factors, factors=factors))


@bk.blick(
    title="Lifetime factors",
    unit="factor",
    plot=bk.plots.line(x=TIME, y=VALUE, color=END_USE, linetype=FACTOR),
    controls=REGION_SPLIT,
)
def lifetime_factors(run: "Run") -> pd.DataFrame:
    """The scenario factors on the lifetime of the in-use stock, per model, region, end use and
    year.

    The nature factor extends the lifetime of new age cohorts; the nurture factor extends the
    lifetime of all cohorts in a year.
    """
    factors = {"nature": "lifetime_factor_nature", "nurture": "lifetime_factor_nurture"}
    return by_model(run, functools.partial(_factors, factors=factors))


def _factors(model: "CommonModel", factors: dict[str, str]) -> pd.DataFrame:
    """The parameters ``factors`` (label to parameter name) of the model in one table, the label
    as the dimension ``Factor``."""
    parameters = model.parameters
    table = pd.concat(
        {label: frame(parameters[name]) for label, name in factors.items()}, names=[FACTOR]
    )
    return table.reset_index(level=FACTOR).reset_index(drop=True)
