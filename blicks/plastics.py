"""Plastics: production, trade and the flows by polymer, the polymer splits, the scenario rates
and the material shares of historical trade."""

import functools
from typing import TYPE_CHECKING

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
    frame,
    history_and_future,
    last_historical_year,
    model_of,
    per_capita_with_world,
    shares,
    with_world,
)

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    import flodym as fd

    from blicketconf import Run
    from remind_mfa.common.common_model import CommonModel

bk.group("plastics", title="Plastics")

POLYMER = "Polymer"
FLOW = "Flow"
PARAMETER = "Parameter"

RATES = (
    "collection_rate",
    "landfill_rate",
    "mechanical_recycling_rate",
    "chemical_recycling_rate",
    "bio_production_rate",
    "daccu_production_rate",
)

FLOWS_BY_POLYMER = (
    ("primary_production", "Primary production", "polymerization => primary_market"),
    ("primary_demand", "Primary plastics demand", "primary_market => manufacturing"),
    ("manufacturing", "Manufacturing", "manufacturing => manufactured_products_market"),
    ("demand", "Demand", "manufactured_products_market => use"),
    ("mechanically_recycled", "Mechanically recycled", "reclmech => aux_recyclate_market"),
    ("collected", "Collected", "eol_management => sorting"),
    ("sorted_to_mechanical_recycling", "Sorted to mechanical recycling", "sorting => reclmech"),
    ("landfilled", "Landfilled", "sorting => landfill"),
    ("incinerated", "Incinerated", "sorting => incineration"),
)
"""The flows with a polymer dimension shown by polymer: the id segment, the title and the flow."""

POLYMER_MARKETS = (
    ("primary", "Primary plastics"),
    ("manufactured_products", "Manufactured products"),
    ("waste", "Plastic waste"),
    ("aux_recyclate", "Recyclate"),
)
"""The markets that resolve polymers, whose trade is shown by polymer: the market and its title."""


def _plastics(run: "Run") -> "CommonModel":
    """The plastics model of the run; a run without one is skipped."""
    return model_of(run, "plastics")


def _production_sources(mfa: "fd.MFASystem") -> dict[str, "fd.FlodymArray"]:
    """Primary and mechanically recycled polymers reaching the primary market."""
    return {
        "Primary": mfa.flows["polymerization => primary_market"],
        "Recycled": mfa.flows["aux_recyclate_market => primary_market"],
    }


def _by_label(
    arrays: dict[str, "fd.FlodymArray"], label: str, dims=("t", "r"), world: bool = True
) -> pd.DataFrame:
    """The arrays summed to ``dims``, in one table with a column ``label`` naming each, World
    first unless ``world`` is off."""
    tables = {name: frame(array.sum_to(dims)) for name, array in arrays.items()}
    if world:
        tables = {name: with_world(table) for name, table in tables.items()}
    table = pd.concat(tables, names=[label]).reset_index(level=label)
    columns = [column for column in table.columns if column not in (label, VALUE)]
    return table[[*columns, label, VALUE]].reset_index(drop=True)


@bk.blick(
    title="Production by polymer",
    unit="t per year",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=POLYMER),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def production_by_polymer(run: "Run") -> pd.DataFrame:
    """Production per region and polymer, newly polymerized and mechanically recycled together,
    with the world total as a region."""
    sources = _production_sources(_plastics(run).future_mfa)
    production = sources["Primary"] + sources["Recycled"]
    return with_world(frame(production.sum_to(("t", "r", "p"))))


@bk.blick(
    title="Production by source",
    unit="t per year",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=FLOW),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def production_by_source(run: "Run") -> pd.DataFrame:
    """Production per region, newly polymerized (primary) or mechanically recycled, with the world
    total as a region."""
    return _by_label(_production_sources(_plastics(run).future_mfa), FLOW)


