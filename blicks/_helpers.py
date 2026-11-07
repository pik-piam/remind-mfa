"""What the Blick modules share: the run's models, long tables of flodym arrays, and the names of
the dimensions and columns the Blicks use.

Discovery skips this module, as it skips every module whose name starts with an underscore.
remind-mfa and flodym are imported for annotations only, so that ``blicket list`` does not import
the model code.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

import pandas as pd

import blicket as bk

if TYPE_CHECKING:  # annotations only
    import flodym as fd

    from blicketconf import Run
    from remind_mfa.common.common_mfa_system import CommonMFASystem
    from remind_mfa.common.common_model import CommonModel

MODEL = "Model"
TIME = "Time"
HISTORICAL_TIME = "Historical Time"
REGION = "Region"
END_USE = "End Use"
PERIOD = "Period"
HISTORICAL = "Historical"
PROJECTED = "Projected"
WORLD = "World"
VALUE = "value"

MARKET = "Market"

PERIOD_ORDER = {PERIOD: [HISTORICAL, PROJECTED]}
"""Display order of the ``Period`` dimension, for ``order=`` of a Blick."""

WORLD_FIRST = {REGION: [WORLD]}
"""World in front of the regions, for ``order=`` of a Blick with the world total as a region; the
first region is also the one a split shows when the viewer turns it into a filter."""

REGION_SPLIT = {REGION: "split"}
"""One panel per region, for ``controls=`` of a Blick."""

type ArrayOf = Callable[["CommonMFASystem"], "fd.FlodymArray"]
type TableOf = Callable[["CommonModel"], "pd.DataFrame | fd.FlodymArray"]


def model_of(run: "Run", name: str) -> "CommonModel":
    """The model ``name`` of the run, for a Blick of that model.

    A Blick of a model the run lacks does not apply to the run and is skipped.

    Args:
        run: The run.
        name: The model the Blick reads, such as ``"steel"``.

    Returns:
        The model.

    Raises:
        bk.Skip: If the run holds no such model.
    """
    try:
        return run.models[name]
    except KeyError:
        raise bk.Skip(f"a {_listed(run.names)} run; this Blick reads {name} runs") from None


def by_model(run: "Run", build: TableOf) -> pd.DataFrame:
    """One table over the run's models, ``build`` of each, with the model's name as the dimension
    ``Model`` first, in the run's order.

    A model whose ``build`` raises ``bk.Skip`` is left out; when every model's does, the Blick is
    skipped with their reasons.

    Args:
        run: The run.
        build: The table, or the flodym array, of one model.

    Returns:
        The table.

    Raises:
        bk.Skip: If ``build`` skips every model.
    """
    parts: dict[str, pd.DataFrame] = {}
    reasons = []
    for name, model in run.models.items():
        try:
            table = build(model)
        except bk.Skip as skip:
            reasons.append(f"{name}: {skip.reason}")
            continue
        parts[name] = table if isinstance(table, pd.DataFrame) else frame(table)
    if not parts:
        raise bk.Skip("; ".join(reasons))
    table = pd.concat(parts, names=[MODEL]).reset_index(level=MODEL).reset_index(drop=True)
    return in_order(table, MODEL, list(parts))


def _listed(names: list[str]) -> str:
    """``names`` as ``a, b and c``."""
    return " and ".join(part for part in (", ".join(names[:-1]), names[-1]) if part)


def frame(array: "fd.FlodymArray", names: dict[str, str] | None = None) -> pd.DataFrame:
    """The array as a long table: one column per dimension, then ``value``.

    ``Historical Time`` is called ``Time``, so a historical array and its future counterpart share
    a chart; ``names`` renames further dimensions.

    Args:
        array: The array.
        names: Dimension names to rename, old to new.

    Returns:
        The table.
    """
    table = array.to_df(index=False)
    return table.rename(columns={HISTORICAL_TIME: TIME, **(names or {})})


def with_world(table: pd.DataFrame) -> pd.DataFrame:
    """Add the sum over all regions as the region ``World``, in front of the regions.

    Args:
        table: A long table with a ``Region`` and a ``value`` column.

    Returns:
        The table with the World rows first.
    """
    others = [column for column in table.columns if column not in (REGION, VALUE)]
    if others:
        world = table.groupby(others, as_index=False, sort=False)[VALUE].sum()
    else:
        world = pd.DataFrame({VALUE: [table[VALUE].sum()]})
    world[REGION] = WORLD
    return pd.concat([world[table.columns], table], ignore_index=True)


def per_capita_with_world(model: "CommonModel", table: pd.DataFrame) -> pd.DataFrame:
    """``table`` per person, with the world total per world population as the region ``World``,
    first.

    Args:
        model: The model whose population divides the values.
        table: A long table with a ``Time``, a ``Region`` and a ``value`` column, without World.

    Returns:
        The table with the World rows first.
    """
    population = with_world(frame(model.future_mfa.parameters["population"]))
    merged = with_world(table).merge(
        population.rename(columns={VALUE: "population"}), on=[TIME, REGION], how="left"
    )
    merged[VALUE] = merged[VALUE] / merged["population"]
    return merged.drop(columns="population")


def history_and_future(table: pd.DataFrame, last_historical_year: int) -> pd.DataFrame:
    """Split the rows at the last historical year into the periods ``Historical`` and
    ``Projected``, which share that year, so a line with ``linetype=Period`` shows where history
    ends.

    Args:
        table: A long table with a ``Time`` column.
        last_historical_year: The last year of the historical period.

    Returns:
        The table with a ``Period`` column before ``value``.
    """
    historical = table[table[TIME] <= last_historical_year].assign(**{PERIOD: HISTORICAL})
    projected = table[table[TIME] >= last_historical_year].assign(**{PERIOD: PROJECTED})
    split = pd.concat([historical, projected], ignore_index=True)
    columns = [column for column in table.columns if column != VALUE]
    return split[[*columns, PERIOD, VALUE]]


def last_historical_year(model: "CommonModel") -> int:
    """The last year of the model's historical period."""
    return int(model.dims["h"].items[-1])


