"""Material flows common to the models: production, consumption, end-use split, the Sankey
diagram and the IAMC variables."""

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
    WORLD,
    WORLD_FIRST,
    by_end_use,
    by_model,
    consumption,
    frame,
    history_and_future,
    last_historical_year,
    per_capita_with_world,
    production,
    shares,
    with_world,
)

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    from blicketconf import Run
    from remind_mfa.common.common_model import CommonModel

bk.group("flows", title="Material flows")

SANKEY_YEAR_STEP = 5


@bk.blick(
    title="Production",
    unit="t per year",
    plot=bk.plots.line(x=TIME, y=VALUE, linetype=PERIOD),
    controls=REGION_SPLIT,
    independent_y=True,
    order={**PERIOD_ORDER, **WORLD_FIRST},
)
def production_by_region(run: "Run") -> pd.DataFrame:
    """Production per region and year, before trade, with the world total as a region: crude
    steel from both routes, cement, or primary plus mechanically recycled polymers; one model at
    a time."""
    return by_model(run, _production_by_region)


def _production_by_region(model: "CommonModel") -> pd.DataFrame:
    table = with_world(frame(production(model)))
    return history_and_future(table, last_historical_year(model))


@bk.blick(
    title="Consumption by end use",
    unit="t per year",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=END_USE),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def consumption_by_end_use(run: "Run") -> pd.DataFrame:
    """The material entering use per region, end use and year, with the world total as a region;
    one model at a time."""
    return by_model(run, lambda model: with_world(by_end_use(model, consumption(model))))


@bk.blick(
    title="Consumption per capita by end use",
    unit="t per person per year",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=END_USE),
    controls=REGION_SPLIT,
    independent_y=True,
    order=WORLD_FIRST,
)
def consumption_per_capita_by_end_use(run: "Run") -> pd.DataFrame:
    """The material entering use per person, region, end use and year; World is the world total
    per world population; one model at a time."""
    return by_model(
        run, lambda model: per_capita_with_world(model, by_end_use(model, consumption(model)))
    )


@bk.blick(
    title="End-use split of consumption",
    unit="fraction",
    plot=bk.plots.stacked_area(x=TIME, y=VALUE, color=END_USE),
    controls=REGION_SPLIT,
    order=WORLD_FIRST,
)
def end_use_split(run: "Run") -> pd.DataFrame:
    """Each end use's share of the material entering use, per region and year; the shares sum to
    one over the end uses; one model at a time."""
    return by_model(
        run, lambda model: shares(with_world(by_end_use(model, consumption(model))), END_USE)
    )


@bk.blick(
    title="Sankey diagram",
    unit="t per year",
    plot=bk.plots.sankey(source="From", target="To", value=VALUE, color="Stage"),
    defaults={TIME: 2050, REGION: WORLD},
    order=WORLD_FIRST,
)
def sankey(run: "Run") -> pd.DataFrame:
    """Every flow of the future system between two processes, for one model, year and region at
    a time, every fifth year; flows from and to the system environment are left out. The stage
    colours the flows: production, use, end of life, recycling, losses, trade or carbonation."""
    return by_model(run, _sankey)


def _sankey(model: "CommonModel") -> pd.DataFrame:
    mfa = model.future_mfa
    display_names = type(model).DisplayNamesCls()
    last = last_historical_year(model)
    years = [year for year in mfa.dims["t"].items if year % SANKEY_YEAR_STEP == 0 or year == last]
    parts = []
    for flow in mfa.flows.values():
        source, target = flow.from_process.name, flow.to_process.name
        if "sysenv" in (source, target):
            continue
        table = with_world(frame(flow.sum_to(("t", "r"))))
        table = table[table[TIME].isin(years)]
        parts.append(
            table.assign(
                From=_display(display_names, source),
                To=_display(display_names, target),
                Stage=_stage(source, target),
            )
        )
    table = pd.concat(parts, ignore_index=True)
    return table[[TIME, REGION, "From", "To", "Stage", VALUE]]


@bk.blick(
    title="IAMC variables",
    plot=bk.plots.line(x=TIME, y=VALUE, color=REGION),
    independent_y=True,
)
def iamc_variables(run: "Run") -> pd.DataFrame:
    """The variables the models report in IAMC format, per region and year, in the reporting
    units, which the variable names carry; one model and variable at a time. World is the
    aggregate the IAMC export writes."""
    return by_model(run, _iamc_variables)


def _iamc_variables(model: "CommonModel") -> pd.DataFrame:
    iamc = model.data_writer.iamc_dataframe(model)
    if iamc is None:
        raise bk.Skip(f"the {model.name} model reports no IAMC variables")
    data = iamc.data
    table = pd.DataFrame(
        {
            TIME: data["year"].astype(int),
            REGION: data["region"],
            "Variable": data["variable"] + " [" + data["unit"] + "]",
            VALUE: data["value"],
        }
    )
    return table.sort_values(["Variable", REGION, TIME], ignore_index=True)


def _display(display_names, process: str) -> str:
    return str(display_names[process]).replace("<br>", " ")


_STAGES: tuple[tuple[str, frozenset[str]], ...] = (
    ("Trade", frozenset({"imports", "exports"})),
    ("Carbonation", frozenset({"atmosphere", "carbonation"})),
    (
        "Losses",
        frozenset(
            {
                "losses",
                "excess_scrap",
                "hibernating",
                "eol_waste",
                "mismanaged",
                "uncontrolled",
                "emission",
                "captured",
            }
        ),
    ),
    ("Recycling", frozenset({"reclmech", "reclchem", "scrap_pool", "scrap_market"})),
    ("End of life", frozenset({"eol_management", "sorting", "reuse"})),
    ("Use", frozenset({"use"})),
)


def _stage(source: str, target: str) -> str:
    """The stage a flow belongs to, from the processes it connects; production by default."""
    for stage, processes in _STAGES:
        if source in processes or target in processes:
            return stage
    return "Production"