@bk.blick(
    title="Production, net imports and consumption",
    unit="t per year",
    plot=bk.plots.line(x=TIME, y=VALUE, color=FLOW),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def production_trade_consumption(run: "Run") -> pd.DataFrame:
    """Production, net imports and consumption per region, with the world total as a region.

    Production is primary and mechanically recycled; net imports, imports minus exports and so
    negative for net exporters, are of primary plastics and of manufactured products; consumption
    is the plastics entering use.
    """
    return _by_label(_production_trade_consumption(_plastics(run).future_mfa), FLOW)


@bk.blick(
    title="Production, net imports and consumption per capita",
    unit="t per person per year",
    plot=bk.plots.line(x=TIME, y=VALUE, color=FLOW),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def production_trade_consumption_per_capita(run: "Run") -> pd.DataFrame:
    """Production, net imports and consumption per person and region; World is the world total
    per world population."""
    plastics = _plastics(run)
    table = _by_label(_production_trade_consumption(plastics.future_mfa), FLOW, world=False)
    return per_capita_with_world(plastics, table)


def _production_trade_consumption(mfa: "fd.MFASystem") -> dict[str, "fd.FlodymArray"]:
    flows = mfa.flows
    sources = _production_sources(mfa)
    return {
        "Production": sources["Primary"] + sources["Recycled"],
        "Primary net imports": (
            flows["imports => primary_market"] - flows["primary_market => exports"]
        ),
        "Manufactured products net imports": (
            flows["imports => manufactured_products_market"]
            - flows["manufactured_products_market => exports"]
        ),
        "Consumption": mfa.stocks["use"].inflow,
    }


def _flow_by_polymer(name: str, run: "Run") -> pd.DataFrame:
    """The flow ``name`` per region, polymer and year, with the world total as a region."""
    flow = _plastics(run).future_mfa.flows[name]
    return with_world(frame(flow.sum_to(("t", "r", "p"))))


for _segment, _title, _flow in FLOWS_BY_POLYMER:
    bk.register(
        id=f"plastics/{_segment}_by_polymer",
        title=f"{_title} by polymer",
        description=(
            f"The flow {_flow} per region, polymer and year, with the world total as a region."
        ),
        unit="t per year",
        plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=POLYMER),
        controls=REGION_SPLIT,
        independent_y=True,
        order=WORLD_FIRST,
        transform=functools.partial(_flow_by_polymer, _flow),
    )


@bk.blick(
    title="Chemically recycled",
    unit="t per year",
    plot=bk.plots.line(x=TIME, y=VALUE, linetype=PERIOD),
    controls=REGION_SPLIT,
    independent_y=True,
    order={**PERIOD_ORDER, **WORLD_FIRST},
)
def chemically_recycled(run: "Run") -> pd.DataFrame:
    """Plastics chemically recycled into feedstock per region and year, with the world total as a
    region."""
    plastics = _plastics(run)
    flow = plastics.future_mfa.flows["reclchem => aux_recl_feedstock_market"]
    table = with_world(frame(flow.sum_to(("t", "r"))))
    return history_and_future(table, last_historical_year(plastics))


@bk.blick(
    title="Polymer splits",
    unit="fraction",
    plot=bk.plots.stacked_bar(x=REGION, y=VALUE, color=POLYMER),
    controls={END_USE: "split"},
)
def polymer_splits(run: "Run") -> "fd.FlodymArray":
    """Each polymer's share of the plastics entering use, per region and end use, in the last
    historical year, which the scenario holds constant afterwards; the shares sum to one over the
    polymers."""
    plastics = _plastics(run)
    parameter = plastics.future_mfa.parameters["polymer_shares_use_inflow"]
    return parameter[{"t": last_historical_year(plastics)}]


@bk.blick(
    title="Scenario rates",
    unit="fraction",
    plot=bk.plots.line(x=TIME, y=VALUE, color=REGION),
    independent_y=True,
    defaults={PARAMETER: "collection_rate"},  # Parameter is a filter: one rate at a time
)
def scenario_rates(run: "Run") -> pd.DataFrame:
    """Six rates the scenario sets per region and year, one at a time.

    Collection is the share of end-of-life plastics collected; landfill, mechanical recycling and
    chemical recycling are shares of the collected waste; the bio-based and DACCU rates are the
    shares of primary high-value chemicals production made from biomass and from carbon captured
    from the air.
    """
    parameters = _plastics(run).future_mfa.parameters
    table = pd.concat(
        {name: frame(parameters[name]) for name in RATES}, names=[PARAMETER]
    ).reset_index(level=PARAMETER)
    return table.reset_index(drop=True)


def _trade_by_polymer(market_name: str, run: "Run") -> pd.DataFrame:
    """Imports and exports of the market ``market_name`` per region, polymer and year, with the
    world total as a region."""
    market = _plastics(run).future_mfa.trade_set.markets[market_name]
    parts = [
        with_world(frame(array.sum_to(("t", "r", "p")))).assign(**{FLOW: flow})
        for flow, array in (("Imports", market.imports), ("Exports", market.exports))
    ]
    table = pd.concat(parts, ignore_index=True)
    return table[[FLOW, TIME, REGION, POLYMER, VALUE]]


for _market, _title in POLYMER_MARKETS:
    bk.register(
        id=f"plastics/trade_{_market}_by_polymer",
        title=f"{_title} trade by polymer",
        description=(
            f"Imports or exports of the market {_market} per region, polymer and year, one flow "
            "at a time, with the world total as a region."
        ),
        unit="t per year",
        plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=POLYMER),
        controls=REGION_SPLIT,
        independent_y=True,
        defaults={FLOW: "Imports"},
        order={FLOW: ["Imports", "Exports"], **WORLD_FIRST},
        transform=functools.partial(_trade_by_polymer, _market),
    )


@bk.blick(
    title="Material shares of historical primary trade",
    unit="fraction",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color="Polymer Type"),
    controls=REGION_SPLIT,
    defaults={FLOW: "Exports"},
    order={FLOW: ["Imports", "Exports"], **WORLD_FIRST},
)
def historical_trade_material_shares(run: "Run") -> pd.DataFrame:
    """Each polymer type's share of the historical primary plastics trade per region and year,
    imports or exports, with the world total as a region.

    Whether the shares are constant over time tells whether a time-independent split could stand
    in for the time-resolved trade data.
    """
    market = _plastics(run).historical_mfa.trade_set.markets["primary"]
    parts = []
    for flow, array in (("Imports", market.imports), ("Exports", market.exports)):
        table = with_world(frame(array.sum_to(("h", "r", "P"))))
        parts.append(shares(table, "Polymer Type").assign(**{FLOW: flow}))
    table = pd.concat(parts, ignore_index=True)
    return table[[FLOW, TIME, REGION, "Polymer Type", VALUE]]
