"""Cement: clinker production, construction output and the carbon uptake of carbonation."""

from typing import TYPE_CHECKING

import pandas as pd

import blicket as bk
from blicks._helpers import (
    PERIOD,
    PERIOD_ORDER,
    REGION_SPLIT,
    TIME,
    VALUE,
    WORLD_FIRST,
    frame,
    history_and_future,
    last_historical_year,
    model_of,
    with_world,
)

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    from blicketconf import Run

bk.group("cement", title="Cement")


@bk.blick(
    title="Clinker production",
    unit="t per year",
    plot=bk.plots.line(x=TIME, y=VALUE, linetype=PERIOD),
    controls=REGION_SPLIT,
    independent_y=True,
    order={**PERIOD_ORDER, **WORLD_FIRST},
)
def clinker_production(run: "Run") -> pd.DataFrame:
    """Clinker production per region and year, before trade, losses included, with the world
    total as a region."""
    cement = model_of(run, "cement")
    flows = cement.future_mfa.flows
    production = (
        flows["clinker_production => clinker_market"] + flows["clinker_production => losses"]
    )
    table = with_world(frame(production.sum_to(("t", "r"))))
    return history_and_future(table, last_historical_year(cement))


@bk.blick(
    title="Construction output",
    unit="t per year",
    plot=bk.plots.line(x=TIME, y=VALUE, linetype=PERIOD),
    controls=REGION_SPLIT,
    independent_y=True,
    order={**PERIOD_ORDER, **WORLD_FIRST},
)
def construction_output(run: "Run") -> pd.DataFrame:
    """The construction materials entering use per region and year, all constituents, with the
    world total as a region."""
    cement = model_of(run, "cement")
    flow = cement.future_mfa.flows["construction => use"]
    table = with_world(frame(flow.sum_to(("t", "r"))))
    return history_and_future(table, last_historical_year(cement))


@bk.blick(
    title="Consumption by construction material",
    unit="t per year",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color="Construction Material"),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def consumption_by_construction_material(run: "Run") -> pd.DataFrame:
    """Cement entering construction per region, construction material and year, with the world
    total as a region."""
    flow = model_of(run, "cement").future_mfa.flows["cement_market => construction"]
    return with_world(frame(flow.sum_to(("t", "r", "m"))))


@bk.blick(
    title="CO2 uptake from carbonation",
    unit="t CO2 per year",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color="Carbonation Location"),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def carbonation(run: "Run") -> pd.DataFrame:
    """The CO2 the cement stock takes up per year, region and carbonation location, with the world
    total as a region; only in runs with the carbonation module."""
    cement = model_of(run, "cement")
    if not cement.cfg.model_switches.carbonation:
        raise bk.Skip("the run has the carbonation module switched off")
    uptake = cement.future_mfa.stocks["carbonated_co2"].inflow
    return with_world(frame(uptake.sum_to(("t", "r", "l"))))
