"""Trade of every market of every model: imports and exports, and net imports."""

from typing import TYPE_CHECKING

import pandas as pd

import blicket as bk
from blicks._helpers import (
    MARKET,
    REGION,
    REGION_SPLIT,
    TIME,
    VALUE,
    WORLD_FIRST,
    frame,
    in_order,
    with_world,
)

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    from blicketconf import Run
    from remind_mfa.common.trade import Trade

bk.group("trade", title="Trade")

FLOW = "Flow"


@bk.blick(
    title="Imports and exports",
    unit="t per year",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=FLOW),
    controls=REGION_SPLIT,
    independent_y=True,
    order={FLOW: ["Imports", "Exports"], **WORLD_FIRST},
)
def imports_and_exports(run: "Run") -> pd.DataFrame:
    """Imports above and exports below the axis, per region and year, one market at a time; the
    markets are named by their model, <model>: <market>, in the models' order of markets.
    World holds the global imports and exports, which trade balancing makes equal."""
    markets = _markets(run)
    parts = []
    for label, market in markets.items():
        labels = {MARKET: label}
        imports = frame(market.imports.sum_to(("t", "r"))).assign(**labels, **{FLOW: "Imports"})
        exports = frame(market.exports.sum_to(("t", "r"))).assign(**labels, **{FLOW: "Exports"})
        exports[VALUE] = -exports[VALUE]
        parts += [with_world(imports), with_world(exports)]
    table = in_order(pd.concat(parts, ignore_index=True), MARKET, list(markets))
    return table[[MARKET, FLOW, TIME, REGION, VALUE]]


@bk.blick(
    title="Net imports",
    unit="t per year",
    plot=bk.plots.line(x=TIME, y=VALUE, color=REGION),
)
def net_imports(run: "Run") -> pd.DataFrame:
    """Imports minus exports per region and year, negative for net exporters, one market at a
    time; the markets are named by their model, <model>: <market>."""
    markets = _markets(run)
    parts = [
        frame(market.net_imports.sum_to(("t", "r"))).assign(**{MARKET: label})
        for label, market in markets.items()
    ]
    table = in_order(pd.concat(parts, ignore_index=True), MARKET, list(markets))
    return table[[MARKET, TIME, REGION, VALUE]]


def _markets(run: "Run") -> dict[str, "Trade"]:
    """The markets of the run's models, labelled ``<model>: <market>``, in the models' order and
    each model's order of markets."""
    return {
        f"{name}: {market_name}": market
        for name, model in run.models.items()
        for market_name, market in model.future_mfa.trade_set.markets.items()
    }
