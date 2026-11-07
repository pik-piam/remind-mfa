"""Steel: production by route, and the scrap supply against the statistics."""

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

import blicket as bk
from blicks._helpers import (
    REGION,
    REGION_SPLIT,
    TIME,
    VALUE,
    WORLD,
    WORLD_FIRST,
    frame,
    model_of,
    with_world,
)

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    from blicketconf import Run

bk.group("steel", title="Steel")

ROUTE = "Route"
SERIES = "Series"
STATISTICS = "Scrap consumption (statistics)"


@bk.blick(
    title="Steel production by route",
    unit="t per year",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=ROUTE),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def production_by_route(run: "Run") -> pd.DataFrame:
    """Crude steel production per region and year, from ores (the BOF route) and from scrap (the
    EAF route), with the world total as a region."""
    flows = model_of(run, "steel").future_mfa.flows
    routes = {
        "Ore-based": flows["steel_production_ore_based => forming"],
        "Scrap-based": flows["steel_production_scrap_based => forming"],
    }
    table = pd.concat(
        {route: with_world(frame(flow.sum_to(("t", "r")))) for route, flow in routes.items()},
        names=[ROUTE],
    ).reset_index(level=ROUTE)
    return table[[TIME, REGION, ROUTE, VALUE]]


@bk.blick(
    title="Scrap supply and demand",
    unit="t per year",
    plot=bk.plots.line(x=TIME, y=VALUE, color=SERIES),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def scrap_supply_and_demand(run: "Run") -> pd.DataFrame:
    """The scrap the model supplies to steel production in the historical years against the scrap
    consumption from the statistics, as reported and as reconstructed where the statistics have
    gaps, and the total production the scrap goes into.

    The reported statistics have no world total, since they do not cover every region.
    """
    mfa = model_of(run, "steel").future_mfa
    flows, parameters = mfa.flows, mfa.parameters
    historical = {"t": mfa.dims["h"]}
    supply = (
        flows["scrap_market => scrap_pool"]
        + flows["forming => scrap_pool"]
        + flows["manufacturing => scrap_pool"]
    )[historical]
    production = (
        flows["forming => steel_market"]
        / (parameters["forming_yield"] * (1 - parameters["steel_production_loss_rate"]))
    )[historical]
    reported = frame(parameters["scrap_consumption_no_assumptions"])
    reported[VALUE] = reported[VALUE].replace(0.0, np.nan)
    series = {
        "Model scrap supply": with_world(frame(supply.sum_to(("h", "r")))),
        "Scrap consumption (reconstructed)": with_world(frame(parameters["scrap_consumption"])),
        STATISTICS: with_world(reported),
        "Total production": with_world(frame(production.sum_to(("h", "r")))),
    }
    table = pd.concat(series, names=[SERIES]).reset_index(level=SERIES)
    statistics_world = (table[SERIES] == STATISTICS) & (table[REGION] == WORLD)
    table.loc[statistics_world, VALUE] = np.nan
    return table[[TIME, REGION, SERIES, VALUE]].reset_index(drop=True)