def per_capita(array: "fd.FlodymArray", mfa: "CommonMFASystem") -> "fd.FlodymArray":
    """``array`` divided by the population of its region and year."""
    return array / mfa.parameters["population"]


def shares(table: pd.DataFrame, over: str) -> pd.DataFrame:
    """The values as shares of their sum over the dimension ``over``, per combination of the other
    dimensions; a share of a zero sum is null.

    Args:
        table: A long table.
        over: The dimension the shares sum to one over.

    Returns:
        The table with the shares as ``value``.
    """
    others = [column for column in table.columns if column not in (over, VALUE)]
    totals = table.groupby(others, sort=False)[VALUE].transform("sum")
    return table.assign(**{VALUE: table[VALUE] / totals.where(totals != 0)})


def in_order(table: pd.DataFrame, column: str, values: list[str]) -> pd.DataFrame:
    """``table`` with ``column`` as an ordered categorical of ``values``, which blicket takes as
    the display order of the dimension; for an order that depends on the run, such as the
    models or the markets it holds, where ``order=`` of a Blick cannot name it.

    Args:
        table: A long table.
        column: The dimension column to order.
        values: Its values in display order; every value of the column must be among them.

    Returns:
        The table with the column ordered.
    """
    return table.assign(**{column: pd.Categorical(table[column], categories=values, ordered=True)})


def end_use_letter(model: "CommonModel", array: "fd.FlodymArray") -> str:
    """The letter of the end-use-like dimension of ``array``: ``e`` (Extended End Use) in the
    cement model with the bottom-up module, ``u`` (End Use) otherwise."""
    if model.name == "cement" and "e" in array.dims.letters:
        return "e"
    return "u"


def by_end_use(model: "CommonModel", array: "fd.FlodymArray") -> pd.DataFrame:
    """``array`` summed to time, region and end use, as a table whose end-use column is called
    ``End Use`` whatever the dimension is called in the model."""
    letter = end_use_letter(model, array)
    summed = array.sum_to(("t", "r", letter))
    return frame(summed, {summed.dims[letter].name: END_USE})


# What the models call production, the in-use stock and the consumption. Each model defines its
# flows in <model>_definition.py; these pick the ones the Blicks show.

PRODUCTION: dict[str, ArrayOf] = {
    "steel": lambda mfa: (
        mfa.flows["steel_production_ore_based => forming"]
        + mfa.flows["steel_production_scrap_based => forming"]
    ),
    "cement": lambda mfa: mfa.flows["cement_production => cement_market"],
    "plastics": lambda mfa: (
        mfa.flows["polymerization => primary_market"]
        + mfa.flows["aux_recyclate_market => primary_market"]
    ),
}
"""Production, before trade: crude steel out of both routes, cement, and primary plus
mechanically recycled polymers."""

IN_USE_STOCK: dict[str, ArrayOf] = {
    "steel": lambda mfa: mfa.stocks["use"].stock,
    "cement": lambda mfa: mfa.stocks["use"].stock[{"k": "Cement"}],
    "plastics": lambda mfa: mfa.stocks["use"].stock,
}
"""The in-use stock; for cement the cement within the construction materials in use."""

CONSUMPTION: dict[str, ArrayOf] = {
    "steel": lambda mfa: mfa.stocks["use"].inflow,
    "cement": lambda mfa: mfa.stocks["use"].inflow[{"k": "Cement"}],
    "plastics": lambda mfa: mfa.stocks["use"].inflow,
}
"""Consumption: the material entering use."""


def production(model: "CommonModel") -> "fd.FlodymArray":
    """The model's production per year and region, in t per year."""
    return PRODUCTION[model.name](model.future_mfa).sum_to(("t", "r"))


def in_use_stock(model: "CommonModel") -> "fd.FlodymArray":
    """The model's in-use stock, over every dimension the model resolves it by."""
    return IN_USE_STOCK[model.name](model.future_mfa)


def consumption(model: "CommonModel") -> "fd.FlodymArray":
    """The model's consumption, over every dimension the model resolves it by."""
    return CONSUMPTION[model.name](model.future_mfa)
